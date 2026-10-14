# Evidence retrieval

The project has two local retrieval paths. Neither calls an LLM or sends queries to an external service.

| Path | Indexed unit | Evidence location |
| --- | --- | --- |
| Python `RetrievalIndex` | An exact text chunk | Document ID and Unicode character span |
| Browser evidence search | A batch row from a public notice | Source URL/hash and table/row/column indices |

The indices use different corpora and tokenization rules. Their scores and evaluations are not interchangeable.

## Python index

`split_chunks` retains exact source slices. Word boundaries define chunk size and overlap; these are not model-token limits. Each chunk retains its language and numeric date convention.

`RetrievalIndex` tokenizes each chunk and extracts its dates once. It stores term postings, document frequencies and chunk lengths. Queries traverse matching postings. Shared date-field vocabulary supports queries such as English `expiry` against French date evidence. Recognized date-field queries require an extracted date with the requested label.

Ranking uses positive-IDF BM25:

```text
idf(t) = log(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
score(q,d) = sum over distinct query terms t:
  idf(t) * tf(t,d) * (k1 + 1)
  / (tf(t,d) + k1 * (1 - b + b * length(d) / average_length))
```

Defaults are `k1=1.2` and `b=0.75`. Term saturation limits repetition effects; length normalization accounts for chunk length. See [Elastic's explanation of the BM25 variables](https://www.elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables).

The implementation deduplicates query terms, ranks unrounded scores and uses stable source order to resolve ties. Configuration rejects non-finite values, `k1` outside `(0, 3]`, and `b` outside `[0, 1]`. Queries allow at most 4,096 characters and 128 searchable tokens. The result limit cannot exceed 100.

```python
from pharma_ocr_date_rag.rag import RetrievalIndex, split_chunks

chunks = split_chunks("notice.txt", "Expiry: 09/10/2026")
index = RetrievalIndex(chunks)
response = index.evidence("expiry", top_k=3)
assert response["status"] == "matched"
assert response["results"][0]["dates"][0]["normalized"] is None
# Reuse this index for later queries over the same source snapshot.
```

`retrieve` and `answer_question` remain convenience functions. Each builds an index for one call. Use `RetrievalIndex` for repeated queries to avoid repeated parsing.

## JSON contract

```bash
pharma-date-rag ask data/multilingual_docs --question "expiry" --format json --top-k 3
```

The response has `schema_version: 1`, the original question, the retrieval method, status, reason and a results array. Each result contains:

- Exact chunk text, source identity and start-inclusive/end-exclusive character offsets.
- SHA-256 of the UTF-8 chunk text, matched terms and lexical relevance score.
- Date candidates with absolute document spans, precision, alternatives and review reasons.

The hash identifies the chunk bytes, not the complete source document. Python character offsets count Unicode code points, not UTF-8 bytes. Browser code must account for this distinction when slicing text.

An empty query or absent lexical evidence returns `status: "abstained"` and an empty results array. Scores are not calibrated probabilities. Lexical overlap does not prove that a passage answers every part of a question. No automatic date approval depends on ranking.

## Browser search

The browser groups public date cells by source table row. This keeps a batch's expiry and distribution evidence together. Selecting a result exposes the original cells and source notice. Exported evidence includes the query and source provenance.

Batch identifiers constrain search instead of acting only as ranking hints. A missing batch must not fall back to an unrelated batch with a similar medicine name. Unsupported values and cutoffs remain source evidence; search does not invent a normalized date.

The browser's public snapshot remains separate from synthetic review decisions. A result is not an approval or a statement of current recall status.

## Reproducible evaluation

```bash
uv run python scripts/benchmark_retrieval_quality.py
uv run python scripts/benchmark_retrieval_quality.py --check
```

The checked-in report compares BM25 with the prior term-frequency cosine method. It records per-query rankings, ranking metrics and no-answer behavior. Explicit relevance judgments make failures inspectable. Input and implementation hashes make stale reports detectable.

The current set has 12 answerable queries and four negative queries over four synthetic documents. Both methods have hit@1, MRR@3 and nDCG@3 of 1.0. Recall@3 is 0.9792; one query has four relevant documents but only three result slots. Both methods abstain on three of four negative queries. Both incorrectly retrieve expiry evidence for a nonexistent vendor. This exposes a missing entity-grounding check, not a demonstrated ranking gain.

These are developer-authored development cases. They are not an independent test set, and they do not measure clinical correctness or end-to-end OCR accuracy. The earlier three-question chunk-size experiment remains a compatibility smoke check.

Next evaluation work requires independently judged queries, unseen document templates and broader negative cases. Measure those before claiming that a ranking method generalizes better.
