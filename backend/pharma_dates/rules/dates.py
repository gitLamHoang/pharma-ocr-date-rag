from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import cache

from .languages import field_patterns, fold, month_lookup, roman_month_lookup

DATE_ORDERS = ("auto", "dmy", "mdy")
OCR_WORD_REPAIRS = {
    "exp1ry": "expiry",
    "exp1ration": "expiration",
    "manufacturc": "manufacture",
    "mfg.": "mfg:",
    "q.c.": "qc",
}
# Letters OCR reads in place of digits. A run of them is repaired only inside a date-shaped token
# and only when it also holds a real digit ("2O26", "1S"), so "II" stays a roman month and
# "Oct" stays a month name.
OCR_DIGITS = str.maketrans({"O": "0", "I": "1", "l": "1", "S": "5", "B": "8"})
_DIGITISH_RUN = re.compile(r"[0-9OIlSB]+")
# The reverse inside a roman month ("1V", "X11", "II|", "Ill"): a month that is not all digits and
# reads as I..XII once 1, l, | and L are read as I. It must hold a V or an X, or have three or more
# characters: a two-character "1l" or "1I" is far more often a misread 11 than a misread II, so it
# is left to the digit repair, which keeps it an ambiguous numeric date.
OCR_ROMAN = str.maketrans({"1": "I", "l": "I", "|": "I", "L": "I"})
_ROMAN_NUMERALS = frozenset("I II III IV V VI VII VIII IX X XI XII".split())
_C = "[0-9OIlSB]"  # a digit, or a letter OCR reads in place of one

# Building blocks, used on folded (lower-case) text, or case-insensitively on the raw text. A
# date starts at a token boundary, or right after a batch-label field word ("EXP03/2027").
_START = r"(?:(?<![\w/.-])|(?<=exp)|(?<=mfg)|(?<=mfd))"
_END = r"(?![\w/-]|\.\d)"
_SEP = r" ?[-/.] ?"  # "12.03.2026", "12 . 03 . 2026", "12. 03. 2026"
_NOISE = r"(?: ?[-/.,:;] ?| {1,2}|)"  # around a month name: "25.Mar.2026", "4 Sep:2025", "25MAR2026"
_ROMAN_SEP = r"(?: ?[-/.] ?| )"
_YEAR = r"(?P<year>(?:19|20)\d{2})"  # a plausible year; "10 X 1000 mL" is a pack size


def _repair_digits(token: str) -> str:
    named = _date_like_token_named().fullmatch(token)
    if named:
        day, month, year = named.groups()
        return _repair_digits(day) + month + _repair_digits(year)
    return _DIGITISH_RUN.sub(
        lambda run: (
            run.group().translate(OCR_DIGITS) if any(c.isdigit() for c in run.group()) else run.group()
        ),
        token,
    )


def _named_shape(group: str) -> str:
    """Day, month name and year; with `group="("` as three groups, so `_repair_digits` can keep
    the "O" of "17Oct2022" a letter."""
    month = "|".join(sorted(month_lookup(), key=lambda s: (-len(s), s)))
    return rf"{group}{_C}{{1,2}}){group}{_NOISE}(?:{month})\.?{_NOISE}){group}{_C}{{4}})"


@cache
def _date_like_token_named() -> re.Pattern[str]:
    return re.compile(_named_shape("("), re.IGNORECASE)


@cache
def _date_like_token() -> re.Pattern[str]:
    """Date-shaped tokens on the raw text, with OCR letters allowed where digits belong.

    Under IGNORECASE the letter class also takes "o", "i", "L", "s" and "b"; `_repair_digits`
    repairs only the upper-case forms (and "l"), so such a token is left as printed."""
    shapes = [
        rf"{_C}{{4}}{_SEP}{_C}{{1,2}}{_SEP}{_C}{{1,2}}",
        rf"{_C}{{1,2}}{_SEP}{_C}{{1,2}}{_SEP}{_C}{{4}}",
        rf"{_C}{{1,2}}[-/]{_C}{{4}}",
        _named_shape("(?:"),
    ]
    return re.compile(_START + "(?:" + "|".join(shapes) + ")" + _END, re.IGNORECASE)


@dataclass(frozen=True)
class DateHit:
    raw_text: str
    normalized: str | None
    label: str
    confidence: float
    context: str
    start: int
    end: int
    candidates: tuple[str, ...] = ()
    precision: str = "day"
    review_reasons: tuple[str, ...] = ()


_ROMAN_TOKEN = re.compile(
    rf"(?<![\w/.-])({_C}{{1,2}}{_ROMAN_SEP})([IVXl1|L]{{2,4}}|[IVXl1|L]*[VX][IVXl1|L]*)({_ROMAN_SEP}{_C}{{4}}){_END}"
)


def _repair_roman(match: re.Match[str]) -> str:
    day, month, year = match.groups()
    repaired = month.translate(OCR_ROMAN)
    if month.isdigit() or repaired not in _ROMAN_NUMERALS:
        return match.group()
    if len(month) < 3 and not {"V", "X"} & set(month):
        return match.group()
    return _repair_digits(day) + repaired + _repair_digits(year)


def repair_ocr_noise(text: str) -> str:
    """Repair only field words and date tokens; preserve source offsets."""
    for wrong, right in OCR_WORD_REPAIRS.items():
        text = re.sub(
            r"(?<!\w)" + re.escape(wrong) + r"(?!\w)",
            right.ljust(len(wrong)),
            text,
            flags=re.IGNORECASE,
        )
    text = _ROMAN_TOKEN.sub(_repair_roman, text)
    return _date_like_token().sub(lambda match: _repair_digits(match.group()), text)


@cache
def _patterns() -> tuple[re.Pattern[str], ...]:
    month = "|".join(re.escape(name) for name in sorted(month_lookup(), key=lambda s: (-len(s), s)))
    romans = sorted(roman_month_lookup(), key=lambda s: (-len(s), s))
    roman = "|".join(romans)
    # A one-letter month (I, V, X) between spaces reads as a quantity ("3 X 2000 TABLETS",
    # "Rev 2 V 2020"), so it needs a punctuated separator on both sides.
    roman_long = "|".join(numeral for numeral in romans if len(numeral) > 1)
    bodies = [
        rf"{_YEAR}{_SEP}(?P<month>\d{{1,2}}){_SEP}(?P<day>\d{{1,2}})",
        rf"(?P<first>\d{{1,2}}){_SEP}(?P<second>\d{{1,2}}){_SEP}{_YEAR}",
        rf"(?P<day>\d{{1,2}}){_SEP}(?P<roman>{roman}){_SEP}{_YEAR}",
        rf"(?P<day>\d{{1,2}}){_ROMAN_SEP}(?P<roman>{roman_long}){_ROMAN_SEP}{_YEAR}",
        rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?: of)?\.?{_NOISE}(?P<month>{month})\.?{_NOISE}{_YEAR}",
        rf"(?P<month>{month})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,\s*|\s+){_YEAR}",
        # Numeric month and year ("03/2027", "03.2027", "2027-03"); see `_NUMERIC_MONTH_YEAR`.
        rf"(?P<month>\d{{1,2}})[-/]{_YEAR}",
        rf"(?P<month>\d{{2}})\.{_YEAR}",
        rf"{_YEAR}[-/](?P<month>\d{{2}})",
        # Month and year only ("MAR 2027", "Feb. 2026", "MAR-2027", "March, 2027"); not after
        # "of", where a spelled-out day may precede the month, and not in lower case (see
        # `extract_dates`).
        rf"(?<!of )(?P<month>{month})(?:\. ?| {{1,2}}|-|, ?){_YEAR}",
    ]
    return tuple(re.compile(_START + body + _END) for body in bodies)


# A numeric month and year followed by a unit is a range or a count: "10-2000 ng/mL", "5-2000 um".
_UNIT_AFTER = re.compile(
    r"\s*(?:%|(?:ng|ug|µg|μg|mcg|mg|g|kg|ml|µl|μl|ul|l|nm|um|µm|μm|mm|cm|cfu|ppm|ppb|iu|units?|counts?"
    r"|tablets?|capsules?|vials?|doses?)(?![^\W\d_]))"
)


def _numeric_month_year(match: re.Match[str]) -> bool:
    groups = match.groupdict()
    return "day" not in groups and "first" not in groups and groups["month"].isdigit()


def _needs_label(match: re.Match[str]) -> bool:
    """A numeric month and year other than "MM/YYYY" or "MM-YYYY" ("3/2027", "03.2027", "2027-03")
    is a date only next to a field word ("EXP 03.2027"): unlabeled, it is more often a dilution
    ("1/2000"), a version ("Rev. 3.2021") or a reference ("Ref 2026-01")."""
    if match.start("month") > match.start("year"):
        return True
    return len(match.group("month")) == 1 or match.string[match.end("month")] == "."


def _safe_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize(match: re.Match[str], date_order: str) -> tuple[str, ...]:
    parts = match.groupdict()
    year = int(parts["year"])
    if parts.get("first"):
        first, second = int(parts["first"]), int(parts["second"])
        dmy = _safe_date(year, second, first)
        mdy = _safe_date(year, first, second)
        options = [dmy, mdy] if date_order == "auto" else [dmy if date_order == "dmy" else mdy]
        return tuple(sorted({option for option in options if option}))
    if parts.get("roman"):
        month = roman_month_lookup()[parts["roman"]]
    else:
        month_raw = parts["month"]
        month = int(month_raw) if month_raw.isdigit() else month_lookup()[month_raw]
    if not 1 <= month <= 12:
        return ()
    if not parts.get("day"):
        return (f"{year:04d}-{month:02d}",)
    normalized = _safe_date(year, month, int(parts["day"]))
    return (normalized,) if normalized else ()


def classify_context(
    context: str,
    date_start: int | None = None,
    date_end: int | None = None,
    other_dates: tuple[tuple[int, int], ...] = (),
) -> tuple[str, float]:
    """The field label nearest the date in `context`, with a confidence.

    `other_dates` are the spans of the other dates in `context`. A label never reaches past one
    ("Mfg: 05-Jan-2026  Analysis: 07-Jan-2026" leaves the second date unlabeled), and a label
    followed by another date is that date's, not an earlier one's.
    """
    best_label, best_distance = "unknown", 10_000
    for label, pattern in field_patterns():
        for match in pattern.finditer(fold(context)):
            if date_start is None or date_end is None:
                distance = 0
            elif match.end() <= date_start:
                if any(match.end() <= s and e <= date_start for s, e in other_dates):
                    continue
                distance = date_start - match.end()
            elif match.start() >= date_end:
                if any(s >= date_end for s, _ in other_dates):
                    continue
                distance = match.start() - date_end + 12
            else:
                continue
            if distance < best_distance:
                best_label, best_distance = label, distance
    if best_distance <= 18:
        return best_label, 0.9
    if best_distance <= 60:
        return best_label, 0.72
    return "unknown", 0.35


def extract_dates(
    text: str,
    repair_ocr: bool = True,
    date_order: str = "auto",
    standalone: bool = False,
) -> list[DateHit]:
    """Return source-backed fields. Ambiguous numeric dates have no normalized value.

    `standalone` means `text` is a quoted date on its own (Claude's verbatim text, checked against
    the page afterwards), so forms that need a field word on a page ("03.2027") are read without."""
    if date_order not in DATE_ORDERS:
        raise ValueError(f"Unsupported date order: {date_order}")
    repaired = repair_ocr_noise(text) if repair_ocr else text
    searchable = fold(repaired)
    found: list[tuple[int, int, tuple[str, ...]]] = []
    seen: list[tuple[int, int]] = []
    for pattern in _patterns():
        for match in pattern.finditer(searchable):
            start, end = match.span()
            if any(start < old_end and old_start < end for old_start, old_end in seen):
                continue
            # Reserve invalid spans too, so a suffix cannot become a month/year.
            seen.append((start, end))
            groups = match.groupdict()
            if groups.get("roman") and not repaired[slice(*match.span("roman"))].isupper():
                continue
            # A lower-case month word with only a year is a verb ("patients may 2000 mg").
            if "day" not in groups and "first" not in groups:
                if repaired[slice(*match.span("month"))].islower():
                    continue
            numeric_month = _numeric_month_year(match)
            if numeric_month and _UNIT_AFTER.match(searchable, end):
                continue
            candidates = _normalize(match, date_order)
            if candidates:
                found.append((start, end, candidates, numeric_month and _needs_label(match)))
    hits: list[DateHit] = []
    for start, end, candidates, needs_label in found:
        left = max(text.rfind("\n", 0, start) + 1, start - 70)
        next_line = text.find("\n", end)
        right = min(next_line if next_line != -1 else len(text), end + 70)
        others = tuple(
            (max(s, left) - left, min(e, right) - left)
            for s, e, *_ in found
            if (s, e) != (start, end) and s < right and left < e
        )
        label, confidence = classify_context(repaired[left:right], start - left, end - left, others)
        if needs_label and label == "unknown" and not standalone:
            continue
        reasons = []
        if len(candidates) > 1:
            reasons.append("ambiguous_numeric_date")
        precision = "month" if len(candidates[0]) == 7 else "day"
        if precision == "month":
            reasons.append("month_precision")
        if repaired[start:end] != text[start:end]:
            reasons.append("ocr_repaired")
        if label == "unknown":
            reasons.append("unknown_label")
        hits.append(
            DateHit(
                raw_text=text[start:end],
                normalized=candidates[0] if len(candidates) == 1 else None,
                label=label,
                confidence=confidence,
                context=text[left:right],
                start=start,
                end=end,
                candidates=candidates,
                precision=precision,
                review_reasons=tuple(reasons),
            )
        )
    return sorted(hits, key=lambda hit: hit.start)
