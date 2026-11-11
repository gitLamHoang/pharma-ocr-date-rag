import json
from pathlib import Path

import pytest

from pharma_dates.rules.dates import extract_dates

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES = json.loads((FIXTURES / "regression_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_regression_case(case):
    hits = extract_dates(case["text"], date_order=case["date_order"])
    actual = [
        {
            "normalized": hit.normalized,
            "label": hit.label,
            "candidates": list(hit.candidates),
            "precision": hit.precision,
            "review_reasons": list(hit.review_reasons),
        }
        for hit in hits
    ]
    assert actual == case["expected"]
    for hit in hits:
        assert case["text"][hit.start : hit.end] == hit.raw_text


def test_source_positions_survive_ocr_word_repairs_and_repeated_dates():
    text = "Q.C. check: 2O26-O8-2I\nExpiry: 2026-08-21; Manufactured: 2026-08-21"
    hits = extract_dates(text)
    assert [hit.label for hit in hits] == ["qa_check", "expiry", "manufacture"]
    assert [hit.raw_text for hit in hits] == ["2O26-O8-2I", "2026-08-21", "2026-08-21"]
    for hit in hits:
        assert text[hit.start : hit.end] == hit.raw_text


def test_invalid_date_order_is_rejected():
    with pytest.raises(ValueError):
        extract_dates("Expiry: 2028-04-14", date_order="ymd")


@pytest.mark.parametrize(
    "text",
    [
        "Date de péremption: 28 février 2028",
        "Fecha de caducidad: 31 de enero de 2028",
        "Verfall: 31. März 2028",
    ],
)
def test_non_english_month_names_are_not_parsed(text):
    assert extract_dates(text) == []


def test_non_english_field_words_get_no_label():
    [hit] = extract_dates("Réception: 24/03/2026")
    assert (hit.normalized, hit.label) == ("2026-03-24", "unknown")


def test_noise_repair_can_be_disabled():
    assert extract_dates("EXP1RY: 2O28-O8-2I", repair_ocr=False) == []
