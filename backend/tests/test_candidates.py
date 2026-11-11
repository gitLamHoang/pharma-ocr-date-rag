from pharma_dates.candidates import apply_document_order, page_candidates, transcription_candidates
from pharma_dates.models import BBox, LabeledDate, PageLayout, Word

CHAR_W, LINE_H = 10, 20


def make_layout(lines: list[str], n: int = 1, transcription: str | None = None) -> PageLayout:
    """A layout whose word boxes follow the character grid: x = column * 10, y = line * 20."""
    words, pos = [], 0
    for row, line in enumerate(lines):
        col = 0
        for text in line.split(" "):
            if text:
                box = BBox(
                    x0=col * CHAR_W, y0=row * LINE_H, x1=(col + len(text)) * CHAR_W, y1=row * LINE_H + 15
                )
                words.append(Word(text=text, bbox=box, char_start=pos + col, char_end=pos + col + len(text)))
            col += len(text) + 1
        pos += len(line) + 1
    return PageLayout(
        n=n,
        width=1000,
        height=1000,
        text="\n".join(lines),
        text_source="pdf",
        words=words,
        transcription=transcription,
    )


def labeled(cand, **overrides) -> LabeledDate:
    fields = {
        "date_type": "signature_date",
        "family": "signature",
        "qualifier": None,
        "resolved_value": None,
        "evidence": None,
        "confidence": 0.5,
        "rationale": None,
    }
    return LabeledDate(**cand.model_dump(), **(fields | overrides))


def test_finds_date_with_box():
    layout = make_layout(["Batch 42", "Expiry date: March 31, 2027 end"], n=3)
    [cand] = page_candidates(layout)
    assert cand.id == "p3-c1"
    assert cand.page == 3
    assert cand.raw_text == "March 31, 2027"
    assert layout.text[cand.char_start : cand.char_end] == "March 31, 2027"
    assert cand.normalized == "2027-03-31"
    assert cand.candidates == ["2027-03-31"]
    assert cand.precision == "day"
    assert cand.source == "rules"
    assert cand.rule_label == "expiry"
    # Union of the three words "March", "31," and "2027" on line 2.
    assert cand.bbox == BBox(x0=130, y0=20, x1=270, y1=35)
    assert cand.context == layout.text


def test_context_is_200_chars_each_side():
    filler = "x" * 300
    layout = make_layout([f"{filler} 31/03/2027 {filler}"])
    [cand] = page_candidates(layout)
    assert cand.context == f"{'x' * 199} 31/03/2027 {'x' * 199}"


def test_ambiguous_kept():
    [cand] = page_candidates(make_layout(["Signed 09/10/2026"]))
    assert cand.normalized is None
    assert cand.candidates == ["2026-09-10", "2026-10-09"]


def test_date_order_policy_applies():
    [cand] = page_candidates(make_layout(["Signed 09/10/2026"]), date_order="dmy")
    assert cand.normalized == "2026-10-09"


def test_month_only_precision():
    [cand] = page_candidates(make_layout(["EXP 03/2027"]))
    assert cand.normalized == "2027-03"
    assert cand.precision == "month"


def test_same_string_twice_two_candidates():
    layout = make_layout(["Reviewed by: A. Smith 12/03/2026", "Approved by: B. Jones 12/03/2026"])
    first, second = page_candidates(layout)
    assert first.raw_text == second.raw_text == "12/03/2026"
    assert first.id != second.id
    assert first.char_start != second.char_start
    assert first.bbox != second.bbox
    assert first.bbox.y0 == 0 and second.bbox.y0 == LINE_H


def test_blank_page_no_candidates():
    blank = PageLayout(n=1, width=1000, height=800, text="", text_source="ocr", words=[])
    assert page_candidates(blank) == []
    assert transcription_candidates(blank, []) == []
    assert page_candidates(make_layout(["Certificate of analysis", "Batch 42, lot 7"])) == []


def test_transcription_only_marked_ai_only():
    layout = make_layout(
        ["Expiry 31/03/2027", "Signed ...smudged..."],
        n=2,
        transcription="Expiry 31/03/2027\nSigned 14 March 2026",
    )
    existing = page_candidates(layout)
    assert [c.raw_text for c in existing] == ["31/03/2027"]
    [extra] = transcription_candidates(layout, existing)
    assert extra.raw_text == "14 March 2026"
    assert extra.normalized == "2026-03-14"
    assert extra.source == "ai_only"
    assert extra.bbox is None
    assert extra.page == 2
    assert extra.id.startswith("p2-") and extra.id not in {c.id for c in existing}
    assert layout.transcription[extra.char_start : extra.char_end] == "14 March 2026"


def test_transcription_without_text_layer_match_kept_even_if_value_matches():
    # Same value, different printed text: still not on the text layer, so it is AI-only.
    layout = make_layout(["Expiry 31/03/2027"], transcription="Expiry 2027-03-31")
    [extra] = transcription_candidates(layout, page_candidates(layout))
    assert extra.raw_text == "2027-03-31"


def test_no_transcription_no_extra_candidates():
    layout = make_layout(["Expiry 31/03/2027"])
    assert transcription_candidates(layout, page_candidates(layout)) == []


def test_document_order_suggests_resolved_value_only():
    page1 = page_candidates(make_layout(["Signed 09/10/2026"], n=1))
    page2 = page_candidates(make_layout(["Released 31/10/2026"], n=2))
    dates = [labeled(c) for c in page1 + page2]
    ambiguous, revealing = apply_document_order(dates)
    assert ambiguous.normalized is None
    assert ambiguous.candidates == ["2026-09-10", "2026-10-09"]
    assert ambiguous.resolved_value == "2026-10-09"
    assert '"31/10/2026"' in ambiguous.evidence
    assert revealing == dates[1]


def test_document_order_conflict_leaves_ambiguous():
    cands = page_candidates(make_layout(["Signed 09/10/2026", "Released 31/10/2026", "Checked 10/31/2026"]))
    ambiguous = apply_document_order([labeled(c) for c in cands])[0]
    assert ambiguous.resolved_value is None
    assert ambiguous.evidence is None


def test_document_order_keeps_existing_resolution():
    cands = page_candidates(make_layout(["Signed 09/10/2026", "Released 31/10/2026"]))
    dates = [
        labeled(cands[0], resolved_value="2026-09-10", evidence="Signed on 10 September"),
        labeled(cands[1]),
    ]
    assert apply_document_order(dates)[0].resolved_value == "2026-09-10"


def test_document_order_never_sets_normalized_on_plain_candidates():
    cands = page_candidates(make_layout(["Signed 09/10/2026", "Released 31/10/2026"]))
    assert apply_document_order(cands) == cands
