from pharma_ocr_date_rag.rag import retrieve, split_chunks


def test_retrieval_finds_expiry_chunk():
    text = "MFG: 2026-07-10. EXP: 07/2029. Quality review verified on 2026/07/21."
    chunks = split_chunks("sample.txt", text, max_words=8, overlap=2)
    results = retrieve(chunks, "expiry date", top_k=1)
    assert results
    assert any(hit.label == "expiry" for hit in results[0].dates)
