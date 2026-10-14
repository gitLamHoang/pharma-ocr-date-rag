from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .dates import extract_dates
from .languages import labels_in
from .pipeline import ProcessedDocument
from .rag import DocumentChunk, RetrievalIndex, RetrievedChunk, split_chunks, tokenize


@dataclass(frozen=True)
class RetrievalCase:
    question: str
    expected_doc: str
    expected_label: str


@dataclass(frozen=True)
class BenchmarkRow:
    chunk_words: int
    hits: int
    total: int
    hit_rate: float


def has_expected_hit(results: list[RetrievedChunk], case: RetrievalCase) -> bool:
    for result in results:
        if result.chunk.doc_id != case.expected_doc:
            continue
        if any(hit.label == case.expected_label for hit in result.dates):
            return True
    return False


def evaluate_chunk_sizes(
    documents: list[ProcessedDocument],
    cases: list[RetrievalCase],
    chunk_sizes: list[int],
    top_k: int = 3,
) -> list[BenchmarkRow]:
    rows: list[BenchmarkRow] = []

    for chunk_words in chunk_sizes:
        chunks = []
        for document in documents:
            chunks.extend(
                split_chunks(
                    document.path.name,
                    document.ocr.text,
                    max_words=chunk_words,
                    overlap=min(chunk_words - 1, max(0, chunk_words // 6)),
                    language=document.language,
                    date_order=document.date_order,
                )
            )

        index = RetrievalIndex(chunks)
        hits = 0
        for case in cases:
            results = index.search(case.question, top_k=top_k)
            if has_expected_hit(results, case):
                hits += 1

        total = len(cases)
        rows.append(
            BenchmarkRow(
                chunk_words=chunk_words,
                hits=hits,
                total=total,
                hit_rate=hits / total if total else 0,
            )
        )

    return rows


def cosine_baseline(chunks: list[DocumentChunk], question: str, top_k: int = 3) -> list[RetrievedChunk]:
    """Previous term-frequency cosine scorer, retained only for offline comparisons.

    It shares tokenization and date-label eligibility with BM25. Ties use the same
    deterministic source order, avoiding input-order differences in the comparison.
    """
    query = Counter(tokenize(question))
    requested_labels = labels_in(question)
    scored = []
    for chunk in sorted(chunks, key=lambda c: (c.doc_id, c.chunk_id, c.start, c.end, c.text)):
        dates = extract_dates(chunk.text, language=chunk.language, date_order=chunk.date_order)
        if requested_labels and not requested_labels.intersection(hit.label for hit in dates):
            continue
        counts = Counter(tokenize(chunk.text))
        dot = sum(count * counts.get(term, 0) for term, count in query.items())
        if dot:
            norm = math.sqrt(sum(c * c for c in query.values()) * sum(c * c for c in counts.values()))
            scored.append(RetrievedChunk(chunk, dot / norm, dates))
    return sorted(scored, key=lambda row: row.score, reverse=True)[: max(0, top_k)]


def score_rankings(rankings: list[list[str]], relevance: list[list[str]], top_k: int = 3) -> dict:
    """Document-level binary relevance metrics; no-match cases have separate denominators."""
    if len(rankings) != len(relevance):
        raise ValueError("rankings and relevance must have equal lengths")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    hit_at_1 = recall = precision = reciprocal_rank = ndcg = 0.0
    answerable = negatives = abstentions = 0
    for ranking, relevant_docs in zip(rankings, relevance):
        # Each document counts once, even if multiple overlapping chunks matched.
        found = list(dict.fromkeys(ranking))[:top_k]
        relevant = set(relevant_docs)
        if not relevant:
            negatives += 1
            abstentions += not found
            continue
        answerable += 1
        gains = [int(doc_id in relevant) for doc_id in found]
        hit_at_1 += bool(gains and gains[0])
        precision += sum(gains) / top_k
        recall += sum(gains) / len(relevant)
        ranks = [i + 1 for i, gain in enumerate(gains) if gain]
        reciprocal_rank += 1 / ranks[0] if ranks else 0
        dcg = sum(gain / math.log2(i + 2) for i, gain in enumerate(gains))
        ideal = sum(1 / math.log2(i + 2) for i in range(min(top_k, len(relevant))))
        ndcg += dcg / ideal
    return {
        "answerable_queries": answerable,
        "no_match_queries": negatives,
        "hit_at_1": hit_at_1 / answerable if answerable else None,
        "precision_at_k": precision / answerable if answerable else None,
        "recall_at_k": recall / answerable if answerable else None,
        "mrr_at_k": reciprocal_rank / answerable if answerable else None,
        "ndcg_at_k": ndcg / answerable if answerable else None,
        "correct_abstentions": abstentions,
        "false_positive_queries": negatives - abstentions,
        "no_match_abstention_rate": abstentions / negatives if negatives else None,
    }
