# Architecture and engineering decisions

## One reviewable evidence trail

`pipeline.py` reads text or calls an optional OCR adapter, extracts dates with nearby context, and constructs chunks. `rag.py` ranks chunks with term-frequency cosine similarity and a small date-presence bonus. It returns source text rather than generating a free-form answer.

`review.py` uses parameterized queries against the packaged [`schema.sql`](../src/pharma_ocr_date_rag/schema.sql). The database contains:

| Relation | Responsibility |
|---|---|
| `documents` | Source collection, filename, SHA-256, extractor version, OCR engine, indexing time, active flag |
| `date_hits` | Candidates attached to one immutable-in-application document version |
| `review_events` | Ordered decisions with reviewer label, reason, UTC timestamp |
| `review_queue` | Active candidates joined to their latest decision, or `pending` |

A partial unique index enforces one active document version per `(collection, path)`. Candidate and event indexes support joins and latest-decision lookups. Queue results have deterministic ID ordering and bounded pagination. SQL column names come from a fixed allowlist, and user values are bound parameters.

## Version and review semantics

A version is `(collection, filename, content SHA-256, extractor version)`. The extractor version is a manually maintained constant and must change when extraction semantics or OCR configuration change. The stored OCR engine identifies what produced the candidates; it does not automatically detect every change in an optional OCR package.

- An identical active version is skipped, preserving candidate IDs and reviews.
- Changed content creates a new document version and deactivates the previous one.
- Reverting to an already indexed version reactivates its earlier candidates **and earlier decisions**. This is deliberate reuse of identical evidence, not a fresh approval. Callers needing a new review cycle must append `needs_review` decisions.
- Old version history remains queryable by hit ID. The review command rejects new decisions on inactive versions.
- Missing files are not interpreted as deletions. The active queue is an index, not proof that every source file is still present.
- Omitted collection names default to the folder's basename. Supply distinct explicit names when basenames overlap.

An indexing transaction uses `BEGIN IMMEDIATE`; either every supported file in the folder is indexed or none of that batch's document changes persist. Content is hashed before extraction and rechecked afterward to catch a source changed during processing. Files should remain stable during indexing. Schema creation may persist even when a batch fails, leaving an empty database.

Review events are append-only through both the API and update/delete rejection triggers. Later decisions supersede earlier ones in the queue without replacing history. Local reviewer names are labels, not authenticated identities. These controls are not a tamper-proof or regulatory audit system.

Extraction context may include repaired OCR tokens. It is not a page bounding box or a byte-exact quotation of the original image. Keep the original document available for actual review.

## Scaling boundary

The current design is intended for a local, single-writer prototype. WAL mode lets readers coexist with a writer; the connection waits up to ten seconds for a lock. SQLite remains a single-writer database, and this implementation holds its transaction while processing a batch. Large or slow OCR batches would delay other writes. Offset pagination is appropriate for small local queues, not a large concurrently changing service.

The next scale step should be driven by measured queue size, indexing latency, and reviewer needs:

1. Store source documents in object storage and submit content-addressed extraction jobs to a worker queue.
2. Extract before taking the database write lock; validate content identity again at commit.
3. Move the relational schema to PostgreSQL when multiple writers or service operations require it; use keyset pagination and explicit migration scripts.
4. Add authenticated reviewer identity, collection authorization, retention controls, and a review-cycle entity before sharing real documents.
5. Measure queue latency, extraction failure rate, reviewer correction rate, and time to review before selecting further components.

None of these scale steps has been implemented or load-tested. The repository avoids claiming a throughput number without a workload measurement.

## Evaluation boundaries

The public data is a developer-authored synthetic fixture set. Extraction scoring uses sets of unique `(document, date, label)` tuples; repeated occurrences of the same tuple count once. Retrieval scoring tests whether a top-three chunk has both the expected document and date label; it does not verify the exact answer, causal usefulness, or safe reviewer behavior.

Chunk targets are word-count thresholds over lines. The current chunker preserves lines and carries over up to two lines; a long line can exceed the target. The chunk benchmark is not a fixed-token ablation, and the `overlap` parameter currently controls whether line overlap is enabled rather than an exact overlap-word count.

The checked-in report records hashes of fixture files and relevant Python source. CI verifies the report matches the current code and input bytes. To intentionally update it, run `uv run python scripts/export_evidence.py`, inspect the differences, and explain changes in the changelog.
