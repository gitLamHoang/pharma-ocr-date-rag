# Contributing

Start with the README's local demo. Python 3.12 is the CI runtime.

```bash
uv sync --frozen --python 3.12 --extra dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python scripts/export_evidence.py --check
```

Keep sample documents synthetic and label them as such. Do not add personal, customer, employer, or patient documents. Database files and build artifacts stay outside Git.

For an extraction change, add a focused example that demonstrates the failure, inspect old and new fixture results, regenerate `reports/synthetic_evaluation.json`, and describe what changed. A perfect fixture score is not a real-world accuracy claim. For a persisted extraction change, bump `EXTRACTOR_VERSION` in `review.py`; otherwise existing content hashes intentionally reuse earlier candidates.

For database changes, preserve existing review history, add a schema migration, and test upgrades and rollback behavior. Never rewrite an earlier decision to represent a later decision; append a review event.

Small contributions with a concrete failing example are easiest to review. The next useful work is an explicit review-cycle model or a bounded, independently labeled evaluation set—not adding a model provider before the retrieval baseline is understood.
