import csv
import io
import json

from pharma_ocr_date_rag.pipeline import process_text
from pharma_ocr_date_rag.reporting import date_rows, export_csv, export_json


def test_json_keeps_ambiguous_candidates_and_source_provenance():
    doc = process_text("review.txt", "Header\nExpiry: 09/01/2026")
    result = json.loads(export_json(date_rows([doc])))
    row = result["dates"][0]
    assert row["normalized"] is None
    assert row["candidates"] == ["2026-01-09", "2026-09-01"]
    assert row["needs_review"] is True
    assert row["line"] == 2
    assert row["raw_text"] == doc.ocr.text[row["start"] : row["end"]]
    assert len(row["source_sha256"]) == 64


def test_csv_keeps_unicode_and_quotes_formula_like_source_text():
    doc = process_text("=sample.txt", "=Hạn sử dụng: 2028-08-21")
    rows = list(csv.DictReader(io.StringIO(export_csv(date_rows([doc])))))
    assert rows[0]["document"] == "'=sample.txt"
    assert rows[0]["context"].startswith("'=Hạn sử dụng")
    assert rows[0]["normalized"] == "2028-08-21"


def test_empty_exports_are_valid():
    assert json.loads(export_json([]))["dates"] == []
    assert list(csv.DictReader(io.StringIO(export_csv([])))) == []
