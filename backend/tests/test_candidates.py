from helpers import LINE_H, make_layout

from pharma_dates.candidates import apply_document_order, page_candidates, transcription_candidates
from pharma_dates.models import BBox, LabeledDate, PageLayout


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


def test_transcription_ocr_digit_noise_is_same_date():
    # Tesseract misreads digits as O/I/l; Claude transcribes the clean form of the same print.
    for page_line, transcription in [
        ("Expiry O1/03/2027", "Expiry 01/03/2027"),
        ("Exp 31/03/2O27", "Exp 31/03/2027"),
        ("Mfg 1l/O3/2026", "Mfg 11/03/2026"),
        ("Mfg I1/03/2026", "Mfg 11/03/2026"),
    ]:
        layout = make_layout([page_line], transcription=transcription)
        existing = page_candidates(layout)
        assert len(existing) == 1, page_line
        assert transcription_candidates(layout, existing) == [], page_line


def test_transcription_case_difference_is_same_date():
    layout = make_layout(["EXPIRY MARCH 31, 2027"], transcription="Expiry March 31, 2027")
    assert transcription_candidates(layout, page_candidates(layout)) == []


def test_transcription_dedupe_independent_of_date_order():
    layout = make_layout(["Signed 09/10/2026"], transcription="Signed 09/10/2026")
    existing = page_candidates(layout, date_order="dmy")
    assert existing[0].normalized == "2026-10-09"
    assert transcription_candidates(layout, existing) == []


def test_transcription_second_identical_signature_kept():
    # The text layer found one of two signature dates; the transcription has both.
    layout = make_layout(
        ["Reviewed by: A. Smith 12/03/2026", "Approved by: B. Jones ...smudged..."],
        transcription="Reviewed by: A. Smith 12/03/2026\nApproved by: B. Jones 12/03/2026",
    )
    existing = page_candidates(layout)
    assert len(existing) == 1
    [extra] = transcription_candidates(layout, existing)
    assert extra.raw_text == "12/03/2026"
    assert extra.source == "ai_only"
    assert layout.transcription.index("Approved") < extra.char_start


def test_date_printed_across_two_lines_gets_one_box_per_line():
    layout = make_layout(["The application received March 4,", "1999, submitted under section 505(b)"])
    [c] = page_candidates(layout)
    assert c.raw_text == "March 4,\n1999"
    first, second = c.line_boxes
    assert (first.y0, second.y0) == (0, 20)  # one tight box on each line
    assert (first.x0, first.x1) == (250, 330)
    assert (second.x0, second.x1) == (0, 50)
    assert c.bbox.y1 == second.y1  # the union box still spans both


def test_date_on_one_line_has_no_line_boxes():
    [c] = page_candidates(make_layout(["Expiry 31/03/2027"]))
    assert c.line_boxes == []
