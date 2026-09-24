import pytest

from pharma_ocr_date_rag.experiments import RetrievalCase, evaluate_chunk_sizes
from pharma_ocr_date_rag.pipeline import process_folder
from pharma_ocr_date_rag.rag import retrieve, split_chunks


def test_retrieval_finds_expiry_chunk():
    text = "MFG: 2026-07-10. EXP: 07/2029. Quality review verified on 2026/07/21."
    chunks = split_chunks("sample.txt", text, max_words=8, overlap=2)
    results = retrieve(chunks, "expiry date", top_k=1)
    assert results
    assert any(hit.label == "expiry" for hit in results[0].dates)


def test_chunk_benchmark_scores_known_sample_cases():
    docs = process_folder("data/synthetic_docs")
    cases = [
        RetrievalCase(
            question="Which document mentions the expiry date for the Delta cold chain vendor?",
            expected_doc="delta_noisy_scan.txt",
            expected_label="expiry",
        ),
        RetrievalCase(
            question="When was the supplier audit planned?",
            expected_doc="beta_excipient_report.txt",
            expected_label="audit",
        ),
    ]

    rows = evaluate_chunk_sizes(docs, cases, chunk_sizes=[35], top_k=3)
    assert rows[0].hits == 2
    assert rows[0].hit_rate == 1.0


def test_english_query_retrieves_french_date_evidence():
    chunks = split_chunks("fr.txt", "Date de péremption: 28 février 2028")
    results = retrieve(chunks, "expiry")
    assert results[0].dates[0].normalized == "2028-02-28"


def test_unrelated_empty_or_zero_limit_queries_do_not_return_evidence():
    chunks = split_chunks("one.txt", "Expiry: 2028-04-14")
    assert retrieve(chunks, "astronomy") == []
    assert retrieve(chunks, "") == []
    assert retrieve(chunks, "expiry", top_k=0) == []


def test_chunk_word_limit_overlap_and_original_source_slices():
    text = "\n".join(f"word{i}" for i in range(20))
    chunks = split_chunks("source.txt", text, max_words=8, overlap=2)
    assert [len(chunk.text.split()) for chunk in chunks] == [8, 8, 8]
    assert chunks[0].text.split()[-2:] == chunks[1].text.split()[:2]
    for chunk in chunks:
        assert text[chunk.start : chunk.end] == chunk.text


@pytest.mark.parametrize("max_words,overlap", [(0, 0), (8, 8), (8, -1)])
def test_invalid_chunk_settings_are_rejected(max_words, overlap):
    with pytest.raises(ValueError):
        split_chunks("test.txt", "some text", max_words=max_words, overlap=overlap)
