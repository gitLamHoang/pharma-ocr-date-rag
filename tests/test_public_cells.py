import importlib
import json
from pathlib import Path

import pytest

from pharma_ocr_date_rag.recalls import date_cell

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "data/mhra_cell_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["record_id"] for case in CASES])
def test_source_cell_semantics_match_explicit_regression_gold(case):
    assert date_cell(case["raw_text"], role=case["role"]) == case["expected"]


@pytest.mark.parametrize(
    "text,role",
    [
        ("Not Distributed", "expiry"),
        ("Not yet distributed except batch 100", "distribution"),
        ("Not yet distributed on 20/09/2026", "distribution"),
        ("May 2026 to June 2026", "expiry"),
        ("All lots with an expiry date up to and including 09/10/2026", "expiry"),
        ("All lots with an expiry date up to and including 29/02/2027", "expiry"),
        ("All lots with an expiry date up to and including 05/29", "expiry"),
        ("All lots with an expiry date up to and including 05/2029 except batch A", "expiry"),
        ("All lots with an expiry date up to but not including 05/2029", "expiry"),
        ("All lots with an expiry date up to and including 05/2029", "distribution"),
        ("All lots with an expiry date up to and including 05/2029**", "expiry"),
        ("All lots with an expiry date up to and including 05/2029* trailing text", "expiry"),
        ("Quarantined at wholesaler since 01/09/2026", "distribution"),
    ],
)
def test_partial_qualified_ambiguous_and_invalid_statements_never_become_dates(text, role):
    result = date_cell(text, role=role)
    assert result["value_kind"] == "unparsed"
    assert result["normalized"] is None and result["candidates"] == []
    assert result["cutoff"] is None and result["statement"] is None


def test_explicit_day_cutoff_keeps_its_day_but_never_becomes_a_single_date():
    result = date_cell("All lots with an expiry date up to and including 2028-02-29", role="expiry")
    assert result["cutoff"] == {"upper": "2028-02-29", "inclusive": True, "precision": "day"}
    assert result["normalized"] is None and result["candidates"] == []


def test_case_and_whitespace_changes_do_not_change_a_source_statement():
    assert date_cell("  NOT   YET\nDISTRIBUTED ", role="distribution")["statement"] == "not_yet_distributed"


def test_single_dates_and_ambiguity_keep_their_original_meaning():
    single = date_cell("05/2028", role="expiry")
    ambiguous = date_cell("09/10/2026", role="expiry")
    assert single["value_kind"] == "date" and single["normalized"] == "2028-05"
    assert ambiguous["value_kind"] == "ambiguous_date"
    assert ambiguous["normalized"] is None and ambiguous["candidates"] == ["2026-09-10", "2026-10-09"]
    assert all(row["cutoff"] is None and row["statement"] is None for row in (single, ambiguous))


def test_report_is_reproducible_and_bound_to_real_source_cells(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    experiment = importlib.import_module("benchmark_cells")
    report = experiment.build()
    assert report == json.loads(experiment.REPORT.read_text(encoding="utf-8"))
    assert report["matches"] == report["cases"] == 6


def test_public_records_preserve_non_dates_cutoffs_and_batch_footnotes():
    records = json.loads((ROOT / "web/public/data/recalls.json").read_text(encoding="utf-8"))["records"]
    groups = {
        kind: [row for row in records if row["value_kind"] == kind]
        for kind in ("date", "ambiguous_date", "cutoff", "non_date", "unparsed")
    }
    assert {kind: len(rows) for kind, rows in groups.items()} == {
        "date": 539,
        "ambiguous_date": 123,
        "cutoff": 3,
        "non_date": 39,
        "unparsed": 38,
    }
    for row in groups["cutoff"] + groups["non_date"]:
        assert row["normalized"] is None and not row["candidates"]
        assert row["status"] == "needs_review"
    assert all("source_footnote" in row["review_reasons"] for row in groups["cutoff"])
