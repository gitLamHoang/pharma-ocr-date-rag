# Architecture and engineering decisions

## One reviewable evidence trail

`pipeline.py` reads text or calls an optional OCR adapter, extracts dates with original nearby context, and constructs chunks. `rag.py` ranks chunks with term-frequency cosine similarity plus shared date-field vocabulary matches across languages. Zero-overlap chunks are excluded. It returns source text rather than generating a free-form answer.

`review.py` uses parameterized queries against the packaged [`schema.sql`](../src/pharma_ocr_date_rag/schema.sql). The database contains:

| Relation | Responsibility |
|---|---|
| `documents` | Source collection, filename, SHA-256, extractor version, OCR engine, indexing time, active flag |
| `date_hits` | Candidates attached to one immutable-in-application document version |
| `review_events` | Ordered decisions with reviewer label, reason, UTC timestamp |
| `review_queue` | Active candidates joined to their latest decision, or `pending` |

A partial unique index enforces one active document version per `(collection, path)`. Candidate and event indexes support joins and latest-decision lookups. Queue results have deterministic ID ordering and bounded pagination. SQL column names come from a fixed allowlist, and user values are bound parameters.

## Version and review semantics

A version is `(collection, filename, content SHA-256, extractor version)`. The stored extractor identity combines a manually maintained semantic version with language and date-order settings. Bump the semantic version when extraction semantics or OCR configuration change. The stored OCR engine identifies what produced the candidates; it does not automatically detect every change in an optional OCR package.

- An identical active version is skipped, preserving candidate IDs and reviews.
- Changed content creates a new document version and deactivates the previous one.
- Reverting to an already indexed version reactivates its earlier candidates **and earlier decisions**. This is deliberate reuse of identical evidence, not a fresh approval. Callers needing a new review cycle must append `needs_review` decisions.
- Old version history remains queryable by hit ID. The review command rejects new decisions on inactive versions.
- Missing files are not interpreted as deletions. The active queue is an index, not proof that every source file is still present.
- Omitted collection names default to the folder's basename. Supply distinct explicit names when basenames overlap.

An indexing transaction uses `BEGIN IMMEDIATE`; either every supported file in the folder is indexed or none of that batch's document changes persist. Content is hashed before extraction and rechecked afterward to catch a source changed during processing. Files should remain stable during indexing. Schema creation may persist even when a batch fails, leaving an empty database.

Review events are append-only through both the API and update/delete rejection triggers. Later decisions supersede earlier ones in the queue without replacing history. Local reviewer names are labels, not authenticated identities. These controls are not a tamper-proof or regulatory audit system.

New extraction records preserve original text, character offsets and context even when date tokens are repaired. They also retain null normalized values, alternative candidates, precision and review reasons. Schema v2 migrates v1 candidates without renumbering IDs or deleting decisions, marks old evidence as `legacy_extraction`, and leaves unavailable source offsets null. Migration statements run inside one explicit transaction, followed by foreign-key validation; an interrupted migration rolls back. Tests exercise both successful migration and rollback.

## Browser and local UI boundary

The TypeScript/Vite app has four views: document review, date register, benchmark lab and review history. `scripts/export_web.py` runs the Python extractor against the eight public fixtures and exports exact source text, field spans, alternatives, input hashes and parser-source hashes. Its `--check` mode fails if the committed browser evidence is stale.

Pillow optionally renders source-page PNGs from those text fixtures using a supplied Unicode font. Highlight rectangles are computed from source offsets and font metrics. They are not OCR predictions. CI verifies PNG hashes, source spans and snapshot reproducibility without requiring Pillow. A browser smoke test loads every image, checks desktop/mobile layouts, and exercises selection, ambiguity, persistence, filtering and downloads.

Browser reviews are append-only through the UI and kept in localStorage. Loading ignores decisions for other source hashes or extractor versions. This is client-side convenience, not secure storage. The static app has no server, uploads, live OCR, user accounts or connection to SQLite. Streamlit remains the local sandbox for running the extractor on new synthetic text. A future service must define identity and conflict semantics before connecting these stores.

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

Chunks obey bounded word counts and exact overlap-word counts. Each chunk retains an original text slice and its start/end offsets. These are word budgets, not model-token budgets. A boundary can still split a contextual field, and three benchmark questions are insufficient to choose a general optimum.

The checked-in report records hashes of fixture files and relevant Python source. CI verifies the report matches the current code and input bytes. To intentionally update it, run `uv run python scripts/export_evidence.py`, inspect the differences, and explain changes in the changelog.
