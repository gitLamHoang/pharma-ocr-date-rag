"""Reproduce the authored multilingual extraction regression benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pharma_ocr_date_rag.dates import extract_dates


def benchmark() -> dict:
    path = ROOT / "data" / "multilingual_cases.json"
    raw = path.read_bytes()
    cases = json.loads(raw)["cases"]
    fields = ("normalized", "label", "candidates", "precision", "review_reasons")
    results = {}
    for mode in ("all_languages", "explicit_language"):
        groups = {}
        failures = []
        for case in cases:
            language = "auto" if mode == "all_languages" else case["language"]
            hits = extract_dates(case["text"], language=language, date_order=case["date_order"])
            predicted = [
                {
                    field: list(value) if isinstance(value := getattr(hit, field), tuple) else value
                    for field in fields
                }
                for hit in hits
            ]
            passed = predicted == case["expected"]
            group = groups.setdefault(case["language"], {"passed": 0, "total": 0})
            group["total"] += 1
            group["passed"] += int(passed)
            if not passed:
                failures.append({"id": case["id"], "expected": case["expected"], "predicted": predicted})
        results[mode] = {
            "passed": len(cases) - len(failures),
            "total": len(cases),
            "by_language": groups,
            "failures": failures,
        }
    return {
        "dataset": "data/multilingual_cases.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "metric": "Exact case match: date, label, candidates, precision, review reasons, and no extra hits",
        "scope": "Synthetic development fixtures; not real OCR, held-out accuracy, or clinical validation",
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the complete report as JSON")
    parser.add_argument("--output", type=Path, help="Write a reproducible JSON report")
    parser.add_argument("--check", action="store_true", help="Exit nonzero when any fixture fails")
    args = parser.parse_args()
    report = benchmark()
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    if args.json:
        print(encoded, end="")
    else:
        for mode, result in report["results"].items():
            print(f"{mode}: {result['passed']}/{result['total']} exact case matches")
            for language, group in sorted(result["by_language"].items()):
                print(f"  {language}: {group['passed']}/{group['total']}")
            for failure in result["failures"]:
                print(f"  FAIL {failure['id']}: {failure['predicted']}")
    if args.check and any(result["failures"] for result in report["results"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
