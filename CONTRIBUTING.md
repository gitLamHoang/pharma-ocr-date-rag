# Contributing

Start with the README's browser demo. Quality checks use Python 3.12; compatibility tests also run on Python 3.9 and 3.11.

```bash
uv sync --frozen --python 3.12 --extra dev --extra demo --extra research
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python scripts/export_evidence.py --check
uv run python scripts/benchmark_multilingual.py --check
uv run python scripts/export_web.py --check
uv run python scripts/benchmark_ocr.py --check-report
uv run python scripts/train_mhra.py --check
uv run python scripts/benchmark_mhra_pdf.py --check-report
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

Keep synthetic samples labeled. Real documents must come from reusable public sources with provenance and attribution; follow the [public-data protocol](docs/public-data.md). Do not add private personal, customer, employer or patient documents. Database files, original PDF downloads and fitted model files stay outside Git. Never silently replace the frozen public benchmark with a fresh crawl.

For an extraction change, add a focused example that demonstrates the failure, inspect old and new fixture results, regenerate the evidence, and describe what changed. A perfect fixture score is not a real-world accuracy claim. For a persisted extraction change, bump `EXTRACTOR_VERSION` in `review.py`; otherwise existing content hashes intentionally reuse earlier candidates.

After Python formatting, regenerate in this order:

```bash
python scripts/benchmark_multilingual.py --json --output docs/benchmark_results.json
python scripts/export_evidence.py
python scripts/export_web.py
```

The public snapshot hashes Python source, so unrelated formatting changes also require regeneration. If source text or date positions change, rerender pages first with `python scripts/export_web.py --render --font /path/to/unicode-font.ttf` (requires Pillow). The checked-in pages use Arial. Font choice affects pixels and boxes; image hashes make that visible, and CI does not pretend every font produces byte-identical images. The viewer's rectangles represent known fixture layout, not model-detected OCR boxes.

The separate [image-OCR experiment](docs/image-ocr.md) hashes its three parser/adapter modules, scripts, models manifest and inputs. When those change, install the `tesseract` extra and native executable, fetch the pinned packs, then rerun `python scripts/benchmark_ocr.py --require-complete`. Review the measured report and update the documented results. `--check-report` only rescores saved OCR text; it is not a new engine measurement. The image-OCR CI job performs fresh recognition and uploads its own report, without overwriting the checked-in macOS measurement.

For database changes, preserve existing review history, add a schema migration, and test upgrades and rollback behavior. Never rewrite an earlier decision to represent a later decision; append a review event.

Public-data reports hash their dataset, labels, protocol and implementation. After relevant edits and formatting, rerun `python scripts/train_mhra.py` with the `research` extra, inspect the comparison, and rerun the original PDF experiment when its hashed sources change. `--check` retrains from frozen data; the PDF `--check-report` only verifies saved transcripts. CI must never crawl fresh data to obtain a passing benchmark.

Small contributions with a concrete failing example are easiest to review. Useful next steps include explicit review cycles, broader image-OCR coverage and a bounded independently labeled test set.
