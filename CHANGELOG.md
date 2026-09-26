# Changelog

## 2026-09-26 - Real public notices, training and source-linked UI

- Collected 60 real public MHRA recall/defect notices through bounded, robots-aware official API requests. Published attributed batch-table excerpts, explicit heading labels and a fixed evaluation protocol, with source hashes and OGL licence boundaries.
- Trained a character TF-IDF/logistic-regression column classifier on 36 documents (182 examples), reserving 12 documents each for validation/test. Test roles score 80/80, tied by keyword rules; 76 test heading instances repeat training templates. No advantage over rules or trained OCR is claimed.
- Added 742 source-linked date-column candidates, including 123 ambiguous and 80 unparsed/non-date cells. Added a default public-notice UI with batch search, source rows, dataset-split filters, pagination and exports; kept the synthetic multilingual review flow separate.
- Measured actual OCR and native extraction on three original public PDF attachments / six pages. Both recover 11/11 supported unique HTML date interpretations. Saved transcripts and exclusions; tests verify selection, references and rescored coverage. This is not full-document accuracy or independent date gold.
- Added 34 Python tests (233 total with research/demo dependencies) and three TypeScript tests (12 total), plus desktop/mobile production-browser flows. Added offline training reproduction to CI and a dataset/model card with honest baselines, reuse terms and remaining gaps.

## 2026-09-26 - Measured multilingual image OCR

- Added explicit Tesseract language packs, page segmentation, language-directory selection and recognition timeout, with separate unavailable/execution errors and image cleanup. Plain text remains dependency-free; a small `tesseract` extra is available independently of PaddleOCR.
- Added a reproducible six-input experiment using three manually annotated synthetic pages and three pinned, checksum-verified upstream language packs. Clean image OCR recovered 16/16 fields; degraded image OCR recovered 8/16 with four extra predictions. All six recognizer runs completed. This is controlled development evidence, not general vendor-scan accuracy.
- Preserved raw OCR text, field evidence, errors, settings, environment details and hashes in `reports/image_ocr.json`. Added saved-report verification and a separate CI image-OCR job with a downloadable report.
- Added 43 regression tests; all 199 Python tests pass on Python 3.9 and a fresh Python 3.12 environment. Repeated native image measurements had the same field counts in both environments. Nine TypeScript tests, production build, formatting, source-evidence checks and desktop/mobile browser flows pass.
- Documented valid-looking wrong-date failures, measured scope and setup. The hosted browser remains a text-backed snapshot; PaddleOCR, German/Spanish image OCR, real scans and model comparisons remain unverified.

## 2026-09-25 - Per-document numeric date conventions

- Added validated filename-to-order JSON maps to `extract`, `ask` and `index`. Each document can use DMY, MDY or unconfirmed interpretation; missing entries inherit the batch default.
- Added local Streamlit controls for individual sample-document conventions, session persistence/reset, and visible effective settings. CSV/JSON and retrieval use the same selected policy.
- Added three synthetic mixed-convention fixtures. Five of eight candidates are ambiguous under the unconfirmed default; one remains ambiguous with the explicit authored policies. Impossible full dates do not leak valid suffixes, and month precision stays month-only.
- Preserved SQLite version identity based on effective settings: only changed documents are reindexed, equivalent settings reuse reviews, older decisions remain in history, and a failed batch rolls back.
- Added 30 regression tests covering policy parsing, duplicate/stale entries, CLI commands, source/export/retrieval consistency, database behavior and UI switching/reset. All 156 Python tests pass in Python 3.9 and a fresh locked Python 3.12 environment; nine browser unit tests and production-browser checks pass.
- Original authored benchmarks are unchanged: 18/18 English field tuples, 42/42 multilingual cases in each mode, and 3/3 retrieval questions at each word budget. No new image-OCR or model-performance claim is made.

## 0.3.0 - 2026-09-24 - Multilingual browser workspace

- Added a TypeScript/Vite review application with rendered source pages, clickable evidence highlights, zoom/text views, field interpretation, reasoned decisions, local history, a filterable register and benchmark lab.
- Added English, French, German, Spanish and Vietnamese date vocabularies; explicit numeric conventions, alternative candidates, precision and review reasons; preserved source text and offsets through scoped OCR repair.
- Added source-preserving word-budget retrieval, cross-language date-field terminology and no-match behavior. The current three-question smoke experiment scores 3/3 at 35, 60 and 90 words; this supersedes the earlier line-chunking result below.
- Integrated the existing SQLite workflow with ambiguous candidates and language/date-order version identity. Added a transactional v1-to-v2 migration preserving candidate IDs and review history, with success and rollback tests.
- Added a local Streamlit extraction sandbox for new synthetic UTF-8 text, source-backed CSV/JSON, and hashed browser evidence generated from the Python pipeline.
- Measured 42/42 authored multilingual development cases in both language modes; original English fixtures remain 18/18 unique field records. These are not held-out or image-OCR accuracy measurements.
- Added nine browser unit tests and end-to-end desktop/mobile checks covering all eight rendered page assets, ambiguity validation, persistent local reviews, filtering, JSON/CSV downloads and benchmark views.
- Validation: 126 Python tests passed on both the existing Python 3.9 environment and a fresh locked Python 3.12 environment with demo dependencies. Ruff passed; a built wheel indexed four multilingual documents and 24 fields from an isolated environment.
- Documented the product hypothesis, architecture, public-project boundaries and daily release roadmap. No trained model, live browser OCR, LlamaIndex index or Mistral/Phi-2 comparison is claimed.

## 2026-09-24 — Persistent document review and reproducible evidence

- Added a SQLite-backed local review workflow: `index`, `queue`, `review`, and `history` commands with JSON output.
- Added content-addressed document versions, collection separation, one active source version, idempotent indexing, bounded queue pagination, and append-only decision events.
- Added atomic batch rollback and source-change detection; rejected review decisions on inactive versions and surfaced database errors as CLI usage errors.
- Packaged the SQL schema, locked dependencies, added pytest/Ruff CI and source-hashed synthetic evidence checks, and documented the local scaling boundary.
- Measured 18/18 expected date tuples on four synthetic text fixtures (precision/recall/F1 1.00). The fixtures are development examples, not held-out accuracy evidence.
- Measured retrieval top-three hits of 2/3 at a 35-word chunk target and 3/3 at 60 and 90. Shorter context failed one query; three queries cannot establish a general optimum.
- Verified a real CLI run: four documents produced 18 candidates; after reviewing an expiry candidate, reindexing produced zero new candidates and preserved the decision.
- Validation: 19 pytest tests passed; Ruff check and format passed; source distribution and wheel built successfully. A fresh isolated wheel installation indexed all four documents and 18 candidates, verifying the packaged `schema.sql`.

Next: measure reviewer usefulness on an independently labeled, consented dataset; keep production, compliance, and time-savings claims out until independently supported.
