"""Portable evidence records shared by the CLI and review UI."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict

from .pipeline import ProcessedDocument


def date_rows(documents: list[ProcessedDocument]) -> list[dict]:
    rows = []
    for document in documents:
        digest = hashlib.sha256(document.ocr.text.encode("utf-8")).hexdigest()
        for hit in document.dates:
            rows.append(
                {
                    "document": document.path.name,
                    "source_sha256": digest,
                    "line": document.ocr.text.count("\n", 0, hit.start) + 1,
                    "engine": document.ocr.engine,
                    "language": document.language,
                    "date_order": document.date_order,
                    **asdict(hit),
                    "needs_review": bool(hit.review_reasons),
                }
            )
    return rows


def export_json(rows: list[dict]) -> str:
    return json.dumps({"schema_version": 1, "dates": rows}, indent=2, ensure_ascii=False)


def _csv_cell(value: object) -> object:
    if isinstance(value, (list, tuple)):
        value = " | ".join(str(item) for item in value)
    # Preserve literal document text when opened in a spreadsheet.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(rows: list[dict]) -> str:
    output = io.StringIO(newline="")
    fields = [
        "document",
        "line",
        "raw_text",
        "normalized",
        "label",
        "precision",
        "needs_review",
        "review_reasons",
        "candidates",
        "context",
        "start",
        "end",
        "confidence",
        "language",
        "date_order",
        "engine",
        "source_sha256",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_cell(row.get(key, "")) for key in fields})
    return output.getvalue()
