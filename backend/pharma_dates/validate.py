"""Step 5: consistency flags over the labeled dates of one document (spec §5.5).

Comparisons use `effective_value`: the rules' normalized value, or the accepted reading of an
ambiguous date (`resolved_value`, which classify and the document-order step only set with
evidence). Month-precision dates compare as the last day of their month, and their flags say
"month precision". A date with no value (ambiguous, unresolved) is never compared.

Standard library and pydantic only at import time (the static build runs this module in Pyodide).
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from itertools import product

from .candidates import EVIDENCE_QUOTES
from .models import Flag, LabeledDate
from .rules.conventions import infer_order, interpret

_APPROVAL = re.compile(r"\bapprov", re.IGNORECASE)
_DOCUMENT_DATES = ("effective_date", "issue_date")
# Legalization chain: each stage must be on or after every earlier stage.
_CHAIN_STAGE = {
    "certificate_issue_date": 0,
    "notarization_date": 1,
    "apostille_date": 2,
    "legalization_date": 2,
    "translation_certification_date": 3,
}
_CHAIN_ORDER = "certificate issue, notarization, apostille or legalization, translation certification"
_SHOULD_BE_PAST = {"signature_date", "manufacture_date", "inspection_date", "audit_date"}


def effective_value(d: LabeledDate) -> date | None:
    """The date to compare: normalized or accepted resolved value; a month counts as its last day."""
    value = d.normalized or d.resolved_value
    if value is None:
        return None
    if d.precision == "month":
        year, month = (int(part) for part in value.split("-")[:2])
        return date(year, month, calendar.monthrange(year, month)[1])
    return date.fromisoformat(value)


def validate(dates: list[LabeledDate], today: date) -> list[Flag]:
    """Flags for one document's dates; `today` is the reference date for expiry and future checks."""
    valued = [(d, v) for d in dates if (v := effective_value(d)) is not None]
    return [
        *_not_after("expiry_before_manufacture", "manufacture_date", "expiry_date", valued),
        *_not_after("retest_before_manufacture", "manufacture_date", "retest_date", valued),
        *_signature_before_effective(valued),
        *_legalization_chain(valued),
        *_certificate_expired(valued, today),
        *_future_past_date(valued, today),
        *_ambiguous_unresolved(dates),
        *_ai_rules_disagree(dates),
    ]


def _of(date_type: str, valued: list[tuple[LabeledDate, date]]) -> list[tuple[LabeledDate, date]]:
    return [(d, v) for d, v in valued if d.date_type == date_type]


def _show(d: LabeledDate, v: date) -> str:
    value = d.normalized or d.resolved_value
    return f"{value} (month precision, compared as {v.isoformat()})" if d.precision == "month" else value


def _name(date_type: str) -> str:
    return date_type.removesuffix("_date").replace("_", " ")


def _not_after(rule: str, first_type: str, later_type: str, valued) -> list[Flag]:
    """Flag a `later_type` date on or before a `first_type` date (e.g. expiry ≤ manufacture).

    With one date of each type, or for a pair that are each other's nearest on the page (one
    batch's manufacture and expiry), it is an error. Other pairs in a document with several lots
    may belong to different lots, so they are only a warning."""
    firsts, laters = _of(first_type, valued), _of(later_type, valued)
    single = len(firsts) == 1 and len(laters) == 1
    flags = []
    for (first, fv), (late, lv) in product(firsts, laters):
        if lv > fv:
            continue
        paired = single or (
            _nearest(late, [f for f, _ in firsts], before=True) is first
            and _nearest(first, [d for d, _ in laters], before=False) is late
        )
        message = f"{_name(later_type).capitalize()} {_show(late, lv)} is not after {_name(first_type)} {_show(first, fv)}"
        flags.append(
            Flag(
                rule=rule,
                severity="error" if paired else "warning",
                message=f"{message}." if paired else f"{message}; these dates may belong to different lots.",
                date_ids=[first.id, late.id],
            )
        )
    return flags


def _nearest(d: LabeledDate, others: list[LabeledDate], before: bool) -> LabeledDate | None:
    """The date of `others` closest to `d` on its page (by box centre, else by text offset); on a
    tie, the one before `d` in reading order if `before`, else the one after."""
    same_page = [o for o in others if o.page == d.page]
    if not same_page:
        return None

    def key(o: LabeledDate) -> tuple[float, bool]:
        if d.bbox and o.bbox:
            dx = (d.bbox.x0 + d.bbox.x1 - o.bbox.x0 - o.bbox.x1) / 2
            dy = (d.bbox.y0 + d.bbox.y1 - o.bbox.y0 - o.bbox.y1) / 2
            distance = (dx * dx + dy * dy) ** 0.5
        else:
            distance = abs(d.char_start - o.char_start)
        return distance, (o.char_start < d.char_start) != before

    return min(same_page, key=key)


def _signature_before_effective(valued) -> list[Flag]:
    """Warning when an approval signature is dated before the document's effective or issue date."""
    approvals = [
        (d, v) for d, v in _of("signature_date", valued) if d.qualifier and _APPROVAL.search(d.qualifier)
    ]
    documents = [(d, v) for d, v in valued if d.date_type in _DOCUMENT_DATES]
    return [
        Flag(
            rule="signature_before_effective",
            severity="warning",
            message=f"Approval signature {_show(sig, sv)} is before the document "
            f"{_name(doc.date_type)} date {_show(doc, dv)}.",
            date_ids=[sig.id, doc.id],
        )
        for (sig, sv), (doc, dv) in product(approvals, documents)
        if sv < dv
    ]


def _legalization_chain(valued) -> list[Flag]:
    """Error when a later stage of the chain is dated before an earlier stage."""
    chain = [(d, v) for d, v in valued if d.date_type in _CHAIN_STAGE]
    return [
        Flag(
            rule="legalization_chain_order",
            severity="error",
            message=f"{_name(late.date_type).capitalize()} {_show(late, lv)} is before "
            f"{_name(early.date_type)} {_show(early, ev)}; expected order: {_CHAIN_ORDER}.",
            date_ids=[early.id, late.id],
        )
        for (early, ev), (late, lv) in product(chain, chain)
        if _CHAIN_STAGE[early.date_type] < _CHAIN_STAGE[late.date_type] and lv < ev
    ]


def _certificate_expired(valued, today: date) -> list[Flag]:
    return [
        Flag(
            rule="certificate_expired",
            severity="error",
            message=f"Certificate valid until {_show(d, v)} has passed (reference date {today.isoformat()}).",
            date_ids=[d.id],
        )
        for d, v in _of("certificate_valid_until", valued)
        if v < today
    ]


def _future_past_date(valued, today: date) -> list[Flag]:
    """Warning for a signature, manufacture, inspection or audit date after `today`.

    A month-precision date is flagged only when its whole month is after `today`: comparing the
    last day would flag every date of the current month.
    """
    return [
        Flag(
            rule="future_past_date",
            severity="warning",
            message=f"{_name(d.date_type).capitalize()} {_show(d, v)} is after the reference date "
            f"{today.isoformat()}; it should be in the past.",
            date_ids=[d.id],
        )
        for d, v in valued
        if d.date_type in _SHOULD_BE_PAST and (v.replace(day=1) if d.precision == "month" else v) > today
    ]


def _ambiguous_unresolved(dates: list[LabeledDate]) -> list[Flag]:
    return [
        Flag(
            rule="ambiguous_unresolved",
            severity="info",
            message=f"{d.raw_text} could be {' or '.join(d.candidates)}; choose the reading.",
            date_ids=[d.id],
        )
        for d in dates
        if d.normalized is None and d.resolved_value is None
    ]


def _ai_rules_disagree(dates: list[LabeledDate]) -> list[Flag]:
    """Warning when a resolved reading contradicts the order shown by the document's other dates.

    Readings from the document-order step agree by construction, so only Claude's can differ.
    """
    order = infer_order((d.id, d.raw_text) for d in dates)
    if order.order is None:
        return []
    first = "day" if order.order == "dmy" else "month"
    flags = []
    for d in dates:
        if d.normalized is not None or d.resolved_value is None:
            continue
        rules_value = interpret(d.raw_text, order.order)
        if rules_value in d.candidates and rules_value != d.resolved_value:
            flags.append(
                Flag(
                    rule="ai_rules_disagree",
                    severity="warning",
                    message=f"AI read {d.raw_text} as {d.resolved_value}; other dates in this document are "
                    f"only valid {first}-first, which reads it as {rules_value}.",
                    date_ids=[d.id, *order.evidence[:EVIDENCE_QUOTES]],
                )
            )
    return flags
