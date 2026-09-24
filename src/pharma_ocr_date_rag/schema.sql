-- Schema v2: ambiguous dates retain candidates and original source evidence.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    collection TEXT NOT NULL,
    path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    engine TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    indexed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (collection, path, content_sha256, extractor_version)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_version ON documents(collection, path) WHERE active = 1;
CREATE TABLE IF NOT EXISTS date_hits (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    normalized TEXT,
    label TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    context TEXT NOT NULL,
    heuristic_confidence REAL NOT NULL CHECK (heuristic_confidence BETWEEN 0 AND 1),
    candidates_json TEXT NOT NULL DEFAULT '[]',
    precision TEXT NOT NULL DEFAULT 'day',
    review_reasons_json TEXT NOT NULL DEFAULT '[]',
    source_start INTEGER,
    source_end INTEGER
);
CREATE INDEX IF NOT EXISTS hits_document ON date_hits(document_id);
CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY,
    hit_id INTEGER NOT NULL REFERENCES date_hits(id),
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected', 'needs_review')),
    reviewer TEXT NOT NULL CHECK (length(trim(reviewer)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS reviews_hit ON review_events(hit_id, id DESC);
CREATE TRIGGER IF NOT EXISTS reviews_no_update BEFORE UPDATE ON review_events
BEGIN SELECT RAISE(ABORT, 'Review events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS reviews_no_delete BEFORE DELETE ON review_events
BEGIN SELECT RAISE(ABORT, 'Review events are append-only'); END;
CREATE VIEW IF NOT EXISTS review_queue AS
SELECT h.*, d.collection, d.path, d.content_sha256, d.extractor_version,
       COALESCE(r.decision, 'pending') AS decision, r.reviewer, r.reason
FROM date_hits h JOIN documents d ON d.id = h.document_id
LEFT JOIN review_events r ON r.id = (SELECT MAX(id) FROM review_events WHERE hit_id = h.id)
WHERE d.active = 1;
PRAGMA user_version = 2;
