"""Verify explicitly authored date-cell semantics against frozen MHRA source cells."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pharma_ocr_date_rag.recalls import date_cell, heading_key

REPORT = ROOT / "reports/mhra_cells.json"


def build() -> dict:
    cases_path = ROOT / "data/mhra_cell_cases.json"
    source_path = ROOT / "data/public_mhra/documents.json"
    labels_path = ROOT / "data/public_mhra/header_labels.json"
    fixture = json.loads(cases_path.read_text(encoding="utf-8"))
    documents = {doc["id"]: doc for doc in json.loads(source_path.read_text(encoding="utf-8"))["documents"]}
    labels = json.loads(labels_path.read_text(encoding="utf-8"))["labels"]
    results, seen = [], set()
    for case in fixture["cases"]:
        if case["record_id"] in seen:
            raise ValueError("Duplicate source-cell case")
        seen.add(case["record_id"])
        doc_id, table_index, row_index, column_index = case["record_id"].split(":")
        doc = documents[doc_id]
        table = next(table for table in doc["tables"] if table["table_index"] == int(table_index))
        raw = table["rows"][int(row_index)][int(column_index)]
        role = labels[heading_key(table["headers"][int(column_index)])]
        if raw != case["raw_text"] or role != case["role"]:
            raise ValueError("Regression case does not match its frozen source cell and column annotation")
        actual = date_cell(raw, role=role)
        results.append(
            {
                "record_id": case["record_id"],
                "url": doc["url"],
                "source_sha256": doc["source"]["sha256"],
                "raw_text": raw,
                "role": role,
                "expected": case["expected"],
                "actual": actual,
                "match": actual == case["expected"],
            }
        )
    paths = [
        cases_path,
        source_path,
        labels_path,
        Path(__file__).resolve(),
        *(ROOT / "src/pharma_ocr_date_rag" / name for name in ("recalls.py", "dates.py", "languages.py")),
    ]
    return {
        "schema_version": 1,
        "attribution": fixture["attribution"],
        "licence": fixture["licence"],
        "scope": fixture["scope"],
        "cases": len(results),
        "matches": sum(row["match"] for row in results),
        "results": results,
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build()
    if args.check:
        if json.loads(REPORT.read_text(encoding="utf-8")) != report:
            parser.exit(1, "Public-cell report differs from frozen sources and current code.\n")
    else:
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Source-anchored development cases: {report['matches']}/{report['cases']}; not held-out accuracy.")
    if report["matches"] != report["cases"]:
        raise SystemExit("Inspect mismatched date-cell semantics")
