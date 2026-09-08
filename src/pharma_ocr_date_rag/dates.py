from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

DATE_PATTERNS = [
    re.compile(r"\b(?P<year>20\d{2})[-/.](?P<month>0?[1-9]|1[0-2])[-/.](?P<day>0?[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(?P<month>0?[1-9]|1[0-2])[-/.](?P<day>0?[1-9]|[12]\d|3[01])[-/.](?P<year>20\d{2})\b"),
    re.compile(
        r"\b(?P<day>0?[1-9]|[12]\d|3[01])\s+"
        r"(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+(?P<year>20\d{2})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+(?P<day>0?[1-9]|[12]\d|3[01]),?\s+(?P<year>20\d{2})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?P<month>0?[1-9]|1[0-2])[-/](?P<year>20\d{2})\b"),
]

LABEL_KEYWORDS = {
    "expiry": ["expiry", "expiration", "expires", "exp ", "exp:", "exp.", "use before", "valid until", "shelf life"],
    "manufacture": ["manufacture", "manufactured", "mfg", "production", "packed"],
    "qa_check": ["qa", "qc", "quality", "check", "inspection", "reviewed", "verified", "released"],
    "audit": ["audit", "supplier visit", "vendor review"],
    "received": ["received", "arrival", "delivered"],
    "document": ["document", "issued", "printed", "report date"],
}

OCR_WORD_REPAIRS = {
    "exp1ry": "expiry",
    "exp1ration": "expiration",
    "manufacturc": "manufacture",
    "mfg.": "mfg:",
    "q.c.": "qc",
}

DATE_LIKE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9-])"
    r"(?P<token>"
    r"[0-9OIl]{4}[-/.][0-9OIl]{1,2}[-/.][0-9OIl]{1,2}|"
    r"[0-9OIl]{1,2}[-/.][0-9OIl]{1,2}[-/.][0-9OIl]{4}|"
    r"[0-9OIl]{1,2}[-/][0-9OIl]{4}"
    r")"
    r"(?![A-Za-z0-9-])"
)


@dataclass(frozen=True)
class DateHit:
    raw_text: str
    normalized: str
    label: str
    confidence: float
    context: str
    start: int
    end: int


def repair_ocr_noise(text: str) -> str:
    """Clean a few OCR mistakes before date extraction.

    This is intentionally small and transparent. It only repairs common field
    words and date-looking tokens, not the whole document.
    """
    repaired = text
    for wrong, right in OCR_WORD_REPAIRS.items():
        repaired = re.sub(re.escape(wrong), right, repaired, flags=re.IGNORECASE)

    def fix_date_token(match: re.Match[str]) -> str:
        token = match.group("token")
        return token.translate(str.maketrans({"O": "0", "I": "1", "l": "1"}))

    return DATE_LIKE_TOKEN.sub(fix_date_token, repaired)


def _safe_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize(match: re.Match[str]) -> str | None:
    parts = match.groupdict()
    year = int(parts["year"])
    month_raw = parts["month"]
    if month_raw.isdigit():
        month = int(month_raw)
    else:
        month = MONTHS[month_raw.lower()]

    day_raw = parts.get("day")
    if not day_raw:
        return f"{year:04d}-{month:02d}"
    return _safe_date(year, month, int(day_raw))


def _window(text: str, start: int, end: int, chars: int = 45) -> str:
    line_left = text.rfind("\n", 0, start) + 1
    line_right = text.find("\n", end)
    if line_right == -1:
        line_right = len(text)

    left = max(line_left, start - chars)
    right = min(line_right, end + chars)
    return " ".join(text[left:right].split())


def classify_context(context: str, date_start: int | None = None, date_end: int | None = None) -> tuple[str, float]:
    lowered = context.lower()
    best_label = "unknown"
    best_distance = 10_000

    for label, keywords in LABEL_KEYWORDS.items():
        for keyword in keywords:
            index = lowered.find(keyword)
            while index != -1:
                if date_start is None or date_end is None:
                    distance = 0
                elif index < date_start:
                    distance = date_start - (index + len(keyword))
                else:
                    distance = (index - date_end) + 12

                if distance < best_distance:
                    best_label = label
                    best_distance = distance
                index = lowered.find(keyword, index + 1)

    if best_label == "unknown":
        return "unknown", 0.35
    if best_distance <= 18:
        return best_label, 0.9
    if best_distance <= 45:
        return best_label, 0.72
    return "unknown", 0.35


def extract_dates(text: str, repair_ocr: bool = True) -> list[DateHit]:
    if repair_ocr:
        text = repair_ocr_noise(text)

    hits: list[DateHit] = []
    seen: list[tuple[int, int]] = []

    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            overlaps = any(span[0] < old_end and old_start < span[1] for old_start, old_end in seen)
            if overlaps:
                continue
            seen.append(span)
            normalized = _normalize(match)
            if not normalized:
                continue
            context = _window(text, match.start(), match.end())
            local_start = context.lower().find(match.group(0).lower())
            local_end = local_start + len(match.group(0)) if local_start >= 0 else None
            label, confidence = classify_context(
                context,
                date_start=local_start if local_start >= 0 else None,
                date_end=local_end,
            )
            hits.append(
                DateHit(
                    raw_text=match.group(0),
                    normalized=normalized,
                    label=label,
                    confidence=confidence,
                    context=context,
                    start=match.start(),
                    end=match.end(),
                )
            )

    return sorted(hits, key=lambda hit: hit.start)
