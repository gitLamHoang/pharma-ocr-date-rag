import pytest
from pydantic import ValidationError

from pharma_dates.models import BBox, Candidate, Flag, LabeledDate, PageLayout, Word


def candidate(**overrides):
    fields = dict(
        id="p1-c1",
        page=1,
        raw_text="09/10/2026",
        normalized=None,
        candidates=["2026-10-09", "2026-09-10"],
        precision="day",
        char_start=8,
        char_end=18,
        bbox=BBox(x0=10, y0=20, x1=110, y1=40),
        context="Expiry: 09/10/2026",
        rule_label="expiry",
        source="rules",
    )
    return Candidate(**(fields | overrides))


def test_page_layout_holds_words_with_boxes_and_offsets():
    word = Word(text="2026-04-15", bbox=BBox(x0=1.5, y0=2, x1=30, y1=12), char_start=6, char_end=16)
    page = PageLayout(n=1, width=1654, height=2339, text="Date: 2026-04-15", text_source="pdf", words=[word])
    assert page.transcription is None
    assert page.text[word.char_start : word.char_end] == word.text
    assert page.words[0].bbox.x0 == 1.5


def test_page_layout_rejects_unknown_text_source():
    with pytest.raises(ValidationError):
        PageLayout(n=1, width=10, height=10, text="", text_source="claude", words=[])


def test_candidate_keeps_ambiguity_and_allows_missing_box():
    ai_only = candidate(source="ai_only", bbox=None)
    assert ai_only.bbox is None
    assert ai_only.normalized is None and len(ai_only.candidates) == 2


@pytest.mark.parametrize("field, value", [("source", "ai"), ("precision", "year")])
def test_candidate_rejects_values_outside_the_contract(field, value):
    with pytest.raises(ValidationError):
        candidate(**{field: value})


def test_labeled_date_extends_candidate():
    base = candidate()
    labeled = LabeledDate(
        **base.model_dump(),
        date_type="expiry_date",
        family="product",
        qualifier=None,
        resolved_value="2026-10-09",
        evidence="dates on this page are written DD/MM/YYYY",
        confidence=0.8,
        rationale=None,
    )
    assert isinstance(labeled, Candidate)
    assert labeled.raw_text == base.raw_text
    assert labeled.model_dump()["bbox"] == {"x0": 10, "y0": 20, "x1": 110, "y1": 40}


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_labeled_date_confidence_is_a_probability(confidence):
    with pytest.raises(ValidationError):
        LabeledDate(
            **candidate().model_dump(),
            date_type="expiry_date",
            family="product",
            qualifier=None,
            resolved_value=None,
            evidence=None,
            confidence=confidence,
            rationale=None,
        )


def test_flag_severity_is_constrained():
    flag = Flag(rule="expiry_before_manufacture", severity="error", message="m", date_ids=["a", "b"])
    assert flag.date_ids == ["a", "b"]
    with pytest.raises(ValidationError):
        Flag(rule="r", severity="fatal", message="m", date_ids=[])
