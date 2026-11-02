"""Measure same-document date-order suggestions on public cells and declared synthetic fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pharma_ocr_date_rag.conventions import apply_document_order, hit_order, leave_one_out
from pharma_ocr_date_rag.dates import extract_dates

PUBLIC = ROOT / "web/public/data/recalls.json"
REPORT = ROOT / "reports/document_conventions.json"
# Fixtures whose authors declared one numeric order; the declaration is the gold reading.
DECLARED = {
    **{path: "mdy" for path in sorted((ROOT / "data/synthetic_docs").glob("*.txt"))},
    ROOT / "data/mixed_conventions/eu_receipt.txt": "dmy",
    ROOT / "data/mixed_conventions/us_receipt.txt": "mdy",
    ROOT / "data/mixed_conventions/unconfirmed_receipt.txt": None,
}


def public_section() -> dict:
    records = json.loads(PUBLIC.read_text(encoding="utf-8"))["records"]
    ambiguous = [row for row in records if row["value_kind"] == "ambiguous_date"]
    by_document: dict[str, list[tuple[str, str]]] = {}
    for row in records:
        if row["value_kind"] == "date":
            by_document.setdefault(row["document_id"], []).append((row["id"], row["raw_text"]))
    return {
        "ambiguous_cells": len(ambiguous),
        "notices_with_ambiguous_cells": len({row["document_id"] for row in ambiguous}),
        "status": dict(sorted(Counter(row["document_order"]["status"] for row in ambiguous).items())),
        "suggested": sum(row["document_order"]["suggested"] is not None for row in ambiguous),
        "suggested_order": dict(
            sorted(
                Counter(
                    row["document_order"]["order"] for row in ambiguous if row["document_order"]["order"]
                ).items()
            )
        ),
        # Hide each order-revealing cell, predict its order from the rest of its notice.
        "leave_one_out": leave_one_out(by_document.values()),
        "scope": "60 English MHRA notices from one publisher; no MDY notice is present, so this checks consistency within notices, not the ability to tell conventions apart.",
    }


def declared_section() -> dict:
    rows, totals = [], Counter()
    for path, declared in DECLARED.items():
        text = path.read_text(encoding="utf-8")
        hits = extract_dates(text, language="en")
        order = hit_order(hits)
        gold = {
            (hit.start, hit.end): hit.normalized
            for hit in extract_dates(text, language="en", date_order=declared or "auto")
        }
        ambiguous = [hit for hit in hits if hit.normalized is None and len(hit.candidates) > 1]
        resolved = {(hit.start, hit.end): hit.normalized for hit in apply_document_order(hits)}
        suggested = [hit for hit in ambiguous if resolved[(hit.start, hit.end)] is not None]
        correct = [
            hit
            for hit in suggested
            if declared and resolved[(hit.start, hit.end)] == gold[(hit.start, hit.end)]
        ]
        row = {
            "document": str(path.relative_to(ROOT)),
            "declared_order": declared,
            "inferred_status": order.status,
            "inferred_order": order.order,
            "ambiguous": len(ambiguous),
            "suggested": len(suggested),
            "correct": len(correct),
        }
        rows.append(row)
        totals.update({key: row[key] for key in ("ambiguous", "suggested", "correct")})
    return {
        "documents": rows,
        "totals": dict(totals),
        "scope": "Authored development fixtures with a declared convention; written before this method, but small.",
    }


def build() -> dict:
    return {
        "schema_version": 1,
        "method": "Unanimous same-document vote of numeric dates valid in exactly one order; any conflict or no evidence abstains.",
        "command": "python scripts/benchmark_conventions.py",
        "public_register": public_section(),
        "declared_fixtures": declared_section(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the saved report differs")
    args = parser.parse_args()
    report = build()
    if args.check:
        if json.loads(REPORT.read_text(encoding="utf-8")) != report:
            parser.exit(1, f"{REPORT.relative_to(ROOT)} is stale; rerun scripts/benchmark_conventions.py.\n")
    else:
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
