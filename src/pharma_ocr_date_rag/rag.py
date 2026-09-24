from __future__ import annotations

from dataclasses import dataclass
import math
import re

from .dates import DateHit, extract_dates
from .languages import fold, labels_in


TOKEN_RE = re.compile(r"\w+", re.UNICODE)
STOP_WORDS = set("which what when where is are the a an of for in on was were does do how date dates document documents quelle quel quand la le les de des du est sont fecha datum ngay".split())


@dataclass(frozen=True)
class DocumentChunk:
    doc_id: str
    chunk_id: int
    text: str
    start: int = 0
    end: int = 0
    language: str = "auto"
    date_order: str = "auto"


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float
    dates: list[DateHit]


def tokenize(text: str) -> list[str]:
    tokens = [token for token in TOKEN_RE.findall(fold(text)) if token not in STOP_WORDS]
    return tokens + [f"field_{label}" for label in sorted(labels_in(text))]


def split_chunks(
    doc_id: str, text: str, max_words: int = 90, overlap: int = 15,
    language: str = "auto", date_order: str = "auto",
) -> list[DocumentChunk]:
    if max_words <= 0 or not 0 <= overlap < max_words:
        raise ValueError("max_words must be positive and 0 <= overlap < max_words")
    words = list(re.finditer(r"\S+", text))
    chunks = []
    for first in range(0, len(words), max_words - overlap):
        last = min(first + max_words, len(words))
        start, end = words[first].start(), words[last - 1].end()
        chunks.append(DocumentChunk(
            doc_id, len(chunks), text[start:end], start, end, language, date_order,
        ))
        if last == len(words):
            break
    return chunks


def _term_counts(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _cosine(query_counts: dict[str, int], chunk_counts: dict[str, int]) -> float:
    dot = sum(count * chunk_counts.get(token, 0) for token, count in query_counts.items())
    if dot == 0:
        return 0.0
    q_norm = math.sqrt(sum(count * count for count in query_counts.values()))
    c_norm = math.sqrt(sum(count * count for count in chunk_counts.values()))
    return dot / (q_norm * c_norm)


def retrieve(chunks: list[DocumentChunk], question: str, top_k: int = 3) -> list[RetrievedChunk]:
    if top_k <= 0:
        return []
    query_counts = _term_counts(tokenize(question))
    requested_labels = labels_in(question)
    scored = []
    for chunk in chunks:
        dates = extract_dates(chunk.text, language=chunk.language, date_order=chunk.date_order)
        if requested_labels and not requested_labels.intersection(hit.label for hit in dates):
            continue
        score = _cosine(query_counts, _term_counts(tokenize(chunk.text)))
        if score <= 0:
            continue
        scored.append(RetrievedChunk(chunk, round(score, 4), dates))
    return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def answer_question(chunks: list[DocumentChunk], question: str, top_k: int = 3) -> str:
    results = retrieve(chunks, question, top_k=top_k)
    lines = [f"Question: {question}", ""]
    if not results:
        return "\n".join(lines + ["No matching evidence found."])
    for result in results:
        chunk = result.chunk
        lines.append(f"[{chunk.doc_id} chunk {chunk.chunk_id}, chars {chunk.start}:{chunk.end}] score={result.score}")
        for hit in result.dates:
            value = hit.normalized or "ambiguous: " + " or ".join(hit.candidates)
            review = "; review: " + ", ".join(hit.review_reasons) if hit.review_reasons else ""
            lines.append(f"- {value} ({hit.label}{review})")
        lines.extend([chunk.text, ""])
    return "\n".join(lines).strip()
