# Contributing

Start with the README's browser demo. Quality checks use Python 3.12; compatibility tests also run on Python 3.9 and 3.11.

```bash
uv sync --frozen --python 3.12 --extra dev --extra demo
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python scripts/export_evidence.py --check
uv run python scripts/benchmark_multilingual.py --check
uv run python scripts/export_web.py --check
```

Browser development requires Node 24.12+:

```bash
cd web
npm ci
npm run format:check
npm test
npm run build
npx playwright install chromium
npm run test:browser
```

The browser test launches a production preview on port 4174. Set `WEB_BASE_URL` to test an already running server instead, or `BROWSER_CHANNEL=chrome` to use an installed Chrome. Screenshots go to ignored `web/test-results/`; set `SCREENSHOT_DIR=../docs/images` only when intentionally updating documentation screenshots. Saved review events created by the test stay in its isolated browser context.

Keep sample documents synthetic and label them as such. Do not add personal, customer, employer, or patient documents. Database files and build artifacts stay outside Git.

For an extraction change, add a focused example that demonstrates the failure, inspect old and new fixture results, regenerate the evidence, and describe what changed. A perfect fixture score is not a real-world accuracy claim. For a persisted extraction change, bump `EXTRACTOR_VERSION` in `review.py`; otherwise existing content hashes intentionally reuse earlier candidates.

After Python formatting, regenerate in this order:

```bash
python scripts/benchmark_multilingual.py --json --output docs/benchmark_results.json
python scripts/export_evidence.py
python scripts/export_web.py
```

The public snapshot hashes Python source, so unrelated formatting changes also require regeneration. If source text or date positions change, rerender pages first with `python scripts/export_web.py --render --font /path/to/unicode-font.ttf` (requires Pillow). The checked-in pages use Arial. Font choice affects pixels and boxes; image hashes make that visible, and CI does not pretend every font produces byte-identical images. The viewer's rectangles represent known fixture layout, not model-detected OCR boxes.

For database changes, preserve existing review history, add a schema migration, and test upgrades and rollback behavior. Never rewrite an earlier decision to represent a later decision; append a review event.

Small contributions with a concrete failing example are easiest to review. Useful next steps include explicit review cycles, real image OCR evaluation and a bounded independently labeled test set.
