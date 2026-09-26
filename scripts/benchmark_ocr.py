"""Measure date-field extraction from real OCR of synthetic page pixels, including failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fetch_ocr_models import model_hashes

from pharma_ocr_date_rag.dates import extract_dates
from pharma_ocr_date_rag.ocr import OCRExecutionError, OCRUnavailable, read_tesseract, tesseract_info

DATASET = ROOT / "data" / "ocr_cases.json"
REPORT = ROOT / "reports" / "image_ocr.json"
FIELDS = ("label", "normalized", "candidates")
SETTINGS = {"oem": 1, "psm": 6, "timeout_seconds": 30, "repair_ocr": True}
CONDITIONS = {
    "clean": "Original committed RGB PNG, unchanged",
    "degraded": "Grayscale; resize to 55% (floor, bilinear); Gaussian blur radius 0.4; rotate 1.2 degrees (bicubic, expanded, white fill)",
}


def field_records(text: str, case: dict) -> list[dict]:
    return [
        asdict(hit) for hit in extract_dates(text, language=case["language"], date_order=case["date_order"])
    ]


def score_fields(expected: list[dict], predicted: list[dict]) -> dict:
    # Count occurrences, so a duplicate OCR hit cannot disappear inside a set.
    def counts(rows):
        return Counter(json.dumps({key: row[key] for key in FIELDS}, sort_keys=True) for row in rows)

    gold, found = counts(expected), counts(predicted)
    tp = sum((gold & found).values())
    fp, fn = sum((found - gold).values()), sum((gold - found).values())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "exact": gold == found,
        "missing": [json.loads(value) for value in sorted((gold - found).elements())],
        "extra": [json.loads(value) for value in sorted((found - gold).elements())],
    }


def prepare_image(source: Path, condition: str, destination: Path) -> Path:
    if condition == "clean":
        return source
    if condition != "degraded":
        raise ValueError(f"Unknown image condition: {condition}")
    try:
        from PIL import Image, ImageFilter
    except ImportError as exc:
        raise OCRUnavailable("Pillow is required to generate the degraded image fixture") from exc
    with Image.open(source) as image:
        gray = image.convert("L")
        small = gray.resize((int(image.width * 0.55), int(image.height * 0.55)), Image.Resampling.BILINEAR)
        degraded = small.filter(ImageFilter.GaussianBlur(0.4)).rotate(
            1.2, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        degraded.save(destination)
    return destination


def provenance(cases: list[dict]) -> dict:
    paths = {
        DATASET,
        ROOT / "data" / "ocr_models.json",
        Path(__file__).resolve(),
        ROOT / "scripts" / "fetch_ocr_models.py",
    }
    paths.update(
        ROOT / "src" / "pharma_ocr_date_rag" / name for name in ("ocr.py", "dates.py", "languages.py")
    )
    paths.update(ROOT / case[key] for case in cases for key in ("source", "image"))
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)
    }


def summarize(results: list[dict]) -> dict:
    totals = {}
    for condition in CONDITIONS:
        rows = [row for row in results if row["condition"] == condition]
        measured = [row for row in rows if row["status"] == "measured"]
        totals[condition] = {
            "attempted": len(rows),
            "measured": len(measured),
            "unavailable": sum(row["status"] == "unavailable" for row in rows),
            "failed": sum(row["status"] == "failed" for row in rows),
            "exact_pages": sum(row["score"]["exact"] for row in measured),
            "expected_fields_all_pages": sum(row["expected_fields"] for row in rows),
            "expected_fields_measured_pages": sum(row["expected_fields"] for row in measured),
            **{
                key: sum(row["score"][key] for row in measured)
                for key in ("true_positive", "false_positive", "false_negative")
            },
        }
    return totals


def benchmark(tessdata_dir: Path, images_dir: Path) -> dict:
    cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    hashes = model_hashes(tessdata_dir)
    environment = {"python": platform.python_version(), "platform": platform.platform()}
    try:
        from PIL import __version__ as pillow_version

        environment["pillow"] = pillow_version
        environment["tesseract"] = tesseract_info(tessdata_dir)
    except (ImportError, OCRUnavailable, OCRExecutionError) as exc:
        environment["probe_error"] = str(exc)
    results = []
    for case in cases:
        baseline = score_fields(
            case["expected"], field_records((ROOT / case["source"]).read_text(encoding="utf-8"), case)
        )
        for condition in CONDITIONS:
            row = {
                "id": case["id"],
                "condition": condition,
                "language": case["language"],
                "ocr_language": case["ocr_language"],
                "date_order": case["date_order"],
                "expected_fields": len(case["expected"]),
                "text_baseline": baseline,
            }
            start = time.perf_counter()
            try:
                image = prepare_image(
                    ROOT / case["image"], condition, images_dir / f"{case['id']}-{condition}.png"
                )
                row["image_sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
                result = read_tesseract(
                    image,
                    language=case["ocr_language"],
                    psm=SETTINGS["psm"],
                    timeout=SETTINGS["timeout_seconds"],
                    tessdata_dir=tessdata_dir,
                )
                predicted = field_records(result.text, case)
                row.update(
                    status="measured",
                    ocr_text=result.text,
                    predicted=predicted,
                    score=score_fields(case["expected"], predicted),
                )
            except OCRUnavailable as exc:
                row.update(status="unavailable", error=str(exc))
            except (OCRExecutionError, OSError) as exc:
                row.update(status="failed", error=str(exc))
            row["elapsed_seconds"] = round(time.perf_counter() - start, 4)
            results.append(row)
    return {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Real Tesseract OCR of three synthetic rendered pages in two conditions; not held-out, scanner, clinical, or model-training evidence",
        "metric": "Occurrence-aware exact (label, normalized, candidates) match per page; no cross-page pooling of matches",
        "settings": SETTINGS,
        "conditions": CONDITIONS,
        "environment": environment,
        "model_sha256": hashes,
        "input_and_source_sha256": provenance(cases),
        "summary": summarize(results),
        "results": results,
    }


def check_report(report: dict) -> None:
    """Check hashes and recompute scores from saved OCR text; does NOT rerun OCR."""
    cases = {case["id"]: case for case in json.loads(DATASET.read_text(encoding="utf-8"))["cases"]}
    if report["schema_version"] != 1 or report["settings"] != SETTINGS or report["conditions"] != CONDITIONS:
        raise ValueError("Saved OCR protocol differs from the current experiment")
    if report["input_and_source_sha256"] != provenance(list(cases.values())):
        raise ValueError("OCR report inputs/code changed; rerun the image benchmark and review the results")
    expected_keys = {(case_id, condition) for case_id in cases for condition in CONDITIONS}
    rows = report["results"]
    if len(rows) != len(expected_keys) or {(row["id"], row["condition"]) for row in rows} != expected_keys:
        raise ValueError("OCR report must contain every page/condition exactly once")
    if report["model_sha256"] != json.loads((ROOT / "data" / "ocr_models.json").read_text())["models"]:
        raise ValueError("OCR report must use all pinned models")
    for row in rows:
        case = cases[row["id"]]
        if any(row[key] != case[key] for key in ("language", "ocr_language", "date_order")):
            raise ValueError("Saved language/date-order settings do not match the case")
        if (
            row["condition"] == "clean"
            and row["image_sha256"] != hashlib.sha256((ROOT / case["image"]).read_bytes()).hexdigest()
        ):
            raise ValueError("Saved clean-image hash does not match its source")
        if row["status"] != "measured":
            raise ValueError("Checked-in OCR evidence must contain measured results for every page")
        predicted = field_records(row["ocr_text"], case)
        if row["score"] != score_fields(case["expected"], predicted):
            raise ValueError(f"Saved score does not match OCR text: {row['id']}/{row['condition']}")
        if json.dumps(predicted, sort_keys=True) != json.dumps(row["predicted"], sort_keys=True):
            raise ValueError("Saved field evidence does not match OCR text")
        baseline = score_fields(
            case["expected"], field_records((ROOT / case["source"]).read_text(encoding="utf-8"), case)
        )
        if row["text_baseline"] != baseline or row["expected_fields"] != len(case["expected"]):
            raise ValueError("Saved text baseline or expected field count is stale")
    if report["summary"] != summarize(rows):
        raise ValueError("Saved summary does not match individual measurements")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tessdata-dir", type=Path, default=ROOT / "outputs" / "tessdata")
    parser.add_argument("--images-dir", type=Path, default=ROOT / "outputs" / "ocr-images")
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument(
        "--check-report", action="store_true", help="Verify saved evidence without running OCR"
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail for unavailable/failed runs, not measured extraction errors",
    )
    args = parser.parse_args()
    try:
        if args.check_report:
            check_report(json.loads(args.output.read_text(encoding="utf-8")))
            print("Saved OCR provenance and scores verified (OCR not rerun).")
            return
        report = benchmark(args.tessdata_dir, args.images_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    for condition, summary in report["summary"].items():
        print(f"{condition}: {json.dumps(summary)}")
    if args.require_complete and any(row["status"] != "measured" for row in report["results"]):
        parser.exit(1, "Incomplete OCR run; see per-page unavailable/failed reasons in the report.\n")


if __name__ == "__main__":
    main()
