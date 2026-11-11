"""Data types shared by every pipeline step."""

from typing import Literal

from pydantic import BaseModel, Field


class BBox(BaseModel):
    """A box in page-image pixel coordinates (origin top-left)."""

    x0: float
    y0: float
    x1: float
    y1: float


class Word(BaseModel):
    text: str
    bbox: BBox
    char_start: int
    char_end: int


class PageLayout(BaseModel):
    n: int
    width: int
    height: int
    text: str
    text_source: Literal["pdf", "ocr"]
    words: list[Word]
    transcription: str | None = None


class Candidate(BaseModel):
    id: str
    page: int
    raw_text: str
    normalized: str | None
    candidates: list[str]
    precision: Literal["day", "month"]
    char_start: int
    char_end: int
    bbox: BBox | None
    context: str
    rule_label: str
    source: Literal["rules", "ai_only", "rules+ai"]


class LabeledDate(Candidate):
    date_type: str
    family: str
    qualifier: str | None
    resolved_value: str | None
    evidence: str | None
    confidence: float = Field(ge=0, le=1)
    rationale: str | None


class Flag(BaseModel):
    rule: str
    severity: Literal["error", "warning", "info"]
    message: str
    date_ids: list[str]
