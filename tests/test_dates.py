from pharma_ocr_date_rag.dates import extract_dates, repair_ocr_noise


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
