# Command-line workflows

For machine-readable retrieval, use `pharma-date-rag ask data/multilingual_docs --question "expiry" --format json --top-k 3`. The response includes exact source spans, chunk hashes, matched terms and unresolved date alternatives. The result limit accepts 1 through 100. See the [retrieval contract](retrieval.md).


```bash
# Inspect multilingual fields, keeping ambiguous dates unresolved
pharma-date-rag extract data/multilingual_docs

# Export evidence with an explicitly chosen date convention
pharma-date-rag extract data/multilingual_docs --date-order dmy --format json

# Search French date fields with an English field term
pharma-date-rag ask data/multilingual_docs --question "expiry"

# Original English sample demo
python scripts/run_demo.py
```

CSV and JSON use the same extractor records as the demos. JSON retains nulls, candidate lists and original text. CSV prefixes formula-like text cells with an apostrophe for spreadsheet export. Source offsets are zero-based, end-exclusive Unicode character positions in decoded text.

### Mixed document conventions

Folder commands accept `--date-order-map`, a JSON object mapping exact filenames to `auto`, `dmy` or `mdy`. A per-document entry overrides the batch `--date-order`; missing entries inherit it. An explicit `auto` keeps that file's numeric convention unconfirmed, even when the batch default is DMY or MDY. Unknown filenames and malformed maps fail before processing.

```bash
pharma-date-rag extract data/mixed_conventions --date-order-map data/mixed_conventions/date_orders.json --format json
```

In the three authored examples, `09/10/2026` becomes September 10 for one file, October 9 for another, and stays unresolved for the third. The effective setting is visible in reports and exports. The same map works with `ask` and `index`; Streamlit has document-specific controls and a **Mixed conventions** collection. [Policy contract and walkthrough](date-conventions.md).

### Persistent local review

```bash
pharma-date-rag index data/multilingual_docs --db work/reviews.sqlite --collection multilingual
pharma-date-rag queue --db work/reviews.sqlite --label expiry
# Replace 1 with a candidate ID returned by the queue
pharma-date-rag review 1 --db work/reviews.sqlite --decision needs_review --reviewer demo --reason "Confirm source convention"
pharma-date-rag history 1 --db work/reviews.sqlite
```

Indexing the same source and parser settings retains its candidate IDs and decisions. A source or setting change creates a separate version. An unresolved SQL candidate cannot be accepted: confirm the source convention, then reindex with `--date-order dmy` or `mdy`. The browser's local review session and the CLI's SQLite database are separate stores; there is no synchronization or authenticated multi-user service.

Use `documents` to find a document version ID, then `document reopen`, `document retire` or `document restore` with a reviewer and reason. Retirement removes a source from the active queue and blocks re-indexing that collection/filename, even when content changes. Restoration marks every stored field `needs_review`; it does not restore old approvals. Missing files are not automatically retired. [Lifecycle commands and limits](review-lifecycle.md).

The browser's **Reopen document for review** button adds a new decision for every synthetic field after confirmation. Earlier decisions remain in history and session exports. Prior manual date selections are cleared; ambiguous fields need another explicit choice. Source retirement is local SQLite functionality, not a browser or public-notice approval feature.

