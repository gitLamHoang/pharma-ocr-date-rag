"""The date types (spec §6), shared by the pipeline, the store and the frontend (via `as_json`)."""

import re

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
}

_CERTIFICATE_VALIDITY = re.compile(
    r"\bcertific\w*.*\bvalid(?:ity)?\b|\bvalid(?:ity)?\b.*\bcertific", re.IGNORECASE | re.DOTALL
)

# Most specific first: an apostille or notarial certificate also says "signed".
_KEYWORDS = [
    ("apostille_date", re.compile(r"\bapostill?e\b", re.IGNORECASE)),
    ("notarization_date", re.compile(r"\bnotar\w*", re.IGNORECASE)),
    ("certificate_valid_until", _CERTIFICATE_VALIDITY),
    ("retest_date", re.compile(r"\bre-?\s?test\w*", re.IGNORECASE)),
    ("signature_date", re.compile(r"\bsign(?:ed|ature|atures|atory)?\b", re.IGNORECASE)),
    ("approval_date", re.compile(r"\bapprov\w*", re.IGNORECASE)),
    ("effective_date", re.compile(r"\beffective\b", re.IGNORECASE)),
]


def offline_label(rule_label: str, context: str) -> str:
    """Taxonomy type for a rule candidate when Claude is not used.

    Strong rule labels (expiry, manufacture, audit, received) are kept, except that an expiry
    next to certificate-validity wording becomes `certificate_valid_until`. Weak labels
    (document, qa_check, unknown) take the first English keyword found in `context`;
    otherwise `document` means `issue_date` and everything else is `unknown`.
    """
    if rule_label == "expiry" and _CERTIFICATE_VALIDITY.search(context):
        return "certificate_valid_until"
    if rule_label in _RULE_TYPES:
        return _RULE_TYPES[rule_label]
    for date_type, pattern in _KEYWORDS:
        if pattern.search(context):
            return date_type
    return "issue_date" if rule_label == "document" else "unknown"
