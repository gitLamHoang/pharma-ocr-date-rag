"""The date types (spec §6), shared by the pipeline, the store and the frontend (via `as_json`)."""

import re

from .rules.dates import extract_dates

FAMILIES: dict[str, list[str]] = {
    "product": [
        "manufacture_date",
        "expiry_date",
        "retest_date",
        "packaging_date",
        "release_date",
        "sampling_date",
        "test_date",
        "analysis_report_date",
    ],
    "document": [
        "effective_date",
        "issue_date",
        "version_date",
        "approval_date",
        "review_date",
        "next_review_date",
        "superseded_date",
    ],
    "signature": ["signature_date"],
    "legal": [
        "certificate_issue_date",
        "certificate_valid_until",
        "notarization_date",
        "apostille_date",
        "legalization_date",
        "translation_certification_date",
        "authorization_date",
    ],
    "audit": ["inspection_date", "audit_date", "next_audit_date", "capa_due_date"],
    "logistics": ["shipping_date", "receipt_date"],
    "other": ["other_date", "unknown"],
}

_FAMILY_LABELS = {
    "product": "Product / batch",
    "document": "Document control",
    "signature": "Signature",
    "legal": "Legal / regulatory",
    "audit": "Audit / inspection",
    "logistics": "Logistics",
    "other": "Other",
}

_FAMILY_OF = {date_type: family for family, types in FAMILIES.items() for date_type in types}
ALL_TYPES: frozenset[str] = frozenset(_FAMILY_OF)

_TYPE_LABELS = {
    "capa_due_date": "CAPA due date",
    "certificate_valid_until": "Certificate valid until",
    "unknown": "Unknown",
}


def family_of(date_type: str) -> str:
    """Family key of a date type; `KeyError` if the type is not in the taxonomy."""
    return _FAMILY_OF[date_type]


def _type_label(date_type: str) -> str:
    return _TYPE_LABELS.get(date_type) or date_type.replace("_", " ").capitalize()


def as_json() -> list[dict]:
    return [
        {
            "family": family,
            "label": _FAMILY_LABELS[family],
            "types": [{"id": date_type, "label": _type_label(date_type)} for date_type in types],
        }
        for family, types in FAMILIES.items()
    ]


# Offline labeling (spec §11.6). Rule labels with their own keyword set map straight across.
_RULE_TYPES = {
    "expiry": "expiry_date",
    "manufacture": "manufacture_date",
    "audit": "audit_date",
    "received": "receipt_date",
    "retest": "retest_date",
    "release": "release_date",
}

# Matched on the date's own line only: a certificate of analysis that says "this certificate is
# valid without signature" three lines below the product expiry is not a validity date.
_CERTIFICATE_VALIDITY = re.compile(
    r"\bcertific\w*.*\bvalid(?:ity)?\b|\bvalid(?:ity)?\b.*\bcertific", re.IGNORECASE
)

# An apostille or notarial certificate also says "signed": on the same line these two win.
_DOCUMENT_KEYWORDS = [
    ("apostille_date", re.compile(r"\bapostill?e\b", re.IGNORECASE)),
    ("notarization_date", re.compile(r"\bnotar\w*", re.IGNORECASE)),
]
_FIELD_KEYWORDS = [
    ("certificate_valid_until", _CERTIFICATE_VALIDITY),
    ("retest_date", re.compile(r"\bre-?\s?test\w*", re.IGNORECASE)),
    ("signature_date", re.compile(r"\bsign(?:ed|ature|atures|atory)?\b", re.IGNORECASE)),
    ("approval_date", re.compile(r"\bapprov\w*", re.IGNORECASE)),
    ("effective_date", re.compile(r"\beffective\b", re.IGNORECASE)),
]
# What may precede a date on a row that does not name it: "Date:", "6. the ", "on".
_BARE_PREFIX = re.compile(r"\s*(?:\d{1,2}\.\s)?(?:[^\w]|_|\b(?:the|on|dated?)\b)*", re.IGNORECASE)
LOOKBACK_LINES = 2
_AFTER_PENALTY = 12  # a word after the date labels it less often than a word before it


def offline_label(rule_label: str, text: str, start: int | None = None, end: int | None = None) -> str:
    """Taxonomy type for a rule candidate when Claude is not used.

    `text[start:end]` is the date (by default the date follows `text`). Only the date's own line
    is read: strong rule labels (expiry, manufacture, audit, received) are kept, except that an
    expiry on a line with certificate-validity wording becomes `certificate_valid_until`. Weak
    labels (document, qa_check, unknown) take the English keyword nearest the date on its line
    (a line that starts in lower case continues the sentence of the line above it).
    A row that does not name its date ("Date: 05-Jan-2026", "6. the 12 March 2026") reads the
    keyword of the block heading just above it, up to two lines and never past another date.
    Otherwise `document` means `issue_date` and everything else is `unknown`.
    """
    if start is None or end is None:
        start = end = len(text)
    line_start = text.rfind("\n", 0, start) + 1
    if line_start and text[line_start : line_start + 1].islower():
        line_start = text.rfind("\n", 0, line_start - 1) + 1  # a sentence wrapped onto this line
    line_end = text.find("\n", end)
    line = text[line_start : len(text) if line_end == -1 else line_end]
    at, until = start - line_start, end - line_start
    if rule_label == "expiry" and _CERTIFICATE_VALIDITY.search(line):
        return "certificate_valid_until"
    if rule_label in _RULE_TYPES:
        return _RULE_TYPES[rule_label]
    found = _nearest_keyword(line, at, until)
    if found is None and _BARE_PREFIX.fullmatch(line[:at]):
        found = _heading_keyword(text[:line_start].split("\n")[:-1])
    if found is not None:
        return found
    return "issue_date" if rule_label == "document" else "unknown"


def _nearest_keyword(line: str, at: int, until: int) -> str | None:
    for date_type, pattern in _DOCUMENT_KEYWORDS:
        if pattern.search(line):
            return date_type
    best, best_distance = None, None
    for date_type, pattern in _FIELD_KEYWORDS:
        for match in pattern.finditer(line):
            if match.end() <= at:
                distance = at - match.end()
            elif match.start() >= until:
                distance = match.start() - until + _AFTER_PENALTY
            else:
                continue
            if best_distance is None or distance < best_distance:
                best, best_distance = date_type, distance
    return best


def _heading_keyword(lines_above: list[str]) -> str | None:
    for line in reversed(lines_above[-LOOKBACK_LINES:]):
        if extract_dates(line):
            return None  # that row is another field's
        found = _nearest_keyword(line, len(line), len(line))
        if found is not None:
            return found
    return None
