from __future__ import annotations

from dataclasses import dataclass
import math
import re

from .dates import DateHit, extract_dates


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


@dataclass(frozen=True)
class DocumentChunk:
    doc_id: str
    chunk_id: int
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float
    dates: list[DateHit]


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def split_chunks(doc_id: str, text: str, max_words: int = 90, overlap: int = 15) -> list[DocumentChunk]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    chunks: list[DocumentChunk] = []
    current: list[str] = []
    current_words = 0

    for line in lines:
        line_words = len(line.split())
        if current and current_words + line_words > max_words:
            chunks.append(DocumentChunk(doc_id=doc_id, chunk_id=len(chunks), text="\n".join(current)))
            keep = current[-2:] if overlap else []
            current = keep[:]
            current_words = sum(len(item.split()) for item in current)

        current.append(line)
        current_words += line_words

    if current:
        chunks.append(DocumentChunk(doc_id=doc_id, chunk_id=len(chunks), text="\n".join(current)))
    return chunks


def _term_counts(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _cosine(query_counts: dict[str, int], chunk_counts: dict[str, int]) -> float:
    dot = sum(query_counts.get(token, 0) * chunk_counts.get(token, 0) for token in query_counts)
    if dot == 0:
        return 0.0
    q_norm = math.sqrt(sum(count * count for count in query_counts.values()))
    c_norm = math.sqrt(sum(count * count for count in chunk_counts.values()))
    return dot / (q_norm * c_norm)


def retrieve(chunks: list[DocumentChunk], question: str, top_k: int = 3) -> list[RetrievedChunk]:
    query_counts = _term_counts(tokenize(question))
    scored: list[RetrievedChunk] = []

    for chunk in chunks:
        chunk_counts = _term_counts(tokenize(chunk.text))
        score = _cosine(query_counts, chunk_counts)
        date_bonus = 0.08 if extract_dates(chunk.text) else 0.0
        scored.append(
            RetrievedChunk(
                chunk=chunk,
                score=round(score + date_bonus, 4),
                dates=extract_dates(chunk.text),
            )
        )

    return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def answer_question(chunks: list[DocumentChunk], question: str, top_k: int = 3) -> str:
    results = retrieve(chunks, question, top_k=top_k)
    lines = [f"Question: {question}", ""]

    for result in results:
        lines.append(f"[{result.chunk.doc_id} chunk {result.chunk.chunk_id}] score={result.score}")
        if result.dates:
            for hit in result.dates:
                lines.append(f"- {hit.normalized} ({hit.label}, confidence={hit.confidence:.2f})")
        else:
            lines.append("- no dates found in this chunk")
        lines.append(result.chunk.text[:350])
        lines.append("")

    return "\n".join(lines).strip()


def try_llama_index_summary(_: list[DocumentChunk]) -> str:
    try:
        import llama_index  # noqa: F401
    except ImportError:
        return "LlamaIndex is not installed; using lightweight local retrieval."
    return "LlamaIndex is installed; this repo keeps the public demo on local retrieval for reproducibility."
