import pytest

from pharma_dates.rules.dates import extract_dates, repair_ocr_noise


def test_extracts_common_pharma_dates():
    text = "Manufacture Date: 15 Apr 2026. Expiry Date: 14 Apr 2028."
    hits = extract_dates(text)
    assert [(hit.normalized, hit.label) for hit in hits] == [
        ("2026-04-15", "manufacture"),
        ("2028-04-14", "expiry"),
    ]


def test_extracts_month_year_expiry():
    hits = extract_dates("EXP: 07/2029")
    assert len(hits) == 1
    assert hits[0].normalized == "2029-07"
    assert hits[0].label == "expiry"


def test_repairs_common_ocr_noise_before_extraction():
    text = "Manufacturc Date: 2O26-O8-12. EXP1RY: O8/2O28."
    hits = extract_dates(text)
    assert [(hit.normalized, hit.label) for hit in hits] == [
        ("2026-08-12", "manufacture"),
        ("2028-08", "expiry"),
    ]


def test_ocr_repair_is_limited_to_date_like_tokens():
    repaired = repair_ocr_noise("Lot DCC-O812-26 was scanned near 2O26.O8.21.")
    assert "DCC-O812-26" in repaired
    assert "2026.08.21" in repaired


@pytest.mark.parametrize(
    ("text", "labels"),
    [
        ("Manufacturing Date: 05-Jan-2026   Expiry Date: 05-Jan-2028", ["manufacture", "expiry"]),
        ("Mfg. Date: 05-Jan-2026   Retest Date: 05-Jan-2027", ["manufacture", "retest"]),
        ("Retest Date: 05-Jan-2027   Expiry Date: 05-Jan-2028", ["retest", "expiry"]),
        ("Re-test date: 05-Jan-2027", ["retest"]),
        ("Manufacturing date: 2026-01-05", ["manufacture"]),
        ("Date of manufacturing: 2026-01-05", ["manufacture"]),
        ("Issue date: 2026-01-05", ["document"]),
        ("Date of issue: 2026-01-05", ["document"]),
        ("Release Date: 2026-01-05", ["release"]),
    ],
)
def test_common_field_words_label_their_own_date(text, labels):
    assert [hit.label for hit in extract_dates(text)] == labels


def test_a_label_does_not_reach_past_another_date():
    # "Analysis" is not a field word, so the analysis date is unlabeled, not "manufacture".
    hits = extract_dates("Mfg: 05-Jan-2026   Analysis: 07-Jan-2026")
    assert [hit.label for hit in hits] == ["manufacture", "unknown"]
    # A field word right before a later date is that date's label, not the earlier one's.
    hits = extract_dates("05-Jan-2026   Expiry Date: 05-Jan-2028")
    assert [hit.label for hit in hits] == ["unknown", "expiry"]


def test_first_issue_in_a_revision_row_is_not_an_issue_label():
    assert [hit.label for hit in extract_dates("1.0 12.Jun.2018 First issue")] == ["unknown"]
