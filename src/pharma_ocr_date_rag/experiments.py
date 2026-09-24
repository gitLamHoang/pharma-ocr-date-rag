from __future__ import annotations

from dataclasses import dataclass

from .pipeline import ProcessedDocument
from .rag import RetrievedChunk, retrieve, split_chunks


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

        hits = 0
        for case in cases:
            results = retrieve(chunks, case.question, top_k=top_k)
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
