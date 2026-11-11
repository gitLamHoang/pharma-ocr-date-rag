-- Store schema (spec §5.6). Applied on every open; every statement is idempotent.

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    pages INTEGER NOT NULL,
    status TEXT NOT NULL,  -- status of the latest run
    created_at TEXT NOT NULL,
    ai_model TEXT,  -- of the latest run
    pipeline_version TEXT  -- of the latest run
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents (id),
    pipeline_version TEXT NOT NULL,
    ai_model TEXT,
    ai_used INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('queued', 'reading', 'classifying', 'validating', 'done', 'failed')),
    error TEXT
);
CREATE INDEX IF NOT EXISTS runs_document ON runs (document_id);

CREATE TABLE IF NOT EXISTS pages (
    run_id INTEGER NOT NULL REFERENCES runs (id),
    document_id INTEGER NOT NULL REFERENCES documents (id),
    n INTEGER NOT NULL,
    image_path TEXT,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_source TEXT NOT NULL,
    words_json TEXT NOT NULL,
    transcription TEXT,
    PRIMARY KEY (run_id, n)
);

CREATE TABLE IF NOT EXISTS dates (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs (id),
    document_id INTEGER NOT NULL REFERENCES documents (id),
    candidate_id TEXT NOT NULL,  -- the pipeline's id, unique within a run
    page INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    normalized TEXT,
    candidates_json TEXT NOT NULL,
    precision TEXT NOT NULL,
    date_type TEXT NOT NULL,
    family TEXT NOT NULL,
    qualifier TEXT,
    resolved_value TEXT,
    evidence TEXT,
    bbox_json TEXT,
    line_boxes_json TEXT,  -- JSON list of boxes, one per printed line; NULL or [] on one line
    source TEXT NOT NULL CHECK (source IN ('rules', 'ai_only', 'rules+ai')),
    confidence REAL NOT NULL,
    rationale TEXT,
    context TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    rule_label TEXT NOT NULL,
    UNIQUE (run_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs (id),
    document_id INTEGER NOT NULL REFERENCES documents (id),
    date_ids TEXT NOT NULL,  -- JSON list of dates.id
    rule TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS flags_run ON flags (run_id);

-- AI suggestions that failed verification: shown only in a debug list, never as dates.
CREATE TABLE IF NOT EXISTS discarded (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs (id),
    page INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS discarded_run ON discarded (run_id);

CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES dates (id),
    action TEXT NOT NULL CHECK (action IN ('accept', 'correct', 'reject', 'reopen')),
    new_type TEXT,
    new_value TEXT,
    reviewer TEXT NOT NULL,
    reason TEXT NOT NULL,
    at TEXT NOT NULL,
    carried_from_run INTEGER REFERENCES runs (id)
);
CREATE INDEX IF NOT EXISTS review_events_date ON review_events (date_id, id);

CREATE TRIGGER IF NOT EXISTS review_events_no_update BEFORE UPDATE ON review_events
BEGIN
    SELECT RAISE(ABORT, 'review_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS review_events_no_delete BEFORE DELETE ON review_events
BEGIN
    SELECT RAISE(ABORT, 'review_events is append-only');
END;
