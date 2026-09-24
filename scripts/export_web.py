"""Export the Python extraction results for the standalone browser workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pharma_ocr_date_rag.languages import FIELD_WORDS
from pharma_ocr_date_rag.pipeline import process_document
from pharma_ocr_date_rag.reporting import date_rows
from pharma_ocr_date_rag.review import EXTRACTOR_VERSION

PUBLIC = ROOT / "web" / "public"
TITLES = {
    "alpha_packaging_coa": ("Packaging certificate", "Alpha Packaging", "en"),
    "beta_excipient_report": ("Incoming material report", "Beta Excipient", "en"),
    "delta_noisy_scan": ("Cold-chain inspection", "Delta Cold Chain", "en"),
    "gamma_stability_notice": ("Stability pull notice", "Gamma Lab", "en"),
    "fr_certificat": ("Certificat de contrôle", "Atelier F", "fr"),
    "de_pruefbericht": ("Prüfbericht", "Werk D", "de"),
    "es_informe": ("Informe de material", "Taller E", "es"),
    "vi_phieu_kiem_tra": ("Phiếu kiểm tra", "Xưởng V", "vi"),
}


def render_page(document, path: Path, font_path: str) -> dict:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1040, 1380
    font = ImageFont.truetype(font_path, 18)
    small = ImageFont.truetype(font_path, 14)
    title = ImageFont.truetype(font_path, 23)
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 12), fill="#19675e")
    draw.text((72, 56), "SYNTHETIC SOURCE DOCUMENT", fill="#19675e", font=small)
    draw.text((72, 90), document.path.name, fill="#243a36", font=title)
    draw.line((72, 140, width - 72, 140), fill="#d9e2de", width=2)
    for i, line in enumerate(document.ocr.text.splitlines()):
        draw.text((72, 184 + i * 34), line, fill="#243a36", font=font)
    draw.line((72, height - 90, width - 72, height - 90), fill="#d9e2de", width=1)
    draw.text(
        (72, height - 66), "PUBLIC TEST FIXTURE / No real vendor or patient data", fill="#667771", font=small
    )
    draw.text((width - 130, height - 66), "01 / 01", fill="#667771", font=small)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    boxes = {}
    for hit in document.dates:
        line_start = document.ocr.text.rfind("\n", 0, hit.start) + 1
        line_number = document.ocr.text.count("\n", 0, hit.start)
        x = 72 + font.getlength(document.ocr.text[line_start : hit.start])
        w = font.getlength(hit.raw_text)
        boxes[f"{hit.start}:{hit.end}"] = [
            round(x / width, 6),
            round((184 + line_number * 34) / height, 6),
            round(w / width, 6),
            round(27 / height, 6),
        ]
    return {"width": width, "height": height, "boxes": boxes}


def export(render: bool = False, font: str | None = None) -> dict:
    paths = sorted((ROOT / "data" / "synthetic_docs").glob("*.txt"))
    paths += sorted((ROOT / "data" / "multilingual_docs").glob("*.txt"))
    documents = []
    for path in paths:
        document = process_document(path)
        name = path.stem
        title, vendor, language = TITLES[name]
        image_path = PUBLIC / "documents" / f"{name}.png"
        layout_path = PUBLIC / "documents" / f"{name}.json"
        if render:
            if not font:
                raise ValueError("--font is required with --render")
            layout = render_page(document, image_path, font)
            layout_path.write_text(json.dumps(layout, indent=2) + "\n", encoding="utf-8")
        layout = json.loads(layout_path.read_text())
        fields = date_rows([document])
        for row in fields:
            row["id"] = f"{name}:{row['start']}:{row['end']}"
            row["box"] = layout["boxes"][f"{row['start']}:{row['end']}"]
        documents.append(
            {
                "id": name,
                "filename": path.name,
                "title": title,
                "vendor": vendor,
                "language": language,
                "text": document.ocr.text,
                "fields": fields,
                "sha256": hashlib.sha256(document.ocr.text.encode()).hexdigest(),
                "image": f"documents/{name}.png",
                "imageSha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "page": {"width": layout["width"], "height": layout["height"]},
            }
        )
    benchmark = json.loads((ROOT / "docs" / "benchmark_results.json").read_text())
    cases = json.loads((ROOT / "data" / "multilingual_cases.json").read_text())["cases"]
    return {
        "schemaVersion": 1,
        "extractorVersion": EXTRACTOR_VERSION,
        "scope": "Authored synthetic development fixtures. Text extraction, not measured image OCR.",
        "documents": documents,
        "benchmark": benchmark,
        "cases": cases,
        "fieldVocabulary": FIELD_WORDS,
        "sourceSha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "src" / "pharma_ocr_date_rag").glob("*.py"))
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--font", help="Path to a Unicode TrueType font for rendering synthetic pages")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = json.dumps(export(args.render, args.font), ensure_ascii=False, indent=2) + "\n"
    output = PUBLIC / "data" / "workspace.json"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != data:
            raise SystemExit("Browser evidence is stale; regenerate scripts/export_web.py.")
        print("Browser snapshot matches source, images and Python extraction.")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(data, encoding="utf-8")
        print(f"Exported {len(json.loads(data)['documents'])} documents to {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
