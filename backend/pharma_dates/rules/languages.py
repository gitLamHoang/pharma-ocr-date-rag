"""Small, inspectable English vocabularies for date fields and month names."""

from __future__ import annotations

import re
import unicodedata
from functools import cache

MONTH_NAMES = "January February March April May June July August September October November December".split()

FIELD_WORDS = {
    "expiry": ["expiry", "expiration", "expires", "exp", "use before", "valid until", "shelf life"],
    "manufacture": ["manufacture", "manufactured", "mfg", "production", "packed"],
    "qa_check": ["qa", "qc", "quality", "check", "inspection", "reviewed", "verified", "released"],
    "audit": ["audit", "supplier visit", "vendor review"],
    "received": ["received", "arrival", "delivered"],
    "document": ["document", "issued", "printed", "report date"],
}


def fold(text: str) -> str:
    # One base character per source character keeps offsets stable for NFC text.
    return "".join(unicodedata.normalize("NFD", char.lower())[0] for char in text)


@cache
def field_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (
            label,
            re.compile(
                r"(?<!\w)(?:"
                + "|".join(re.escape(fold(word)) for word in sorted(synonyms, key=lambda s: (-len(s), s)))
                + r")(?!\w)"
            ),
        )
        for label, synonyms in FIELD_WORDS.items()
    )


def labels_in(text: str) -> set[str]:
    text = fold(text)
    return {label for label, pattern in field_patterns() if pattern.search(text)}


@cache
def month_lookup() -> dict[str, int]:
    months = {}
    for number, name in enumerate(MONTH_NAMES, start=1):
        months[fold(name)] = number
        months[fold(name[:3])] = number
    months["sept"] = 9
    return months
