import subprocess
import sys
from datetime import date

import pytest

from pharma_dates.models import LabeledDate
from pharma_dates.taxonomy import family_of
from pharma_dates.validate import effective_value, validate

TODAY = date(2026, 11, 11)


def dated(id_, date_type, normalized=None, *, raw_text=None, candidates=None, resolved_value=None, **fields):
    """A labeled date. A 7-character value (`YYYY-MM`) has month precision."""
    value = normalized or resolved_value
    readings = candidates if candidates is not None else [normalized] if normalized else []
    defaults = {
        "page": 1,
        "char_start": 0,
        "char_end": 10,
        "bbox": None,
        "context": "",
        "rule_label": "unknown",
        "source": "rules+ai",
        "qualifier": None,
        "evidence": "quoted from the page" if resolved_value else None,
        "confidence": 0.9,
        "rationale": None,
    }
    return LabeledDate(
        id=id_,
        raw_text=raw_text or value or "?",
        normalized=normalized,
        candidates=readings,
        precision="month" if value and len(value) == 7 else "day",
        date_type=date_type,
        family=family_of(date_type),
        resolved_value=resolved_value,
        **(defaults | fields),
    )


def ambiguous(id_, raw_text, date_type="issue_date", resolved_value=None):
    first, second, year = raw_text.split("/")
    readings = sorted({f"{year}-{second}-{first}", f"{year}-{first}-{second}"})
    return dated(id_, date_type, raw_text=raw_text, candidates=readings, resolved_value=resolved_value)


def rules_of(flags):
    return [f.rule for f in flags]


def test_no_dates_no_flags():
    assert validate([], TODAY) == []


def test_consistent_document_has_no_flags():
    dates = [
        dated("mfg", "manufacture_date", "2026-01-15"),
        dated("exp", "expiry_date", "2028-01"),
        dated("ret", "retest_date", "2027-01-15"),
        dated("sig", "signature_date", "2026-02-01", qualifier="J. Smith, approver"),
        dated("eff", "effective_date", "2026-02-01"),
        dated("cert", "certificate_valid_until", "2027-06-30"),
        dated("insp", "inspection_date", "2026-11-11"),
    ]
    assert validate(dates, TODAY) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (dated("a", "issue_date", "2026-03-15"), date(2026, 3, 15)),
        (dated("a", "expiry_date", "2027-03"), date(2027, 3, 31)),
        (dated("a", "expiry_date", "2028-02"), date(2028, 2, 29)),
        (ambiguous("a", "03/04/2026"), None),
        (ambiguous("a", "03/04/2026", resolved_value="2026-04-03"), date(2026, 4, 3)),
    ],
)
def test_effective_value(value, expected):
    assert effective_value(value) == expected


@pytest.mark.parametrize("expiry", ["2026-05-01", "2026-04-30"])
def test_expiry_before_manufacture(expiry):
    mfg = dated("mfg", "manufacture_date", "2026-05-01")
    exp = dated("exp", "expiry_date", expiry)
    [flag] = validate([mfg, exp], TODAY)
    assert (flag.rule, flag.severity, flag.date_ids) == ("expiry_before_manufacture", "error", ["mfg", "exp"])
    assert expiry in flag.message and "2026-05-01" in flag.message


def test_month_precision_compares_end_of_month():
    mfg = dated("mfg", "manufacture_date", "2027-03-15")
    exp = dated("exp", "expiry_date", "2027-03")
    assert validate([mfg, exp], date(2027, 6, 1)) == []


def test_month_precision_flag_says_month_precision():
    mfg = dated("mfg", "manufacture_date", "2026-04-02")
    exp = dated("exp", "expiry_date", "2026-03")
    [flag] = validate([mfg, exp], TODAY)
    assert flag.rule == "expiry_before_manufacture"
    assert "month precision" in flag.message


def test_retest_before_manufacture():
    mfg = dated("mfg", "manufacture_date", "2026-05-01")
    ret = dated("ret", "retest_date", "2026-04-01")
    [flag] = validate([mfg, ret], TODAY)
    assert (flag.rule, flag.severity, flag.date_ids) == ("retest_before_manufacture", "error", ["mfg", "ret"])


def test_ambiguous_dates_are_not_compared():
    mfg = dated("mfg", "manufacture_date", "2026-05-01")
    exp = ambiguous("exp", "03/04/2026", date_type="expiry_date")
    assert rules_of(validate([mfg, exp], TODAY)) == ["ambiguous_unresolved"]


@pytest.mark.parametrize("doc_type", ["effective_date", "issue_date"])
def test_signature_before_effective(doc_type):
    sig = dated("sig", "signature_date", "2026-01-10", qualifier="Head of QA (approval)")
    doc = dated("doc", doc_type, "2026-02-01")
    [flag] = validate([sig, doc], TODAY)
    assert (flag.rule, flag.severity, flag.date_ids) == (
        "signature_before_effective",
        "warning",
        ["sig", "doc"],
    )


@pytest.mark.parametrize(
    ("qualifier", "signed"),
    [
        ("J. Smith, author", "2026-01-10"),  # not an approval
        (None, "2026-01-10"),  # meaning unknown (offline label)
        ("approved by J. Smith", "2026-02-01"),  # same day is fine
    ],
)
def test_signature_before_effective_needs_an_earlier_approval(qualifier, signed):
    sig = dated("sig", "signature_date", signed, qualifier=qualifier)
    eff = dated("eff", "effective_date", "2026-02-01")
    assert validate([sig, eff], TODAY) == []


def test_legalization_chain_order():
    chain = [
        dated("issue", "certificate_issue_date", "2026-03-01"),
        dated("notary", "notarization_date", "2026-02-20"),
        dated("apostille", "apostille_date", "2026-03-05"),
        dated("translation", "translation_certification_date", "2026-03-04"),
    ]
    flags = validate(chain, TODAY)
    assert {(f.rule, f.severity) for f in flags} == {("legalization_chain_order", "error")}
    assert [f.date_ids for f in flags] == [["issue", "notary"], ["apostille", "translation"]]


def test_legalization_chain_in_order_allows_same_day():
    chain = [
        dated("issue", "certificate_issue_date", "2026-03-01"),
        dated("notary", "notarization_date", "2026-03-01"),
        dated("apostille", "apostille_date", "2026-03-05"),
        dated("legal", "legalization_date", "2026-03-02"),  # same stage as the apostille: not compared
        dated("translation", "translation_certification_date", "2026-03-06"),
    ]
    assert validate(chain, TODAY) == []


def test_certificate_expired():
    cert = dated("cert", "certificate_valid_until", "2026-11-10")
    [flag] = validate([cert], TODAY)
    assert (flag.rule, flag.severity, flag.date_ids) == ("certificate_expired", "error", ["cert"])
    assert "2026-11-11" in flag.message


@pytest.mark.parametrize("valid_until", ["2026-11-11", "2026-11", "2027-01-01"])
def test_certificate_still_valid(valid_until):
    assert validate([dated("cert", "certificate_valid_until", valid_until)], TODAY) == []


def test_certificate_expired_uses_the_reference_date():
    cert = dated("cert", "certificate_valid_until", "2026-11-10")
    assert validate([cert], date(2026, 1, 1)) == []


@pytest.mark.parametrize("date_type", ["signature_date", "manufacture_date", "inspection_date", "audit_date"])
def test_future_past_date(date_type):
    [flag] = validate([dated("d", date_type, "2026-11-12")], TODAY)
    assert (flag.rule, flag.severity, flag.date_ids) == ("future_past_date", "warning", ["d"])


@pytest.mark.parametrize(
    ("date_type", "value"),
    [
        ("expiry_date", "2027-01-01"),  # meant to be in the future
        ("next_audit_date", "2027-01-01"),
        ("manufacture_date", "2026-11-11"),  # today is not the future
        ("manufacture_date", "2026-11"),  # this month: not after today
    ],
)
def test_future_past_date_not_flagged(date_type, value):
    assert validate([dated("d", date_type, value)], TODAY) == []


def test_future_past_date_month_precision_next_month():
    [flag] = validate([dated("d", "manufacture_date", "2026-12")], TODAY)
    assert flag.rule == "future_past_date"
    assert "month precision" in flag.message


def test_ambiguous_unresolved():
    [flag] = validate([ambiguous("amb", "03/04/2026")], TODAY)
    assert (flag.rule, flag.severity, flag.date_ids) == ("ambiguous_unresolved", "info", ["amb"])
    assert "2026-03-04" in flag.message and "2026-04-03" in flag.message


def test_resolved_ambiguous_date_is_not_flagged():
    assert validate([ambiguous("amb", "03/04/2026", resolved_value="2026-04-03")], TODAY) == []


def test_ai_rules_disagree():
    # 31/01/2026 is only valid day-first, so the rules read 03/04/2026 as 3 April; the AI said 4 March.
    proof = dated("proof", "issue_date", "2026-01-31", raw_text="31/01/2026")
    amb = ambiguous("amb", "03/04/2026", resolved_value="2026-03-04")
    [flag] = validate([proof, amb], TODAY)
    assert (flag.rule, flag.severity, flag.date_ids) == ("ai_rules_disagree", "warning", ["amb", "proof"])
    assert "2026-03-04" in flag.message and "2026-04-03" in flag.message


@pytest.mark.parametrize(
    "others",
    [
        [dated("proof", "issue_date", "2026-01-31", raw_text="31/01/2026")],  # agrees with the AI
        [],  # no order evidence
        [  # conflicting evidence
            dated("dmy", "issue_date", "2026-01-31", raw_text="31/01/2026"),
            dated("mdy", "issue_date", "2026-01-31", raw_text="01/31/2026"),
        ],
    ],
)
def test_ai_rules_agree_or_rules_abstain(others):
    amb = ambiguous("amb", "03/04/2026", resolved_value="2026-04-03")
    assert validate([*others, amb], TODAY) == []


def test_validate_imports_only_pure_modules():
    # The static build runs validate.py in Pyodide.
    code = (
        "import sys, pharma_dates.validate; "
        "heavy = {'anthropic', 'rapidfuzz', 'fastapi', 'pdfplumber', 'pypdfium2', 'pytesseract', 'PIL'}; "
        "print(sorted(heavy & set(sys.modules)))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
