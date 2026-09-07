from pharma_ocr_date_rag.dates import extract_dates


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
