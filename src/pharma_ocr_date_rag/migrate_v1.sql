-- Caller holds a write transaction and temporarily disables FK enforcement.
-- Preserve candidate IDs so existing review events keep their original targets.
DROP VIEW IF EXISTS review_queue;
CREATE TABLE date_hits_v2 (
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
INSERT INTO date_hits_v2 (
    id, document_id, normalized, label, extracted_text, context, heuristic_confidence,
    precision, review_reasons_json
)
SELECT id, document_id, normalized, label, extracted_text, context, heuristic_confidence,
       CASE WHEN length(normalized) = 7 THEN 'month' ELSE 'day' END,
       '["legacy_extraction"]'
FROM date_hits;
DROP TABLE date_hits;
ALTER TABLE date_hits_v2 RENAME TO date_hits;
