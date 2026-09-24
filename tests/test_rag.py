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
