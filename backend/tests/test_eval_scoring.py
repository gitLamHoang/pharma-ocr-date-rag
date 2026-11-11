"""The evaluation scorer (`eval/run_eval.py`): matching, per-type counts and the two gates."""

import json

import pytest
import run_eval
from run_eval import GOLD_DIR, load_gold, load_sources, score

from pharma_dates.models import LabeledDate
from pharma_dates.taxonomy import family_of

PAGES = {1: "Date of issue: 12 March 2026\nExpiry: 03/2027\nSigned 09/10/2026", 2: "Approved 2026-01-05"}


def predicted(raw_text, date_type, normalized=None, *, page=1, candidates=None, resolved=None, evidence=None):
    return LabeledDate(
        id=f"p{page}-{raw_text}",
        page=page,
        raw_text=raw_text,
        normalized=normalized,
        candidates=candidates if candidates is not None else [normalized],
        precision="month" if normalized and len(normalized) == 7 else "day",
        char_start=0,
        char_end=len(raw_text),
        bbox=None,
        context="",
        rule_label="unknown",
        source="rules",
        date_type=date_type,
        family=family_of(date_type),
        qualifier=None,
        resolved_value=resolved,
        evidence=evidence,
        confidence=0.5,
        rationale=None,
    )


AMBIGUOUS = ["2026-09-10", "2026-10-09"]
GOLD = [
    {"page": 1, "raw_text": "12 March 2026", "date_type": "issue_date", "normalized": "2026-03-12"},
    {"page": 1, "raw_text": "03/2027", "date_type": "expiry_date", "normalized": "2027-03"},
    {"page": 1, "raw_text": "09/10/2026", "date_type": "signature_date", "candidates": AMBIGUOUS},
    {"page": 2, "raw_text": "2026-01-05", "date_type": "approval_date", "normalized": "2026-01-05"},
]


def perfect():
    return [
        predicted("12 March 2026", "issue_date", "2026-03-12"),
        predicted("03/2027", "expiry_date", "2027-03"),
        predicted("09/10/2026", "signature_date", candidates=AMBIGUOUS),
        predicted("2026-01-05", "approval_date", "2026-01-05", page=2),
    ]


def test_perfect_prediction_scores_one_everywhere():
    scores = score(perfect(), GOLD, PAGES)
    assert (scores.micro.precision, scores.micro.recall, scores.micro.f1) == (1.0, 1.0, 1.0)
    assert set(scores.per_type) == {"issue_date", "expiry_date", "signature_date", "approval_date"}
    assert all(prf.f1 == 1.0 for prf in scores.per_type.values())
    assert (scores.hallucinations, scores.silent_resolutions) == (0, 0)


def test_nothing_predicted_has_zero_recall_and_no_gate_failures():
    scores = score([], GOLD, PAGES)
    assert (scores.micro.tp, scores.micro.fp, scores.micro.fn) == (0, 0, 4)
    assert (scores.detected.tp, scores.detected.fn) == (0, 4)
    assert (scores.micro.precision, scores.micro.recall, scores.micro.f1) == (0.0, 0.0, 0.0)
    assert (scores.hallucinations, scores.silent_resolutions) == (0, 0)


def test_wrong_type_is_a_false_positive_for_one_type_and_a_miss_for_the_other():
    preds = perfect()
    preds[0] = predicted("12 March 2026", "effective_date", "2026-03-12")
    scores = score(preds, GOLD, PAGES)
    assert (scores.per_type["effective_date"].tp, scores.per_type["effective_date"].fp) == (0, 1)
    assert (scores.per_type["issue_date"].tp, scores.per_type["issue_date"].fn) == (0, 1)
    assert (scores.micro.tp, scores.micro.fp, scores.micro.fn) == (3, 1, 1)
    assert scores.micro.precision == pytest.approx(0.75)
    assert scores.hallucinations == 0  # found on the page, just mislabeled
    assert (scores.detected.tp, scores.detected.fp, scores.detected.fn) == (4, 0, 0)


def test_wrong_value_is_not_a_true_positive():
    preds = perfect()
    preds[0] = predicted("12 March 2026", "issue_date", "2026-12-03")
    scores = score(preds, GOLD, PAGES)
    assert (scores.per_type["issue_date"].tp, scores.per_type["issue_date"].fp) == (0, 1)
    assert scores.per_type["issue_date"].fn == 1


def test_unmatched_date_printed_on_the_page_is_a_false_positive_not_a_hallucination():
    preds = perfect() + [predicted("2026-01-05", "unknown", "2026-01-05", page=1)]  # not printed on p1
    preds += [predicted("12  march 2026", "unknown", "2026-03-12")]  # printed, but already matched
    scores = score(preds, GOLD, PAGES)
    assert scores.per_type["unknown"].fp == 2
    assert (scores.detected.tp, scores.detected.fp, scores.detected.fn) == (4, 2, 0)
    assert scores.hallucinations == 1


def test_hallucination_is_an_unmatched_date_whose_text_is_not_on_its_page():
    preds = perfect() + [predicted("01/01/2030", "expiry_date", "2030-01-01")]
    scores = score(preds, GOLD, PAGES)
    assert scores.hallucinations == 1
    assert scores.per_type["expiry_date"].fp == 1


def test_matching_ignores_case_and_spacing_and_pairs_duplicates_one_to_one():
    pages = {1: "Signed 12/03/2026 ... Signed 12/03/2026"}
    item = {"page": 1, "raw_text": "12/03/2026", "date_type": "signature_date", "candidates": ["x", "y"]}
    gold = [item, dict(item)]
    preds = [predicted(" 12/03/2026 ", "signature_date", candidates=["x", "y"]) for _ in range(3)]
    scores = score(preds, gold, pages)
    assert (scores.micro.tp, scores.micro.fp, scores.micro.fn) == (2, 1, 0)
    assert scores.hallucinations == 0


def test_same_text_on_another_page_does_not_match():
    gold = [{"page": 2, "raw_text": "2026-01-05", "date_type": "approval_date", "normalized": "2026-01-05"}]
    scores = score([predicted("2026-01-05", "approval_date", "2026-01-05", page=1)], gold, PAGES)
    assert (scores.micro.tp, scores.micro.fp, scores.micro.fn) == (0, 1, 1)
    assert scores.hallucinations == 1  # page 1 does not print it


def test_ambiguous_gold_resolved_without_evidence_is_a_silent_resolution():
    preds = perfect()
    preds[2] = predicted("09/10/2026", "signature_date", "2026-10-09", candidates=["2026-10-09"])
    scores = score(preds, GOLD, PAGES)
    assert scores.silent_resolutions == 1
    assert scores.per_type["signature_date"].tp == 0


def test_resolved_value_without_evidence_is_a_silent_resolution():
    preds = perfect()
    preds[2] = predicted("09/10/2026", "signature_date", candidates=AMBIGUOUS, resolved="2026-09-10")
    assert score(preds, GOLD, PAGES).silent_resolutions == 1


def test_ambiguous_gold_resolved_with_evidence_counts_when_the_reading_is_a_gold_candidate():
    preds = perfect()
    preds[2] = predicted(
        "09/10/2026", "signature_date", candidates=AMBIGUOUS, resolved="2026-09-10", evidence="DD/MM/YYYY"
    )
    scores = score(preds, GOLD, PAGES)
    assert scores.silent_resolutions == 0
    assert scores.per_type["signature_date"].tp == 1


def test_unambiguous_gold_is_never_a_silent_resolution():
    preds = perfect()
    preds[0] = predicted("12 March 2026", "issue_date", "2026-03-12")
    assert score(preds, GOLD, PAGES).silent_resolutions == 0


def test_matching_by_value_pairs_dates_whose_printed_text_differs():
    # OCR printed "12 . 03 . 2026"-style gold text differently; the synthetic set matches by value.
    preds = perfect()
    preds[0] = predicted("12  Mar 2026", "issue_date", "2026-03-12")
    preds[2] = predicted("09 /10 /2026", "signature_date", candidates=AMBIGUOUS)
    result = score(preds, GOLD, PAGES | {1: PAGES[1] + "\n12  Mar 2026 09 /10 /2026"}, by="value")
    assert (result.micro.tp, result.micro.fp, result.micro.fn) == (4, 0, 0)


def test_matching_by_value_needs_the_same_readings():
    preds = perfect()
    preds[2] = predicted("09/10/2026", "signature_date", "2026-09-10")  # one reading only
    result = score(preds, GOLD, PAGES, by="value")
    assert (result.detected.tp, result.detected.fp, result.detected.fn) == (3, 1, 1)


def test_text_matching_ignores_whitespace_inside_the_date():
    preds = perfect()
    preds[1] = predicted("03 /2027", "expiry_date", "2027-03")
    assert score(preds, GOLD, PAGES | {1: PAGES[1] + " 03 /2027"}).micro.tp == 4


def test_every_source_has_valid_gold_labels_and_a_pinned_hash():
    sources = load_sources()
    ids = [s["id"] for s in sources]
    assert len(ids) == len(set(ids))
    assert {p.stem for p in GOLD_DIR.glob("*.json")} == set(ids)
    for source in sources:
        assert len(source["sha256"]) == 64 and source["url"].startswith("https://") and source["licence"]
        load_gold(source["id"])  # raises on an unusable item


@pytest.mark.parametrize(
    ("item", "message"),
    [
        ({"page": 1, "raw_text": "x", "date_type": "best_before", "normalized": "2026-01-01"}, "taxonomy"),
        ({"page": 1, "raw_text": "x", "date_type": "issue_date"}, "exactly one"),
        ({"page": 1, "raw_text": "x", "date_type": "issue_date", "candidates": ["2026-01-02"]}, "two"),
        ({"page": 0, "raw_text": "x", "date_type": "issue_date", "normalized": "2026-01-01"}, "page"),
    ],
)
def test_load_gold_rejects_unusable_items(tmp_path, monkeypatch, item, message):
    (tmp_path / "doc.json").write_text(json.dumps([item]))
    monkeypatch.setattr(run_eval, "GOLD_DIR", tmp_path)
    with pytest.raises(ValueError, match=message):
        load_gold("doc")
