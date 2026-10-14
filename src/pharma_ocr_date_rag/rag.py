from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256

from .dates import DateHit, extract_dates
from .languages import fold, labels_in

TOKEN_RE = re.compile(r"\w+", re.UNICODE)
STOP_WORDS = set(
    "which what when where is are the a an of for in on was were does do how date dates document documents quelle quel quand la le les de des du est sont fecha datum ngay".split()
)


@dataclass(frozen=True)
class DocumentChunk:
    doc_id: str
    chunk_id: int
    text: str
    start: int = 0
    end: int = 0
    language: str = "auto"
    date_order: str = "auto"

    def __post_init__(self) -> None:
        if self.end == 0:
            object.__setattr__(self, "end", self.start + len(self.text))
        if self.start < 0 or self.end - self.start != len(self.text):
            raise ValueError("chunk span must describe its exact original text")


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float
    dates: list[DateHit]


def tokenize(text: str) -> list[str]:
    tokens = [token for token in TOKEN_RE.findall(fold(text)) if token not in STOP_WORDS]
    return tokens + [f"field_{label}" for label in sorted(labels_in(text))]


def split_chunks(
    doc_id: str,
    text: str,
    max_words: int = 90,
    overlap: int = 15,
    language: str = "auto",
    date_order: str = "auto",
) -> list[DocumentChunk]:
    if max_words <= 0 or not 0 <= overlap < max_words:
        raise ValueError("max_words must be positive and 0 <= overlap < max_words")
    words = list(re.finditer(r"\S+", text))
    chunks = []
    for first in range(0, len(words), max_words - overlap):
        last = min(first + max_words, len(words))
        start, end = words[first].start(), words[last - 1].end()
        chunks.append(
            DocumentChunk(
                doc_id,
                len(chunks),
                text[start:end],
                start,
                end,
                language,
                date_order,
            )
        )
        if last == len(words):
            break
    return chunks


@dataclass(frozen=True)
class BM25Config:
    """Bounded ranking parameters; scores are relevance values, never probabilities."""

    k1: float = 1.2
    b: float = 0.75

    def __post_init__(self) -> None:
        if not math.isfinite(self.k1) or not 0 < self.k1 <= 3:
            raise ValueError("k1 must be finite and in (0, 3]")
        if not math.isfinite(self.b) or not 0 <= self.b <= 1:
            raise ValueError("b must be finite and in [0, 1]")


class RetrievalIndex:
    """Reusable BM25 index over exact source chunks.

    Indexing tokenizes and extracts dates once. Query-time work traverses postings
    only for query terms. Field aliases retain multilingual date-label matching;
    recognized date-field queries still require an extracted date of that label.
    This is lexical evidence retrieval, not a generative or semantic model.
    """

    MAX_QUERY_CHARS = 4096
    MAX_QUERY_TOKENS = 128
    MAX_TOP_K = 100

    def __init__(self, chunks: Iterable[DocumentChunk], config: BM25Config | None = None):
        self.config = config or BM25Config()
        # Freeze the caller's sequence, with a stable tie order independent of input order.
        self.chunks = tuple(
            sorted(
                chunks, key=lambda c: (c.doc_id, c.chunk_id, c.start, c.end, c.text, c.language, c.date_order)
            )
        )
        self._dates = tuple(
            tuple(extract_dates(c.text, language=c.language, date_order=c.date_order)) for c in self.chunks
        )
        counts = [Counter(tokenize(c.text)) for c in self.chunks]
        self._lengths = tuple(sum(count.values()) for count in counts)
        self._average_length = sum(self._lengths) / len(counts) if counts else 0.0
        self._postings: dict[str, list[tuple[int, int]]] = {}
        for index, terms in enumerate(counts):
            for term, frequency in terms.items():
                self._postings.setdefault(term, []).append((index, frequency))
        self._idf = {
            term: math.log1p((len(counts) - len(postings) + 0.5) / (len(postings) + 0.5))
            for term, postings in self._postings.items()
        }

    def _query_terms(self, question: str, top_k: int) -> list[str]:
        if not isinstance(question, str):
            raise TypeError("question must be a string")
        if not isinstance(top_k, int) or isinstance(top_k, bool):
            raise TypeError("top_k must be an integer")
        if top_k > self.MAX_TOP_K:
            raise ValueError(f"top_k must not exceed {self.MAX_TOP_K}")
        if len(question) > self.MAX_QUERY_CHARS:
            raise ValueError(f"question must not exceed {self.MAX_QUERY_CHARS} characters")
        tokens = tokenize(question)
        if len(tokens) > self.MAX_QUERY_TOKENS:
            raise ValueError(f"question must not exceed {self.MAX_QUERY_TOKENS} searchable tokens")
        # Repeating a query word must not multiply its influence.
        return sorted(set(tokens))

    def search(self, question: str, top_k: int = 3) -> list[RetrievedChunk]:
        terms = self._query_terms(question, top_k)
        if top_k <= 0 or not terms or not self._average_length:
            return []
        requested_labels = labels_in(question)
        scores: dict[int, float] = {}
        for term in terms:
            for index, frequency in self._postings.get(term, ()):
                length = self._lengths[index] / self._average_length
                denominator = frequency + self.config.k1 * (1 - self.config.b + self.config.b * length)
                value = self._idf[term] * frequency * (self.config.k1 + 1) / denominator
                scores[index] = scores.get(index, 0.0) + value
        eligible = [
            index
            for index in scores
            if not requested_labels or requested_labels.intersection(hit.label for hit in self._dates[index])
        ]
        # Rank full-precision scores; round only for serialization/display.
        ranked = sorted(eligible, key=lambda index: (-scores[index], index))[:top_k]
        return [RetrievedChunk(self.chunks[i], round(scores[i], 6), list(self._dates[i])) for i in ranked]

    def evidence(self, question: str, top_k: int = 3) -> dict[str, object]:
        """Return JSON-safe citations; all spans use original-document character offsets."""
        results = self.search(question, top_k)
        terms = set(self._query_terms(question, top_k))
        reason = None
        if not results:
            reason = "zero_limit" if top_k <= 0 else "empty_query" if not terms else "no_matching_evidence"
        evidence = []
        for result in results:
            chunk = result.chunk
            evidence.append(
                {
                    "doc_id": chunk.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "source_span": {"start": chunk.start, "end": chunk.end},
                    "chunk_sha256": sha256(chunk.text.encode("utf-8")).hexdigest(),
                    "text": chunk.text,
                    "score": result.score,
                    "language": chunk.language,
                    "date_order": chunk.date_order,
                    "matched_terms": sorted(terms.intersection(tokenize(chunk.text))),
                    "dates": [
                        {
                            "raw_text": hit.raw_text,
                            "normalized": hit.normalized,
                            "label": hit.label,
                            "candidates": list(hit.candidates),
                            "precision": hit.precision,
                            "review_reasons": list(hit.review_reasons),
                            "source_span": {"start": chunk.start + hit.start, "end": chunk.start + hit.end},
                        }
                        for hit in result.dates
                    ],
                }
            )
        return {
            "schema_version": 1,
            "retrieval_method": "bm25",
            "question": question,
            "status": "matched" if results else "abstained",
            "reason": reason,
            "score_semantics": "Uncalibrated lexical relevance, not extraction confidence or probability.",
            "results": evidence,
        }


def retrieve(chunks: list[DocumentChunk], question: str, top_k: int = 3) -> list[RetrievedChunk]:
    """Compatibility wrapper. Reuse RetrievalIndex for multiple queries over one corpus."""
    return RetrievalIndex(chunks).search(question, top_k=top_k)


def answer_question_json(chunks: list[DocumentChunk], question: str, top_k: int = 3) -> dict[str, object]:
    return RetrievalIndex(chunks).evidence(question, top_k=top_k)


def answer_question(chunks: list[DocumentChunk], question: str, top_k: int = 3) -> str:
    results = retrieve(chunks, question, top_k=top_k)
    lines = [f"Question: {question}", ""]
    if not results:
        return "\n".join(lines + ["No matching evidence found."])
    for result in results:
        chunk = result.chunk
        lines.append(
            f"[{chunk.doc_id} chunk {chunk.chunk_id}, chars {chunk.start}:{chunk.end}] score={result.score}"
        )
        for hit in result.dates:
            value = hit.normalized or "ambiguous: " + " or ".join(hit.candidates)
            review = "; review: " + ", ".join(hit.review_reasons) if hit.review_reasons else ""
            lines.append(f"- {value} ({hit.label}{review})")
        lines.extend([chunk.text, ""])
    return "\n".join(lines).strip()
