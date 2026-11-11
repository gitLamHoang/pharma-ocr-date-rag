"""Suggest a numeric date order from unambiguous dates in the same document.

A date such as ``31/10/2026`` is only valid day-first, so it is evidence about the
convention its document uses. A suggestion is made only when every such date in the
document agrees; conflicting or missing evidence leaves ambiguous dates unresolved.
The suggestion never replaces an explicit policy and never changes the original hit.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date

from .dates import DateHit

NUMERIC_DATE = re.compile(r"\s*(\d{1,2})[-/.](\d{1,2})[-/.]([12]\d{3})\s*")
EVIDENCE_REASON = "order_from_document_evidence"
CONFLICT_REASON = "conflicting_document_evidence"


@dataclass(frozen=True)
class DocumentOrder:
    """Unanimous, conflicting or absent same-document evidence for one numeric order."""

    status: str
    order: str | None
    dmy_evidence: tuple[str, ...] = ()
    mdy_evidence: tuple[str, ...] = ()

    @property
    def evidence(self) -> tuple[str, ...]:
        return self.dmy_evidence if self.order == "dmy" else self.mdy_evidence if self.order else ()


def _valid(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def order_vote(raw_text: str) -> str | None:
    """Return the only valid order for a full numeric date, or None if it proves nothing."""
    match = NUMERIC_DATE.fullmatch(raw_text)
    if not match:
        return None
    first, second, year = (int(part) for part in match.groups())
    dmy, mdy = _valid(year, second, first), _valid(year, first, second)
    if dmy and not mdy:
        return "dmy"
    if mdy and not dmy:
        return "mdy"
    return None


def interpret(raw_text: str, order: str) -> str | None:
    """ISO date for a full numeric date under one explicit order."""
    match = NUMERIC_DATE.fullmatch(raw_text)
    if not match or order not in {"dmy", "mdy"}:
        return None
    first, second, year = (int(part) for part in match.groups())
    day, month = (first, second) if order == "dmy" else (second, first)
    return date(year, month, day).isoformat() if _valid(year, month, day) else None


def infer_order(evidence: Iterable[tuple[str, str]]) -> DocumentOrder:
    """Combine (evidence id, raw text) pairs from one document; any disagreement abstains."""
    votes: dict[str, list[str]] = {"dmy": [], "mdy": []}
    for evidence_id, raw_text in evidence:
        vote = order_vote(raw_text)
        if vote:
            votes[vote].append(evidence_id)
    dmy, mdy = tuple(votes["dmy"]), tuple(votes["mdy"])
    if dmy and mdy:
        return DocumentOrder("conflict", None, dmy, mdy)
    if dmy or mdy:
        return DocumentOrder("unanimous", "dmy" if dmy else "mdy", dmy, mdy)
    return DocumentOrder("no_evidence", None)


def hit_order(hits: Sequence[DateHit]) -> DocumentOrder:
    """Document evidence from extracted hits, identified by their source character spans."""
    return infer_order((f"{hit.start}:{hit.end}", hit.raw_text) for hit in hits)


def apply_document_order(hits: Sequence[DateHit], order: DocumentOrder | None = None) -> list[DateHit]:
    """Resolve ambiguous numeric hits only from unanimous same-document evidence."""
    order = order or hit_order(hits)
    resolved = []
    for hit in hits:
        if "ambiguous_numeric_date" not in hit.review_reasons:
            resolved.append(hit)
            continue
        if order.status == "conflict":
            resolved.append(replace(hit, review_reasons=(*hit.review_reasons, CONFLICT_REASON)))
            continue
        value = interpret(hit.raw_text, order.order) if order.order else None
        if value is None or value not in hit.candidates:
            resolved.append(hit)
            continue
        reasons = tuple(EVIDENCE_REASON if r == "ambiguous_numeric_date" else r for r in hit.review_reasons)
        resolved.append(replace(hit, normalized=value, review_reasons=reasons))
    return resolved


def attach_document_order(records: list[dict]) -> None:
    """Add a same-notice order suggestion to ambiguous register cells; never fill `normalized`."""
    by_document: dict[str, list[dict]] = {}
    for row in records:
        by_document.setdefault(row["document_id"], []).append(row)
    for rows in by_document.values():
        order = infer_order((row["id"], row["raw_text"]) for row in rows if row["value_kind"] == "date")
        for row in rows:
            if row["value_kind"] != "ambiguous_date":
                continue
            suggested = interpret(row["raw_text"], order.order) if order.order else None
            row["document_order"] = {
                "status": order.status,
                "order": order.order,
                "suggested": suggested if suggested in row["candidates"] else None,
                # The first three revealing cells, in table order; the counts cover all of them.
                "evidence_ids": list(order.evidence[:3]),
                "dmy_count": len(order.dmy_evidence),
                "mdy_count": len(order.mdy_evidence),
            }


def leave_one_out(documents: Iterable[Sequence[tuple[str, str]]]) -> dict:
    """Hide each order-revealing date and predict its order from the rest of its document."""
    agree = disagree = abstain = 0
    for evidence in documents:
        revealing = [(item, order_vote(item[1])) for item in evidence]
        revealing = [(item, vote) for item, vote in revealing if vote]
        for index, (_, truth) in enumerate(revealing):
            rest = [item for position, (item, _) in enumerate(revealing) if position != index]
            predicted = infer_order(rest)
            if predicted.order is None:
                abstain += 1
            elif predicted.order == truth:
                agree += 1
            else:
                disagree += 1
    return {"agree": agree, "disagree": disagree, "abstain": abstain, "total": agree + disagree + abstain}
