import json
import logging
import subprocess
import sys

import pytest
from helpers import make_layout

from pharma_dates.candidates import page_candidates, transcription_candidates
from pharma_dates.classify import (
    CandidateLabel,
    ClaudeUnavailable,
    MissedDate,
    PageClassification,
    label_page,
    loose_parse,
)
from pharma_dates.models import BBox
from pharma_dates.taxonomy import offline_label


class FakeClient:
    """Stands in for ClaudeClient: returns a canned classification or raises."""

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def classify(self, image_png, page_text, candidates, taxonomy_json):
        self.calls.append((image_png, page_text, [c.id for c in candidates], taxonomy_json))
        if self.error is not None:
            raise self.error
        return self.result


def label(candidate_id, date_type, **fields):
    defaults = {
        "qualifier": None,
        "resolved_value": None,
        "evidence": None,
        "confidence": 0.9,
        "rationale": "next to the field name",
    }
    return CandidateLabel(candidate_id=candidate_id, date_type=date_type, **(defaults | fields))


def missed(verbatim_text, date_type="legalization_date", **fields):
    defaults = {"qualifier": None, "confidence": 0.8, "rationale": "seen on the stamp"}
    return MissedDate(verbatim_text=verbatim_text, date_type=date_type, **(defaults | fields))


def classified(items=(), missed_dates=()):
    return PageClassification(items=list(items), missed_dates=list(missed_dates))


def test_labels_applied():
    layout = make_layout(["Signed by J. Smith (QA approval) on 14 March 2026", "Expiry 31/03/2027"])
    cands = page_candidates(layout)
    sig, exp = cands
    client = FakeClient(
        classified(
            [
                label(sig.id, "signature_date", qualifier="J. Smith - QA approval", confidence=0.95),
                label(exp.id, "expiry_date"),
            ]
        )
    )
    dates, discarded = label_page(layout, cands, client, image_png=b"png")
    assert discarded == []
    by_id = {d.id: d for d in dates}
    assert by_id[sig.id].date_type == "signature_date"
    assert by_id[sig.id].family == "signature"
    assert by_id[sig.id].qualifier == "J. Smith - QA approval"
    assert by_id[sig.id].confidence == 0.95
    assert by_id[sig.id].rationale == "next to the field name"
    assert by_id[sig.id].source == "rules+ai"
    assert by_id[sig.id].bbox == sig.bbox
    assert by_id[exp.id].date_type == "expiry_date"
    assert by_id[exp.id].family == "product"
    [(image, page_text, ids, taxonomy_json)] = client.calls
    assert image == b"png"
    assert page_text == layout.text
    assert ids == [sig.id, exp.id]
    assert {family["family"] for family in taxonomy_json} >= {"product", "signature"}


def test_ambiguous_resolved_only_with_evidence():
    layout = make_layout(["Issued 03/04/2026", "Approved 05/06/2026", "All dates are DD/MM/YYYY"])
    issued, approved = page_candidates(layout)
    assert issued.normalized is None and approved.normalized is None
    client = FakeClient(
        classified(
            [
                label(
                    issued.id,
                    "issue_date",
                    resolved_value="2026-04-03",
                    evidence='"All dates are DD/MM/YYYY"',
                ),
                label(approved.id, "approval_date", resolved_value="2026-06-05", evidence="  "),
            ]
        )
    )
    dates, discarded = label_page(layout, [issued, approved], client)
    by_id = {d.id: d for d in dates}
    assert by_id[issued.id].resolved_value == "2026-04-03"
    assert by_id[issued.id].evidence == '"All dates are DD/MM/YYYY"'
    assert by_id[issued.id].normalized is None
    assert by_id[approved.id].resolved_value is None
    assert by_id[approved.id].evidence is None
    assert by_id[approved.id].date_type == "approval_date"
    assert [d["candidate_id"] for d in discarded] == [approved.id]
    assert "evidence" in discarded[0]["reason"]


def test_resolved_value_not_in_candidates_rejected():
    layout = make_layout(["Issued 03/04/2026"])
    [issued] = page_candidates(layout)
    client = FakeClient(
        classified([label(issued.id, "issue_date", resolved_value="2026-04-30", evidence="a quote")])
    )
    [date], discarded = label_page(layout, [issued], client)
    assert date.resolved_value is None
    assert date.evidence is None
    assert date.date_type == "issue_date"
    assert date.candidates == ["2026-03-04", "2026-04-03"]
    assert discarded[0]["kind"] == "resolution"
    assert discarded[0]["page"] == 1


def test_resolution_ignored_on_unambiguous_date():
    layout = make_layout(["Expiry 31/03/2027"])
    [exp] = page_candidates(layout)
    client = FakeClient(classified([label(exp.id, "expiry_date", resolved_value="2027-03-31", evidence="x")]))
    [date], discarded = label_page(layout, [exp], client)
    assert date.normalized == "2027-03-31"
    assert date.resolved_value is None
    assert discarded == []


def test_ai_only_verified_against_page_text():
    layout = make_layout(["Legalized by the Ministry of Foreign Affairs", "Seal dated 2026.III.12 Riga"])
    cands = page_candidates(layout)
    assert cands == []
    client = FakeClient(
        classified(missed_dates=[missed("2026.III.12", qualifier="Ministry of Foreign Affairs")])
    )
    [date], discarded = label_page(layout, cands, client)
    assert discarded == []
    assert date.source == "ai_only"
    assert date.raw_text == "2026.III.12"
    assert date.normalized == "2026-03-12"
    assert date.candidates == ["2026-03-12"]
    assert date.precision == "day"
    assert date.date_type == "legalization_date"
    assert date.family == "legal"
    assert date.qualifier == "Ministry of Foreign Affairs"
    assert layout.text[date.char_start : date.char_end] == "2026.III.12"
    # The word "2026.III.12" (year first: the rules parser reads only day-first roman dates) sits on line 2 from column 11.
    assert date.bbox == BBox(x0=110, y0=20, x1=220, y1=35)
    assert date.id == "p1-a1"


def test_ai_only_not_on_page_discarded(caplog):
    layout = make_layout(["Certificate of analysis", "Released 14 March 2026"])
    cands = page_candidates(layout)
    client = FakeClient(
        classified([label(cands[0].id, "release_date")], missed_dates=[missed("01/01/2030", "expiry_date")])
    )
    with caplog.at_level(logging.INFO, logger="pharma_dates.classify"):
        dates, discarded = label_page(layout, cands, client)
    assert [d.raw_text for d in dates] == ["14 March 2026"]
    assert [(d["kind"], d["verbatim_text"], d["page"]) for d in discarded] == [
        ("missed_date", "01/01/2030", 1)
    ]
    assert "not found" in discarded[0]["reason"]
    assert "01/01/2030" not in caplog.text  # logs never carry document text


def test_ai_only_near_miss_digits_discarded():
    # "12.III.2026" scores 91 against the printed "12.III.2020" but is a different date.
    layout = make_layout(["Seal dated 12.III.2020"])
    client = FakeClient(classified(missed_dates=[missed("12.III.2026")]))
    dates, discarded = label_page(layout, [], client)
    assert dates == []
    assert discarded[0]["verbatim_text"] == "12.III.2026"
    assert "not found" in discarded[0]["reason"]


@pytest.mark.parametrize(
    ("printed", "verbatim"),
    [
        ("Seal dated 12.II.2026", "12.III.2026"),
        ("Seal dated 12.IV.2026", "12.VI.2026"),
        ("Seal dated 12.XI.2026", "12.XII.2026"),
        ("Signed 14 Jun 2026", "14 Jan 2026"),
        ("Valid until III.2027", "II.2027"),
        (
            "Given on the twelfth day of March, two thousand twenty-six",
            "the eleventh day of March, two thousand twenty-six",
        ),
    ],
)
def test_ai_only_near_miss_month_or_day_discarded(printed, verbatim):
    # Close enough for partial_ratio >= 85 and no digit differs, but the page prints another date.
    layout = make_layout([printed])
    client = FakeClient(classified(missed_dates=[missed(verbatim)]))
    dates, discarded = label_page(layout, [], client)
    assert dates == []
    assert [(d["verbatim_text"], d["reason"]) for d in discarded] == [
        (verbatim, "printed text reads as a different date")
    ]


def test_ai_only_near_miss_of_rule_candidate_discarded():
    layout = make_layout(["Signed 14 Jun 2026"])
    cands = page_candidates(layout)
    client = FakeClient(classified(missed_dates=[missed("14 Jan 2026")]))
    dates, discarded = label_page(layout, cands, client)
    assert [d.id for d in dates] == [cands[0].id]
    assert discarded[0]["reason"] == "printed text reads as a different date"


@pytest.mark.parametrize(
    ("printed", "verbatim", "token"),
    [
        ("Seal dated 12.III.2O26 Riga", "12.III.2026", "12.III.2O26"),
        ("Seal dated l2.III.2026 Riga", "12.III.2026", "l2.III.2026"),
        ("Released 12 March 2O26 by QA", "12 March 2026", "12 March 2O26"),
        (
            "Given on the twelfth day of March, two thousand twenty-six at Riga",
            "the twelfth day of March, two thousand twenty-six",
            "the twelfth day of March, two thousand twenty-six",
        ),
    ],
)
def test_ai_only_kept_despite_ocr_noise(printed, verbatim, token):
    layout = make_layout([printed])
    client = FakeClient(classified(missed_dates=[missed(verbatim)]))
    [date], discarded = label_page(layout, [], client)
    assert discarded == []
    assert date.normalized == "2026-03-12"
    assert layout.text[date.char_start : date.char_end] == token


@pytest.mark.parametrize(
    ("printed", "verbatim", "token", "normalized"),
    [
        ("Expiry:III.2027", "III.2027", "III.2027", "2027-03"),
        ("Date:12.III.2026", "12.III.2026", "12.III.2026", "2026-03-12"),
        ("Ref=12.III.2026", "12.III.2026", "12.III.2026", "2026-03-12"),
        ("Sealed 12.III.2026/Riga", "12.III.2026", "12.III.2026", "2026-03-12"),
    ],
)
def test_ai_only_kept_next_to_label_punctuation(printed, verbatim, token, normalized):
    # The rules parser misses these roman-month forms; the label or place name glued to the
    # date must not be read as part of it.
    layout = make_layout([printed])
    client = FakeClient(classified(missed_dates=[missed(verbatim)]))
    [date], discarded = label_page(layout, [], client)
    assert discarded == []
    assert date.normalized == normalized
    assert layout.text[date.char_start : date.char_end] == token


@pytest.mark.parametrize(
    ("printed", "verbatim"),
    [("Expiry:III.2027", "II.2027"), ("Due 12/03/2026", "03/2026")],
)
def test_ai_only_part_of_a_printed_date_still_discarded(printed, verbatim):
    layout = make_layout([printed])
    client = FakeClient(classified(missed_dates=[missed(verbatim)]))
    dates, discarded = label_page(layout, page_candidates(layout), client)
    assert all(d.source != "ai_only" for d in dates)
    assert [d["verbatim_text"] for d in discarded] == [verbatim]


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (
            "Issued 03/04/2026 and the footer says all dates are DD/MM/YYYY so April",
            "evidence not found on the page",
        ),
        ("03/04/2026", "evidence only repeats the date"),
        ('"03/04/2026."', "evidence only repeats the date"),
    ],
)
def test_ambiguous_resolution_evidence_longer_than_page_or_only_the_date(evidence, reason):
    layout = make_layout(["Issued 03/04/2026"])
    [issued] = page_candidates(layout)
    client = FakeClient(
        classified([label(issued.id, "issue_date", resolved_value="2026-04-03", evidence=evidence)])
    )
    [date], discarded = label_page(layout, [issued], client)
    assert date.resolved_value is None and date.evidence is None
    assert [(d["kind"], d["reason"]) for d in discarded] == [("resolution", reason)]


def test_ambiguous_resolution_evidence_must_be_on_page():
    layout = make_layout(["Issued 03/04/2026"])
    [issued] = page_candidates(layout)
    client = FakeClient(
        classified([label(issued.id, "issue_date", resolved_value="2026-04-03", evidence="3 April 2026")])
    )
    [date], discarded = label_page(layout, [issued], client)
    assert date.resolved_value is None and date.evidence is None
    assert [(d["kind"], d["reason"]) for d in discarded] == [("resolution", "evidence not found on the page")]


def test_ai_only_unparseable_text_discarded():
    layout = make_layout(["Signed soon"])
    client = FakeClient(classified(missed_dates=[missed("soon", "signature_date")]))
    dates, discarded = label_page(layout, [], client)
    assert dates == []
    assert "parse" in discarded[0]["reason"]


def test_missed_date_already_a_candidate_not_duplicated():
    layout = make_layout(["Signed 14 March 2026"])
    cands = page_candidates(layout)
    client = FakeClient(classified([label(cands[0].id, "signature_date")], [missed("14 March 2026")]))
    dates, discarded = label_page(layout, cands, client)
    assert [d.id for d in dates] == [cands[0].id]
    assert discarded[0]["reason"].startswith("duplicate")


def test_same_missed_date_printed_twice_kept_twice():
    layout = make_layout(["Seal 12.III.2026", "Stamp 12.III.2026"])
    client = FakeClient(classified(missed_dates=[missed("12.III.2026"), missed("12.III.2026")]))
    dates, discarded = label_page(layout, [], client)
    assert discarded == []
    assert [d.bbox.y0 for d in dates] == [0, 20]
    assert [d.id for d in dates] == ["p1-a1", "p1-a2"]


def test_transcription_candidate_verified_and_located():
    # OCR misread a digit in a month-first date, where the rules do not repair digits;
    # Claude's transcription has the printed form.
    layout = make_layout(["Expiry 31/03/2027", "Signed Mar 14, 2O26"], transcription="Signed Mar 14, 2026")
    rules = page_candidates(layout)
    extra = transcription_candidates(layout, rules)
    cands = rules + extra
    client = FakeClient(classified([label(c.id, "signature_date") for c in extra]))
    dates, discarded = label_page(layout, cands, client)
    assert discarded == []
    by_id = {d.id: d for d in dates}
    [t] = extra
    assert by_id[t.id].source == "ai_only"
    assert by_id[t.id].date_type == "signature_date"
    assert layout.text[by_id[t.id].char_start : by_id[t.id].char_end] == "Mar 14, 2O26"
    assert by_id[t.id].bbox is not None
    assert by_id[rules[0].id].source == "rules"  # not labeled by Claude: rule label kept


def test_transcription_candidate_not_on_page_discarded_even_offline():
    layout = make_layout(["Expiry 31/03/2027"], transcription="Expiry 31/03/2027\nSigned 14 March 2026")
    rules = page_candidates(layout)
    cands = rules + transcription_candidates(layout, rules)
    dates, discarded = label_page(layout, cands, None)
    assert [d.raw_text for d in dates] == ["31/03/2027"]
    assert [(d["kind"], d["verbatim_text"]) for d in discarded] == [("transcription", "14 March 2026")]


def test_unknown_id_and_bad_type_ignored(caplog):
    layout = make_layout(["Approved 14 March 2026", "Expiry 31/03/2027"])
    approved, exp = page_candidates(layout)
    client = FakeClient(
        classified(
            [
                label("p9-c99", "expiry_date"),
                label(approved.id, "birthday"),
                label(exp.id, "expiry_date"),
            ],
            [missed("31.III.2027", "made_up_type")],
        )
    )
    with caplog.at_level(logging.INFO, logger="pharma_dates.classify"):
        dates, discarded = label_page(layout, [approved, exp], client)
    by_id = {d.id: d for d in dates}
    assert set(by_id) == {approved.id, exp.id}
    # The bad label is ignored: the rule label is kept for that candidate.
    assert by_id[approved.id].date_type == offline_label(
        approved.rule_label, layout.text, approved.char_start, approved.char_end
    )
    assert by_id[approved.id].source == "rules"
    assert by_id[approved.id].confidence == 0.5
    assert by_id[exp.id].date_type == "expiry_date"
    assert by_id[exp.id].source == "rules+ai"
    assert sorted(d["reason"].split(":")[0] for d in discarded) == [
        "date type not in taxonomy",
        "date type not in taxonomy",
        "unknown candidate id",
    ]
    assert "unknown candidate id" in caplog.text
    assert "not in taxonomy" in caplog.text


def test_duplicate_label_for_same_candidate_first_wins():
    layout = make_layout(["Expiry 31/03/2027"])
    [exp] = page_candidates(layout)
    client = FakeClient(classified([label(exp.id, "expiry_date"), label(exp.id, "retest_date")]))
    [date], discarded = label_page(layout, [exp], client)
    assert date.date_type == "expiry_date"
    assert discarded[0]["reason"].startswith("duplicate label")


def test_confidence_clamped():
    layout = make_layout(["Expiry 31/03/2027"])
    [exp] = page_candidates(layout)
    client = FakeClient(classified([label(exp.id, "expiry_date", confidence=1.7)]))
    [date], _ = label_page(layout, [exp], client)
    assert date.confidence == 1.0


@pytest.mark.parametrize(
    "error",
    [
        json.JSONDecodeError("Expecting value", "{", 1),
        ValueError("not a PageClassification"),
        ClaudeUnavailable("refused"),
    ],
)
def test_invalid_json_falls_back_to_rules(error):
    layout = make_layout(["Signed 14 March 2026", "Expiry 31/03/2027"])
    cands = page_candidates(layout)
    dates, discarded = label_page(layout, cands, FakeClient(error=error))
    assert discarded == []
    assert [(d.id, d.date_type, d.confidence, d.source) for d in dates] == [
        (c.id, offline_label(c.rule_label, layout.text, c.char_start, c.char_end), 0.5, "rules")
        for c in cands
    ]


def test_offline_when_client_none():
    layout = make_layout(["Signed 14 March 2026", "Expiry 31/03/2027", "Issued 03/04/2026"])
    cands = page_candidates(layout)
    dates, discarded = label_page(layout, cands, None)
    assert discarded == []
    assert [d.date_type for d in dates] == [
        offline_label(c.rule_label, layout.text, c.char_start, c.char_end) for c in cands
    ]
    assert dates[1].date_type == "expiry_date"
    assert all(d.confidence == 0.5 and d.source == "rules" for d in dates)
    assert all(d.resolved_value is None and d.qualifier is None for d in dates)
    assert [d.bbox for d in dates] == [c.bbox for c in cands]


def test_blank_page_offline_and_online():
    layout = make_layout([""])
    assert label_page(layout, [], None) == ([], [])
    assert label_page(layout, [], FakeClient(classified())) == ([], [])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12.III.2026", ("2026-03-12", "day")),
        ("12 iii 2026", ("2026-03-12", "day")),
        ("2026.XII.01", ("2026-12-01", "day")),
        ("III.2027", ("2027-03", "month")),
        ("12th March 2026", ("2026-03-12", "day")),
        ("the twelfth day of March, two thousand twenty-six", ("2026-03-12", "day")),
        ("21st day of September in the year two thousand and twenty-five", ("2025-09-21", "day")),
        ("March twenty twenty-six", ("2026-03", "month")),
        ("1 January nineteen ninety-nine", ("1999-01-01", "day")),
        ("31.II.2026", None),
        ("12.XIII.2026", None),
        ("soon", None),
        ("III", None),
    ],
)
def test_loose_parse(text, expected):
    assert loose_parse(text) == expected


def test_classify_imports_only_pure_modules():
    # The static build runs classify.py in Pyodide: no SDK, OCR, PDF or native fuzzy-match imports.
    code = (
        "import sys, pharma_dates.classify; "
        "heavy = {'anthropic', 'rapidfuzz', 'fastapi', 'pdfplumber', 'pypdfium2', 'pytesseract', 'PIL'}; "
        "print(sorted(heavy & set(sys.modules)))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def _offline_types(lines):
    layout = make_layout(lines)
    dates, _ = label_page(layout, page_candidates(layout), None)
    return [(d.raw_text, d.date_type) for d in dates]


def test_offline_certificate_wording_elsewhere_on_page_keeps_expiry():
    lines = [
        "CERTIFICATE OF ANALYSIS",
        "Product: Paracetamol 500 mg",
        "Batch: 12031",
        "Expiry date: 31-Jan-2025",
        "Result: complies",
        "This certificate is valid without signature.",
    ]
    assert _offline_types(lines) == [("31-Jan-2025", "expiry_date")]


def test_offline_keyword_on_another_field_line_does_not_leak():
    lines = [
        "Prepared by: A. Clerk",
        "Signature: ________",
        "Date: 05-Jan-2026",
        "Analysis date: 07-Jan-2026",
    ]
    # A bare "Date:" row takes the signature line just above it; a labelled row keeps its own.
    assert _offline_types(lines) == [("05-Jan-2026", "signature_date"), ("07-Jan-2026", "unknown")]


def test_offline_coa_header_row_labels_each_date_and_raises_no_false_flag():
    from datetime import date

    from pharma_dates.validate import validate

    layout = make_layout(["Mfg. Date: 05-Jan-2026   Retest Date: 05-Jan-2027   Expiry Date: 05-Jan-2028"])
    dates, _ = label_page(layout, page_candidates(layout), None)
    assert [d.date_type for d in dates] == ["manufacture_date", "retest_date", "expiry_date"]
    assert validate(dates, date(2026, 11, 11)) == []


def _resolve_with(lines, evidence, value):
    layout = make_layout(lines)
    cands = page_candidates(layout)
    target = next(c for c in cands if c.normalized is None)
    client = FakeClient(
        classified([label(target.id, "expiry_date", resolved_value=value, evidence=evidence)])
    )
    dates, discarded = label_page(layout, cands, client)
    date = next(d for d in dates if d.id == target.id)
    return date, discarded


def test_evidence_that_contradicts_the_page_is_rejected():
    lines = ["All dates in this certificate are written MM/DD/YYYY.", "Expiry date: 03/04/2027"]
    date, discarded = _resolve_with(
        lines, "All dates in this certificate are written DD/MM/YYYY.", "2027-04-03"
    )
    assert date.resolved_value is None and date.evidence is None
    assert [d["reason"] for d in discarded] == ["evidence not found on the page"]


def test_evidence_that_is_only_the_label_and_date_is_rejected():
    lines = ["All dates in this certificate are written MM/DD/YYYY.", "Expiry date: 03/04/2027"]
    date, discarded = _resolve_with(lines, "Expiry date: 03/04/2027", "2027-03-04")
    assert date.resolved_value is None and date.evidence is None
    assert [d["reason"] for d in discarded] == ["evidence does not show the day/month order"]


def test_evidence_on_the_page_up_to_case_and_spacing_is_accepted():
    lines = ["All dates in this certificate are written MM/DD/YYYY.", "Expiry date: 03/04/2027"]
    date, discarded = _resolve_with(
        lines, "all dates in this  certificate are written mm/dd/yyyy", "2027-03-04"
    )
    assert date.resolved_value == "2027-03-04"
    assert discarded == []
