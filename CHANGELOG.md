# Changelog

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
