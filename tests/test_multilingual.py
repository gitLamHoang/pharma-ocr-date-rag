import json
from pathlib import Path

import pytest

from pharma_ocr_date_rag.dates import extract_dates

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "data" / "multilingual_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
@pytest.mark.parametrize("use_explicit_language", [False, True], ids=["all-languages", "explicit"])
def test_multilingual_regression_case(case, use_explicit_language):
    language = case["language"] if use_explicit_language else "auto"
    hits = extract_dates(case["text"], language=language, date_order=case["date_order"])
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


@pytest.mark.parametrize("options", [{"language": "zz"}, {"date_order": "ymd"}])
def test_invalid_configuration_is_rejected(options):
    with pytest.raises(ValueError):
        extract_dates("Expiry: 2028-04-14", **options)


def test_noise_repair_can_be_disabled():
    assert extract_dates("EXP1RY: 2O28-O8-2I", repair_ocr=False) == []
