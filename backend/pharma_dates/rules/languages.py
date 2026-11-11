"""Small, inspectable English vocabularies for date fields and month names (including roman)."""

from __future__ import annotations

import re
import unicodedata
from functools import cache

MONTH_NAMES = "January February March April May June July August September October November December".split()
ROMAN_MONTHS = "I II III IV V VI VII VIII IX X XI XII".split()

FIELD_WORDS = {
    "expiry": ["expiry", "expiration", "expires", "exp", "use before", "valid until", "shelf life"],
    "manufacture": ["manufacture", "manufactured", "mfg", "mfd", "production", "packed"],
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
    """One pattern per field label. A field word may touch a digit ("EXP03/2027", "LOT12031EXP"),
    not another letter."""
    return tuple(
        (
            label,
            re.compile(
                r"(?<![^\W\d_])(?:"
                + "|".join(re.escape(fold(word)) for word in sorted(synonyms, key=lambda s: (-len(s), s)))
                + r")(?![^\W\d_])"
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


@cache
def roman_month_lookup() -> dict[str, int]:
    """Folded (lower-case) roman numerals I..XII; callers check the printed text is upper case."""
    return {fold(numeral): number for number, numeral in enumerate(ROMAN_MONTHS, start=1)}
