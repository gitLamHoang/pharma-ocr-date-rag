from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import re

from .languages import field_patterns, fold, month_lookup, validate_language


DATE_ORDERS = ("auto", "dmy", "mdy")
OCR_WORD_REPAIRS = {
    "exp1ry": "expiry", "exp1ration": "expiration", "manufacturc": "manufacture",
    "mfg.": "mfg:", "q.c.": "qc",
}
DATE_LIKE_TOKEN = re.compile(
    r"(?<![\w/.-])(?:[0-9OIl]{4}[-/.][0-9OIl]{1,2}[-/.][0-9OIl]{1,2}|"
    r"[0-9OIl]{1,2}[-/.][0-9OIl]{1,2}[-/.][0-9OIl]{4}|"
    r"[0-9OIl]{1,2}[-/][0-9OIl]{4})(?![\w/-]|\.\d)"
)


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


def repair_ocr_noise(text: str) -> str:
    """Repair only field words and date tokens; preserve source offsets."""
    for wrong, right in OCR_WORD_REPAIRS.items():
        text = re.sub(
            r"(?<!\w)" + re.escape(wrong) + r"(?!\w)",
            right.ljust(len(wrong)), text, flags=re.IGNORECASE,
        )
    return DATE_LIKE_TOKEN.sub(
        lambda match: match.group().translate(str.maketrans({"O": "0", "I": "1", "l": "1"})),
        text,
    )


@lru_cache(maxsize=None)
def _patterns(language: str) -> tuple[re.Pattern[str], ...]:
    months = month_lookup(language)
    month = "|".join(re.escape(name) for name in sorted(months, key=lambda s: (-len(s), s)))
    bodies = [
        r"(?P<year>[12]\d{3})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})",
        r"(?P<first>\d{1,2})[-/.](?P<second>\d{1,2})[-/.](?P<year>[12]\d{3})",
    ]
    if months:
        bodies.extend([
            rf"(?P<day>\d{{1,2}})\.?\s+(?:de\s+)?(?P<month>{month})\.?\s+(?:de\s+)?(?P<year>[12]\d{{3}})",
            rf"(?P<month>{month})\.?\s+(?P<day>\d{{1,2}}),?\s+(?P<year>[12]\d{{3}})",
        ])
    if language in {"auto", "vi"}:
        bodies.append(r"ngay\s+(?P<day>\d{1,2})\s+thang\s+(?P<month>\d{1,2})\s+nam\s+(?P<year>[12]\d{3})")
    bodies.append(r"(?P<month>\d{1,2})[-/](?P<year>[12]\d{3})")
    return tuple(re.compile(r"(?<![\w/.-])" + body + r"(?![\w/-]|\.\d)") for body in bodies)


def _safe_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize(match: re.Match[str], language: str, date_order: str) -> tuple[str, ...]:
    parts = match.groupdict()
    year = int(parts["year"])
    if parts.get("first"):
        first, second = int(parts["first"]), int(parts["second"])
        dmy = _safe_date(year, second, first)
        mdy = _safe_date(year, first, second)
        options = [dmy, mdy] if date_order == "auto" else [dmy if date_order == "dmy" else mdy]
        return tuple(sorted({option for option in options if option}))
    month_raw = parts["month"]
    month = int(month_raw) if month_raw.isdigit() else month_lookup(language)[month_raw]
    if not 1 <= month <= 12:
        return ()
    if not parts.get("day"):
        return (f"{year:04d}-{month:02d}",)
    normalized = _safe_date(year, month, int(parts["day"]))
    return (normalized,) if normalized else ()


def classify_context(
    context: str, date_start: int | None = None, date_end: int | None = None,
    language: str = "auto",
) -> tuple[str, float]:
    best_label, best_distance = "unknown", 10_000
    for label, pattern in field_patterns(language):
        for match in pattern.finditer(fold(context)):
            if date_start is None or date_end is None:
                distance = 0
            elif match.end() <= date_start:
                distance = date_start - match.end()
            elif match.start() >= date_end:
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
    text: str, repair_ocr: bool = True, language: str = "auto", date_order: str = "auto",
) -> list[DateHit]:
    """Return source-backed fields. Ambiguous numeric dates have no normalized value."""
    validate_language(language)
    if date_order not in DATE_ORDERS:
        raise ValueError(f"Unsupported date order: {date_order}")
    repaired = repair_ocr_noise(text) if repair_ocr else text
    searchable = fold(repaired)
    hits: list[DateHit] = []
    seen: list[tuple[int, int]] = []
    for pattern in _patterns(language):
        for match in pattern.finditer(searchable):
            start, end = match.span()
            if any(start < old_end and old_start < end for old_start, old_end in seen):
                continue
            # Reserve invalid spans too, so a suffix cannot become a month/year.
            seen.append((start, end))
            candidates = _normalize(match, language, date_order)
            if not candidates:
                continue
            left = max(text.rfind("\n", 0, start) + 1, start - 70)
            next_line = text.find("\n", end)
            right = min(next_line if next_line != -1 else len(text), end + 70)
            label, confidence = classify_context(repaired[left:right], start - left, end - left, language)
            reasons = []
            if len(candidates) > 1:
                reasons.append("ambiguous_numeric_date")
            precision = "month" if len(candidates[0]) == 7 else "day"
            if precision == "month":
                reasons.append("month_precision")
            if repaired[left:right] != text[left:right]:
                reasons.append("ocr_repaired")
            if label == "unknown":
                reasons.append("unknown_label")
            hits.append(DateHit(
                raw_text=text[start:end], normalized=candidates[0] if len(candidates) == 1 else None,
                label=label, confidence=confidence, context=text[left:right], start=start, end=end,
                candidates=candidates, precision=precision, review_reasons=tuple(reasons),
            ))
    return sorted(hits, key=lambda hit: hit.start)
