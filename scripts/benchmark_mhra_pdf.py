"""Run actual OCR on original public MHRA PDFs; measure limited HTML-table date coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fetch_ocr_models import model_hashes

from pharma_ocr_date_rag.dates import extract_dates
from pharma_ocr_date_rag.ocr import read_tesseract, tesseract_info
from pharma_ocr_date_rag.public_data import PublicClient
from pharma_ocr_date_rag.recalls import date_cell, heading_key, split_documents

REPORT = ROOT / "reports/mhra_pdf_ocr.json"


def date_keys(text: str) -> set[tuple[str, ...]]:
    return {hit.candidates for hit in extract_dates(text, language="en", date_order="auto", repair_ocr=False)}


def selected_documents(docs: list[dict]) -> list[dict]:
    splits = split_documents(docs)
    return sorted(
        (doc for doc in docs if splits[doc["id"]] == "test" and doc["pdf_urls"]),
        key=lambda doc: doc["published_at"],
        reverse=True,
    )[:3]


def reference_dates(doc: dict, labels: dict) -> tuple[set[tuple[str, ...]], list[str]]:
    expected, unsupported = set(), []
    for table in doc["tables"]:
        for column, header in enumerate(table["headers"]):
            if labels[heading_key(header)] not in {"expiry", "distribution"}:
                continue
            for row in table["rows"]:
                parsed = date_cell(row[column])
                if parsed["candidates"]:
                    expected.add(tuple(parsed["candidates"]))
                else:
                    unsupported.append(row[column])
    return expected, unsupported


def benchmark() -> dict:
    import pdfplumber
    from PIL import __version__ as pillow_version

    root = ROOT / "outputs/mhra/pdf"
    root.mkdir(parents=True, exist_ok=True)
    client = PublicClient(ROOT / "outputs/mhra/cache")
    dataset_path = ROOT / "data/public_mhra/documents.json"
    label_path = ROOT / "data/public_mhra/header_labels.json"
    docs = json.loads(dataset_path.read_text(encoding="utf-8"))["documents"]
    labels = json.loads(label_path.read_text(encoding="utf-8"))["labels"]
    selected = selected_documents(docs)
    packs = ROOT / "outputs/tessdata"
    results = []
    for doc in selected:
        expected, unsupported = reference_dates(doc, labels)
        result = {
            "document_id": doc["id"],
            "title": doc["title"],
            "url": doc["url"],
            "split": "test",
            "expected_date_keys": sorted(expected),
            "unsupported_html_cells": unsupported,
        }
        try:
            raw, provenance = client.get(doc["pdf_urls"][0], limit=20_000_000)
            if not raw.startswith(b"%PDF-"):
                raise ValueError("Attachment is not a PDF")
            path = root / f"{doc['id']}.pdf"
            path.write_bytes(raw)
            result["pdf_source"] = provenance
            pages = []
            ocr_values, native_values = set(), set()
            with pdfplumber.open(path) as pdf:
                result["total_pdf_pages"] = len(pdf.pages)
                for number, page in enumerate(pdf.pages[:2], 1):
                    image_path = root / f"{doc['id']}-page-{number}.png"
                    page.to_image(resolution=150).save(image_path)
                    ocr = read_tesseract(image_path, language="eng", psm=3, timeout=30, tessdata_dir=packs)
                    native = page.extract_text() or ""
                    ocr_values.update(date_keys(ocr.text))
                    native_values.update(date_keys(native))
                    pages.append(
                        {
                            "page": number,
                            "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                            "ocr_text": ocr.text,
                            "native_text": native,
                        }
                    )
            result.update(
                status="measured",
                pages=pages,
                ocr_matched=sorted(expected & ocr_values),
                ocr_missing=sorted(expected - ocr_values),
                native_matched=sorted(expected & native_values),
                native_missing=sorted(expected - native_values),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            result.update(status="failed", error=str(exc))
        results.append(result)
        print(f"{doc['title'][:75]}: {result['status']}", flush=True)
    source_paths = [
        dataset_path,
        label_path,
        ROOT / "data/public_mhra/protocol.json",
        Path(__file__).resolve(),
        *(
            ROOT / "src/pharma_ocr_date_rag" / name
            for name in ("ocr.py", "dates.py", "languages.py", "public_data.py", "recalls.py")
        ),
    ]
    return {
        "schema_version": 1,
        "scope": "Original public MHRA PDFs, not synthetic pages. Coverage of supported unique HTML-table date interpretations within the first two PDF pages. Not field precision, independent date gold, batch-link accuracy or trained OCR.",
        "protocol": {
            "selection": "Three newest test notices with PDFs",
            "dpi": 150,
            "max_pages_per_document": 2,
            "psm": 3,
            "oem": 1,
            "language": "eng",
            "date_order": "auto",
            "repair_ocr": False,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pillow": pillow_version,
            "pdfplumber": pdfplumber.__version__,
            "tesseract": tesseract_info(packs),
        },
        "model_sha256": model_hashes(packs),
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        },
        "results": results,
    }


def check_report(report: dict) -> None:
    for name, digest in report["source_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"PDF OCR source changed: {name}; rerun the experiment")
    docs = json.loads((ROOT / "data/public_mhra/documents.json").read_text(encoding="utf-8"))["documents"]
    labels = json.loads((ROOT / "data/public_mhra/header_labels.json").read_text(encoding="utf-8"))["labels"]
    selected = selected_documents(docs)
    if [result["document_id"] for result in report["results"]] != [doc["id"] for doc in selected]:
        raise ValueError("PDF measurements do not match the predeclared document selection")
    for result, doc in zip(report["results"], selected):
        if result["status"] != "measured":
            raise ValueError("Checked-in evidence must include three completed PDF measurements")
        expected, unsupported = reference_dates(doc, labels)
        if result["expected_date_keys"] != [list(value) for value in sorted(expected)]:
            raise ValueError("PDF reference dates do not match the source HTML tables")
        if result["unsupported_html_cells"] != unsupported:
            raise ValueError("PDF reference exclusions do not match the source HTML tables")
        if result["pdf_source"]["url"] != doc["pdf_urls"][0]:
            raise ValueError("PDF URL does not match the selected source")
        if [page["page"] for page in result["pages"]] != list(
            range(1, min(2, result["total_pdf_pages"]) + 1)
        ):
            raise ValueError("PDF measurement must cover the first two pages")
        for kind in ("ocr", "native"):
            values = set().union(*(date_keys(page[f"{kind}_text"]) for page in result["pages"]))
            if [list(value) for value in sorted(expected & values)] != result[f"{kind}_matched"]:
                raise ValueError("Saved PDF date coverage does not match transcript")
            if [list(value) for value in sorted(expected - values)] != result[f"{kind}_missing"]:
                raise ValueError("Saved PDF missing dates do not match transcript")
    if len(report["results"]) != 3:
        raise ValueError("Expected three PDF measurements")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-report", action="store_true")
    args = parser.parse_args()
    if args.check_report:
        check_report(json.loads(REPORT.read_text(encoding="utf-8")))
        print("Saved original-PDF OCR evidence verified; OCR not rerun.")
    else:
        report = benchmark()
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if any(result["status"] != "measured" for result in report["results"]):
            raise SystemExit("PDF experiment incomplete; inspect per-document failures")
