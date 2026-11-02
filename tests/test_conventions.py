from pathlib import Path

import pytest

from pharma_ocr_date_rag.conventions import (
    CONFLICT_REASON,
    EVIDENCE_REASON,
    apply_document_order,
    hit_order,
    infer_order,
    interpret,
    leave_one_out,
    order_vote,
)
from pharma_ocr_date_rag.dates import extract_dates

MIXED = Path(__file__).resolve().parents[1] / "data/mixed_conventions"


@pytest.mark.parametrize(
    ("raw", "vote"),
    [
        ("31/10/2026", "dmy"),
        ("10/31/2026", "mdy"),
        ("29/02/2024", "dmy"),
        ("02/29/2024", "mdy"),
        ("09/10/2026", None),
        ("10/10/2026", None),
        ("31/02/2026", None),
        ("12/2028", None),
        ("2026-10-31", None),
        ("31 October 2026", None),
    ],
)
def test_only_dates_valid_in_exactly_one_order_vote(raw, vote):
    assert order_vote(raw) == vote


def test_interpret_respects_order_and_calendar():
    assert interpret("09/10/2026", "dmy") == "2026-10-09"
    assert interpret("09/10/2026", "mdy") == "2026-09-10"
    assert interpret("31/02/2026", "dmy") is None
    assert interpret("09/10/2026", "auto") is None


def test_unanimous_conflicting_and_missing_evidence():
    assert infer_order([("a", "31/10/2026"), ("b", "13/01/2027")]).order == "dmy"
    conflict = infer_order([("a", "31/10/2026"), ("b", "10/31/2026")])
    assert (conflict.status, conflict.order) == ("conflict", None)
    assert conflict.dmy_evidence == ("a",) and conflict.mdy_evidence == ("b",)
    assert infer_order([("a", "09/10/2026")]).status == "no_evidence"


@pytest.mark.parametrize(
    ("name", "expiry", "manufacture"),
    [("eu_receipt.txt", "2026-10-09", "2025-01-12"), ("us_receipt.txt", "2026-09-10", "2025-01-12")],
)
def test_declared_fixture_conventions_are_recovered_from_document_evidence(name, expiry, manufacture):
    hits = extract_dates((MIXED / name).read_text(encoding="utf-8"), language="en")
    assert sum(hit.normalized is None for hit in hits) == 2
    resolved = {hit.label: hit for hit in apply_document_order(hits)}
    assert resolved["expiry"].normalized == expiry
    assert resolved["manufacture"].normalized == manufacture
    assert EVIDENCE_REASON in resolved["expiry"].review_reasons
    assert "ambiguous_numeric_date" not in resolved["expiry"].review_reasons
    # Both readings stay visible so a reviewer can still reject the suggestion.
    assert len(resolved["expiry"].candidates) == 2


def test_document_without_revealing_dates_stays_unresolved():
    hits = extract_dates((MIXED / "unconfirmed_receipt.txt").read_text(encoding="utf-8"), language="en")
    assert hit_order(hits).status == "no_evidence"
    assert apply_document_order(hits) == hits


def test_conflicting_document_keeps_ambiguity_and_says_why():
    hits = extract_dates("Expiry: 09/10/2026\nMfg: 31/01/2025\nQC: 01/31/2025", language="en")
    expiry = apply_document_order(hits)[0]
    assert expiry.normalized is None
    assert {"ambiguous_numeric_date", CONFLICT_REASON} <= set(expiry.review_reasons)


def test_explicit_policy_hits_are_not_changed():
    hits = extract_dates("Expiry: 09/10/2026\nMfg: 10/31/2025", language="en", date_order="dmy")
    assert apply_document_order(hits) == hits


def test_ocr_damaged_ambiguous_date_is_not_reinterpreted():
    hits = extract_dates("Expiry: O9/10/2026\nMfg: 31/01/2025", language="en")
    expiry = apply_document_order(hits)[0]
    assert expiry.normalized is None


def test_leave_one_out_counts_agreement_disagreement_and_abstention():
    result = leave_one_out(
        [
            [("a", "31/10/2026"), ("b", "13/01/2027"), ("c", "09/10/2026")],
            [("d", "31/10/2026"), ("e", "10/31/2026")],
            [("f", "31/10/2026")],
        ]
    )
    assert result == {"agree": 2, "disagree": 2, "abstain": 1, "total": 5}
