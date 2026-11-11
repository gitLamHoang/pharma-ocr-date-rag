"""Date formats and OCR repairs added for scanned pages (roman months, spaced numerics, noisy month
abbreviations, label-adjacent forms), and look-alikes that must stay non-dates."""

import pytest

from pharma_dates.rules.dates import extract_dates


def one(text: str):
    hits = extract_dates(text)
    assert len(hits) == 1, [h.raw_text for h in hits]
    hit = hits[0]
    assert text[hit.start : hit.end] == hit.raw_text
    return hit


# --- Roman-numeral months ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "raw", "value"),
    [
        ("Notarized on 12.III.2026", "12.III.2026", "2026-03-12"),
        ("Signed 07-XI-2025", "07-XI-2025", "2025-11-07"),
        ("Date: 5 IX 2024", "5 IX 2024", "2024-09-05"),
        ("Date: 12.II.2026", "12.II.2026", "2026-02-12"),  # "II" is February, not OCR noise for 11
        ("Date: 30.IV.2026", "30.IV.2026", "2026-04-30"),
    ],
)
def test_roman_numeral_months(text, raw, value):
    hit = one(text)
    assert (hit.raw_text, hit.normalized, hit.candidates) == (raw, value, (value,))
    assert "ocr_repaired" not in hit.review_reasons


def test_roman_month_must_be_upper_case():
    assert extract_dates("item 12 i 2026") == []


def test_roman_month_out_of_range_is_not_a_date():
    assert extract_dates("Ref 12.XIII.2026") == []


# --- Spaced and dotted numerics ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("Issued: 25 . 03 . 2026", "25 . 03 . 2026"),
        ("Issued: 25. 03. 2026", "25. 03. 2026"),
        ("Issued: 25 / 03 / 2026", "25 / 03 / 2026"),
        ("Issued: 2026 . 03 . 25", "2026 . 03 . 25"),
    ],
)
def test_spaced_numeric_dates(text, raw):
    hit = one(text)
    assert (hit.raw_text, hit.normalized) == (raw, "2026-03-25")


def test_spaced_numeric_date_keeps_both_readings_when_ambiguous():
    hit = one("Issued: 12 . 03 . 2026")
    assert hit.normalized is None
    assert hit.candidates == ("2026-03-12", "2026-12-03")
    assert "ambiguous_numeric_date" in hit.review_reasons


# --- Month abbreviations with OCR-noisy punctuation ---------------------------------------------


@pytest.mark.parametrize(
    ("text", "raw", "value"),
    [
        ("Date of issue: 25.Mar.2026", "25.Mar.2026", "2026-03-25"),
        ("Valid until 25-MAR-2026", "25-MAR-2026", "2026-03-25"),
        ("Expiry 25MAR2026", "25MAR2026", "2026-03-25"),
        ("Closed 07March2022", "07March2022", "2022-03-07"),
        ("Date of analysis: 4 Sep:2025", "4 Sep:2025", "2025-09-04"),
        ("Date of analysis: 4 Sept. 2025", "4 Sept. 2025", "2025-09-04"),
        ("Date of analysis: 4 Sep, 2025", "4 Sep, 2025", "2025-09-04"),
        ("Approved DEC 2 1999", "DEC 2 1999", "1999-12-02"),
    ],
)
def test_noisy_month_abbreviations(text, raw, value):
    hit = one(text)
    assert (hit.raw_text, hit.normalized) == (raw, value)


@pytest.mark.parametrize(
    ("text", "raw", "value"),
    [("EXP MAR 2027", "MAR 2027", "2027-03"), ("Accessed Feb 2026", "Feb 2026", "2026-02")],
)
def test_month_name_and_year_is_month_precision(text, raw, value):
    hit = one(text)
    assert (hit.raw_text, hit.normalized, hit.precision) == (raw, value, "month")


def test_month_word_inside_another_word_is_not_a_month():
    assert extract_dates("12 marching 2026 and decimal 2026") == []


# --- Label-adjacent forms on batch labels -----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "raw", "value", "label"),
    [
        ("EXP03/2027", "03/2027", "2027-03", "expiry"),
        ("EXP2022-06-25", "2022-06-25", "2022-06-25", "expiry"),
        ("MFG25MAR2026", "25MAR2026", "2026-03-25", "manufacture"),
        ("MFD:2026-03-25", "2026-03-25", "2026-03-25", "manufacture"),
        ("MFD 25.03.2026", "25.03.2026", "2026-03-25", "manufacture"),
        ("LOT12031EXP03/2027", "03/2027", "2027-03", "expiry"),
    ],
)
def test_label_adjacent_dates(text, raw, value, label):
    hit = one(text)
    assert (hit.raw_text, hit.normalized, hit.label) == (raw, value, label)


# --- OCR digit repair inside date-shaped tokens -----------------------------------------------


@pytest.mark.parametrize(
    ("text", "raw", "value"),
    [
        ("Expiry: 2O26-O3-1S", "2O26-O3-1S", "2026-03-15"),  # O -> 0, S -> 5
        ("Expiry: 1B/03/2026", "1B/03/2026", "2026-03-18"),  # B -> 8
        ("Expiry: l9.O3.2026", "l9.O3.2026", "2026-03-19"),  # l -> 1
        ("Expiry: 2I/03/2026", "2I/03/2026", "2026-03-21"),  # I -> 1
        ("Expiry: 1S Mar 2O26", "1S Mar 2O26", "2026-03-15"),
    ],
)
def test_ocr_digit_confusions_are_repaired_and_recorded(text, raw, value):
    hit = one(text)
    assert (hit.raw_text, hit.normalized) == (raw, value)
    assert "ocr_repaired" in hit.review_reasons


def test_ocr_repaired_is_recorded_only_on_the_repaired_date():
    clean, noisy = extract_dates("Expiry: 2O28-O8-21  Manufactured: 2026-08-21")
    assert "ocr_repaired" in clean.review_reasons
    assert "ocr_repaired" not in noisy.review_reasons


def test_word_repair_alone_is_not_an_ocr_repaired_date():
    hit = one("EXP1RY: 2028-08-21")
    assert hit.label == "expiry"
    assert "ocr_repaired" not in hit.review_reasons


@pytest.mark.parametrize("text", ["Ref S/B/2026", "Ref OI/IO/2026", "Code BOSS-2026"])
def test_letters_outside_date_shaped_tokens_are_not_repaired(text):
    assert extract_dates(text) == []


# --- Look-alikes that are not dates -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "LOT 12031",
        "Quality system certified to ISO 9001:2015",
        "Tel: +1 (212) 555-0147",
        "Fax: 020 7946 0958",
        "Assay 95.0 - 105.0 %   pH 6.8",
        "Batch size: 120 000 tablets",
        "Version 1.0 12.2026",
    ],
)
def test_look_alikes_are_not_dates(text):
    assert extract_dates(text) == []


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("Signed 12th March 2026", "12th March 2026"),
        ("Signed 12th of March 2026", "12th of March 2026"),
        ("Signed March 12th, 2026", "March 12th, 2026"),
    ],
)
def test_ordinal_days_keep_day_precision(text, raw):
    hit = one(text)
    assert (hit.raw_text, hit.normalized, hit.precision) == (raw, "2026-03-12", "day")


def test_spelled_out_day_before_month_is_not_read_as_month_only():
    assert extract_dates("on the twelfth day of March 2026") == []


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("dated 17Oct2022, was", "2022-10-17"),
        ("dated 27Sep2021.Reported", "2021-09-27"),
        ("on 01Aug2022", "2022-08-01"),
    ],
)
def test_month_name_letters_are_not_repaired_as_digits(text, value):
    assert one(text).normalized == value  # the "O" of Oct and the "S" of Sep stay letters


def test_compact_month_and_year_needs_a_separator():
    assert extract_dates("datedJ~Nov2020. reported") == []  # the day was lost to OCR noise


@pytest.mark.parametrize(
    ("text", "raw", "value"),
    [
        ("Seal 8.1V.2028", "8.1V.2028", "2028-04-08"),
        ("Seal 15.X11.2022", "15.X11.2022", "2022-12-15"),
        ("Seal 01-II|-2021", "01-II|-2021", "2021-03-01"),
        ("Seal 17 Ill 2023", "17 Ill 2023", "2023-03-17"),
        ("Seal 04-1X-2O25", "04-1X-2O25", "2025-09-04"),
    ],
)
def test_ocr_noise_in_roman_months_is_repaired_and_recorded(text, raw, value):
    hit = one(text)
    assert (hit.raw_text, hit.normalized) == (raw, value)
    assert "ocr_repaired" in hit.review_reasons


@pytest.mark.parametrize("text", ["Due 10-1-2022", "Due 10.11.2022"])
def test_digit_months_are_not_read_as_roman(text):
    hit = one(text)
    assert hit.candidates in (("2022-01-10", "2022-10-01"), ("2022-10-11", "2022-11-10"))


def test_a_lone_l_month_is_left_unread():
    assert extract_dates("Due 10.l.2022") == []  # roman I or digit 1: the page does not say


@pytest.mark.parametrize("text", ["Due 10.1l.2022", "Due 10.l1.2022", "Due 10-1I-2022"])
def test_two_character_l_months_read_as_digits_and_stay_ambiguous(text):
    # "1l" is far more often a misread 11 than a misread II; read as 11 it stays ambiguous.
    hit = one(text)
    assert hit.normalized is None
    assert hit.candidates == ("2022-10-11", "2022-11-10")
    assert {"ambiguous_numeric_date", "ocr_repaired"} <= set(hit.review_reasons)


@pytest.mark.parametrize(
    ("text", "raw", "value"),
    [("Signed 5.X.2024", "5.X.2024", "2024-10-05"), ("Signed 05-V-2024", "05-V-2024", "2024-05-05")],
)
def test_one_letter_roman_months_need_a_punctuated_separator(text, raw, value):
    hit = one(text)
    assert (hit.raw_text, hit.normalized) == (raw, value)


@pytest.mark.parametrize(
    "text",
    [
        "Pack: 10 X 1000 mL",  # pack size, not 10.X.1000
        "Pack 3 X 2000 TABLETS",  # "X" read as a multiplication sign
        "Rev 2 V 2020",
        "Patients may 1200 mg daily",
        "Dose of 5 mg may 1500 units",
        "Patients may 2000 mg daily",  # lower-case "may" is the verb
        "Pack 10/1000",
        "Ref 12.III.1500",
    ],
)
def test_quantities_and_implausible_years_are_not_dates(text):
    assert extract_dates(text) == []


def test_title_case_month_and_year_is_still_read():
    hit = one("Valid until May 2026")
    assert (hit.raw_text, hit.normalized, hit.precision) == ("May 2026", "2026-05", "month")
