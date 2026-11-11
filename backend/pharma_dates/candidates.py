"""Step 3: rule-based date candidates with their location on the page.

Only dates found in the page's own text layer (pdfplumber or Tesseract) are `rules` candidates.
Dates found only in Claude's transcription are `ai_only` and must pass verification later.
"""

from collections.abc import Iterable

from .models import BBox, Candidate, PageLayout, Word
from .rules.conventions import infer_order, interpret
from .rules.dates import DateHit, extract_dates, repair_ocr_noise
from .rules.languages import fold

CONTEXT_CHARS = 200
EVIDENCE_QUOTES = 3


def page_candidates(layout: PageLayout, date_order: str = "auto") -> list[Candidate]:
    """Every date the rules find in `layout.text`, each with the union box of its words."""
    return [
        _candidate(
            hit,
            layout.text,
            f"p{layout.n}-c{i}",
            layout.n,
            span_box(layout.words, hit.start, hit.end),
            "rules",
        )
        for i, hit in enumerate(extract_dates(layout.text, date_order=date_order), start=1)
    ]


def transcription_candidates(layout: PageLayout, existing: list[Candidate]) -> list[Candidate]:
    """Dates in Claude's transcription that the text layer did not yield.

    A transcription hit is the same date as a text-layer candidate when their raw texts match
    after OCR-digit repair, case folding and whitespace collapsing, and their possible values
    overlap (so the comparison does not depend on the `date_order` policy). Each text-layer
    candidate absorbs at most one transcription hit, so a date printed twice stays twice.
    Offsets and context refer to the transcription; the extras have no box until verified.
    """
    if not layout.transcription:
        return []
    unmatched = list(existing)
    hits = []
    for hit in extract_dates(layout.transcription):
        match = next((c for c in unmatched if _same_date(c, hit)), None)
        if match is None:
            hits.append(hit)
        else:
            unmatched.remove(match)
    return [
        _candidate(hit, layout.transcription, f"p{layout.n}-t{i}", layout.n, None, "ai_only")
        for i, hit in enumerate(hits, start=1)
    ]


def apply_document_order[C: Candidate](cands: list[C]) -> list[C]:
    """Suggest a value for ambiguous numeric dates from unanimous order evidence in the document.

    The suggestion goes into `resolved_value` with the revealing dates quoted as `evidence`, and
    only on labeled dates that have no resolution yet. `normalized` is never set.
    """
    order = infer_order((c.id, c.raw_text) for c in cands)
    if order.order is None:
        return list(cands)
    raw_by_id = {c.id: c.raw_text for c in cands}
    quotes = ", ".join(f'"{raw_by_id[i]}" ({i})' for i in order.evidence[:EVIDENCE_QUOTES])
    first = "day" if order.order == "dmy" else "month"
    evidence = f"Other dates in this document are only valid {first}-first: {quotes}"
    result = []
    for c in cands:
        suggested = interpret(c.raw_text, order.order)
        if (
            c.normalized is None
            and suggested in c.candidates
            and hasattr(c, "resolved_value")
            and c.resolved_value is None
        ):
            c = c.model_copy(update={"resolved_value": suggested, "evidence": evidence})
        result.append(c)
    return result


def _candidate(hit: DateHit, text: str, id_: str, page: int, bbox: BBox | None, source: str) -> Candidate:
    return Candidate(
        id=id_,
        page=page,
        raw_text=hit.raw_text,
        normalized=hit.normalized,
        candidates=list(hit.candidates),
        precision=hit.precision,
        char_start=hit.start,
        char_end=hit.end,
        bbox=bbox,
        context=text[max(0, hit.start - CONTEXT_CHARS) : hit.end + CONTEXT_CHARS],
        rule_label=hit.label,
        source=source,
    )


def span_box(words: list[Word], start: int, end: int) -> BBox | None:
    """Union box of the words overlapping the text span `[start, end)`."""
    boxes = [w.bbox for w in words if w.char_start < end and start < w.char_end]
    if not boxes:
        return None
    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


def _same_date(cand: Candidate, hit: DateHit) -> bool:
    return _print_key(cand.raw_text) == _print_key(hit.raw_text) and bool(
        _values(cand.normalized, cand.candidates) & _values(hit.normalized, hit.candidates)
    )


def _print_key(raw_text: str) -> str:
    """The printed form with OCR digit noise, case and spacing differences removed."""
    return " ".join(fold(repair_ocr_noise(raw_text)).split())


def _values(normalized: str | None, candidates: Iterable[str]) -> set[str]:
    return set(candidates) | ({normalized} if normalized else set())
