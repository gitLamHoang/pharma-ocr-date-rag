import hashlib
import json
import math

import pytest

from pharma_ocr_date_rag import rag
from pharma_ocr_date_rag.rag import (
    BM25Config,
    DocumentChunk,
    RetrievalIndex,
    answer_question_json,
    split_chunks,
)


def test_bm25_matches_hand_calculated_score_and_ignores_repeated_query_words():
    chunks = split_chunks("a", "quartz quartz") + split_chunks("b", "granite")
    index = RetrievalIndex(chunks)
    expected = math.log1p(1.5 / 1.5) * 2 * 2.2 / (2 + 1.2 * (0.25 + 0.75 * 2 / 1.5))
    result = index.search("quartz")
    assert result[0].score == pytest.approx(expected, abs=0.000001)
    assert index.search("quartz quartz") == result


def test_equal_scores_are_stable_independent_of_corpus_order():
    chunks = split_chunks("zeta", "Expiry: 2028-04-14") + split_chunks("alpha", "Expiry: 2028-04-14")
    assert [r.chunk.doc_id for r in RetrievalIndex(chunks).search("expiry")] == ["alpha", "zeta"]
    assert RetrievalIndex(reversed(chunks)).search("expiry") == RetrievalIndex(chunks).search("expiry")


def test_index_parses_dates_once_and_results_cannot_mutate_cached_evidence(monkeypatch):
    calls = []
    original = rag.extract_dates

    def counting_extract(text, **kwargs):
        calls.append(text)
        return original(text, **kwargs)

    monkeypatch.setattr(rag, "extract_dates", counting_extract)
    chunks = split_chunks("a", "Expiry: 2028-04-14")
    index = RetrievalIndex(chunks)
    chunks.clear()
    result = index.search("expiry")
    result[0].dates.clear()
    assert index.search("expiry")[0].dates[0].normalized == "2028-04-14"
    assert len(calls) == 1


def test_requested_label_requires_date_evidence_not_just_keyword():
    chunks = split_chunks("empty", "Expiry date is missing.") + split_chunks("dated", "Expiry: 2028-04-14")
    assert [r.chunk.doc_id for r in RetrievalIndex(chunks).search("expiry")] == ["dated"]
    assert RetrievalIndex(chunks).search("manufacture") == []


def test_structured_evidence_retains_original_unicode_spans_hash_and_ambiguity():
    text = "Préface étude\n\nExpiry: 09/10/2026"
    chunks = split_chunks("source.txt", text, max_words=2, overlap=0)
    response = answer_question_json(chunks, "expiry")
    assert response["status"] == "matched"
    assert response["reason"] is None
    result = response["results"][0]
    assert result["source_span"]["start"] > 0
    span = result["source_span"]
    assert text[span["start"] : span["end"]] == result["text"]
    assert result["chunk_sha256"] == hashlib.sha256(result["text"].encode()).hexdigest()
    date = result["dates"][0]
    assert date["normalized"] is None
    assert date["candidates"] == ["2026-09-10", "2026-10-09"]
    assert date["review_reasons"] == ["ambiguous_numeric_date"]
    span = date["source_span"]
    assert text[span["start"] : span["end"]] == date["raw_text"] == "09/10/2026"
    assert "not extraction confidence" in response["score_semantics"]
    assert json.loads(json.dumps(response)) == response


def test_per_document_date_policy_is_not_lost_when_indexed():
    chunks = split_chunks("uk", "Expiry: 09/10/2026", date_order="dmy")
    response = RetrievalIndex(chunks).evidence("expiry")
    assert response["results"][0]["date_order"] == "dmy"
    assert response["results"][0]["dates"][0]["normalized"] == "2026-10-09"


@pytest.mark.parametrize(
    "question,top_k,reason",
    [
        ("", 3, "empty_query"),
        ("the date", 3, "empty_query"),
        ("volcano", 3, "no_matching_evidence"),
        ("expiry", 0, "zero_limit"),
    ],
)
def test_explicit_abstention_reasons(question, top_k, reason):
    response = answer_question_json(split_chunks("a", "Expiry: 2028-04-14"), question, top_k)
    assert response["status"] == "abstained"
    assert response["reason"] == reason
    assert response["results"] == []


@pytest.mark.parametrize(
    "question,top_k,error",
    [
        ("x" * 4097, 3, ValueError),
        ("x " * 129, 3, ValueError),
        ("expiry", 101, ValueError),
        (None, 3, TypeError),
        ("expiry", 1.5, TypeError),
        ("expiry", True, TypeError),
    ],
)
def test_query_limits_are_explicit(question, top_k, error):
    with pytest.raises(error):
        RetrievalIndex([]).search(question, top_k)


@pytest.mark.parametrize(
    "kwargs", [{"k1": 0}, {"k1": 4}, {"k1": float("nan")}, {"b": -1}, {"b": 1.1}, {"b": float("inf")}]
)
def test_invalid_ranking_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        BM25Config(**kwargs)


def test_empty_corpus_and_tokenless_chunks_are_valid():
    assert RetrievalIndex([]).search("expiry") == []
    assert RetrievalIndex([DocumentChunk("a", 0, "the and")]).search("expiry") == []


def test_ranking_metrics_have_explicit_denominators_and_deduplicate_documents():
    from pharma_ocr_date_rag.experiments import score_rankings

    metrics = score_rankings([["wrong", "right", "right"], [], ["wrong"]], [["right"], [], []], top_k=3)
    assert metrics["answerable_queries"] == 1
    assert metrics["no_match_queries"] == 2
    assert metrics["hit_at_1"] == 0
    assert metrics["precision_at_k"] == 1 / 3
    assert metrics["recall_at_k"] == 1
    assert metrics["mrr_at_k"] == 0.5
    assert metrics["ndcg_at_k"] == 1 / math.log2(3)
    assert metrics["no_match_abstention_rate"] == 0.5
    assert metrics["false_positive_queries"] == 1
    assert score_rankings([], [])["mrr_at_k"] is None
    with pytest.raises(ValueError):
        score_rankings([[]], [])
    with pytest.raises(ValueError):
        score_rankings([], [], top_k=0)


def test_retrieval_report_matches_authored_inputs_and_preserves_known_failure():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "benchmark_retrieval_quality", root / "scripts/benchmark_retrieval_quality.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.build()
    assert report == json.loads((root / "reports/retrieval_quality.json").read_text())
    for comparison in report["comparisons"].values():
        assert comparison["metrics"]["answerable_queries"] == 12
        assert comparison["metrics"]["no_match_queries"] == 4
        failure = next(q for q in comparison["queries"] if q["id"] == "unknown-vendor-expiry")
        assert failure["relevant_documents"] == []


def test_rare_terms_receive_more_weight_than_common_terms_at_equal_length():
    index = RetrievalIndex(
        [
            DocumentChunk("rare", 0, "quartz sample"),
            DocumentChunk("b", 0, "granite sample"),
            DocumentChunk("c", 0, "granite sample"),
        ]
    )
    result = index.search("quartz granite")
    assert result[0].chunk.doc_id == "rare"
    assert result[0].score > result[1].score


def test_direct_chunks_infer_end_and_reject_false_citations():
    chunk = DocumentChunk("direct", 0, "Expiry: 2028-04-14", start=12)
    assert chunk.end == 12 + len(chunk.text)
    assert RetrievalIndex([chunk]).evidence("expiry")["results"][0]["source_span"] == {
        "start": 12,
        "end": chunk.end,
    }
    with pytest.raises(ValueError, match="chunk span"):
        DocumentChunk("bad", 0, "Expiry: 2028-04-14", start=12, end=13)
    with pytest.raises(ValueError, match="chunk span"):
        DocumentChunk("bad", 0, "text", start=-1)
