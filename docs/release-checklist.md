# October 2 Release Check

This closes the application sprint on October 2, 2026, America/Los_Angeles. It records verified behavior, not a clinical release or a claim that every proposed feature shipped.

## Share and Demonstrate

- [Repository](https://github.com/gitLamHoang/pharma-ocr-date-rag)
- [Public-notice demo](https://gitlamhoang.github.io/pharma-ocr-date-rag/#recalls)
- [Synthetic review demo](https://gitlamhoang.github.io/pharma-ocr-date-rag/#workspace)
- [Detailed walkthrough](demo_walkthrough.md) and [portfolio explanation](portfolio-guide.md)

For a short demonstration:

1. Search public batch `0162858`, select Expiry, and inspect `05/2028` beside its source row. Explain why the month has no invented day.
2. Filter to Expiry cutoff, then Distribution statement. These are bounds or source statements, not exact dates.
3. Open Document review. Select an interpretation of the synthetic French audit date and record a reason.
4. Reopen the document for review. The earlier decision remains in history, but the ambiguous date needs a fresh choice.
5. Export the evidence and explain the model comparison: keyword rules tie the classifier on these repeated templates.

Public notices are a September 26 snapshot, not current recall advice. Browser decisions apply only to synthetic examples and remain in local storage.

## Verification Results

The final local check used a new locked Python 3.12.13 environment with development, demo, research and Tesseract extras. The frontend used a fresh `npm ci` installation with Node 24.

| Check | Observed result | Boundary |
| --- | --- | --- |
| Python tests | 275 passed | Includes Streamlit interactions and eight new verifier tests |
| Python 3.9 compatibility | 270 passed, 5 skipped | Optional research dependencies absent in that environment |
| Frontend | 17 unit tests, type check and production build passed | Static browser app, not live OCR |
| Browser walkthrough | Desktop/mobile flows passed | Source assets, filters, exports, history, re-review and storage failure |
| Installed wheel | Six check groups passed in a fresh temporary environment | Installed CLI and bundled SQL; no optional runtime dependencies |
| English text extraction | 18/18 unique field tuples | Four authored synthetic documents |
| Five-language parser | 42/42 cases in each of two modes | Authored development regressions |
| Retrieval | 3/3 at each of 35, 60 and 90 words | Existing synthetic smoke questions only |
| Public schema model | 80/80 test roles; rules also 80/80 | 76/80 headings repeat training templates |
| Conditional source cells | 6/6 cases | AI-assisted development cases, not independent gold |
| Fresh synthetic image OCR | Clean 16/16; degraded 8/16 with 4 extras | Three pages, two render conditions |
| Fresh original-PDF OCR | OCR and native text each recover 11/11 interpretations | First two pages of three PDFs; coverage, not overall accuracy |

Ruff, formatting and all saved-evidence checks passed. Corpus bytes, model split, parsing logic and checked-in measurements are unchanged. Fresh OCR reports remain separate under ignored `outputs/`; they reproduce the reported counts without replacing frozen evidence.

A negative installation probe removed `schema.sql` from a temporary copy of the wheel. Verification returned exit code 1 and a failed report, identifying the missing installed resource. The valid package passed. No broken artifact is committed or distributed.

## Reproduce

```bash
uv sync --frozen --python 3.12 --extra dev --extra demo --extra research --extra tesseract
uv run pytest -q
uv run python scripts/evaluate.py
uv run python scripts/benchmark_multilingual.py --check
uv run python scripts/benchmark_retrieval.py
uv run python scripts/train_mhra.py --check
uv run python scripts/benchmark_cells.py --check
uv run python scripts/export_evidence.py --check
uv run python scripts/export_web.py --check
uv run python scripts/benchmark_ocr.py --check-report
uv run python scripts/benchmark_mhra_pdf.py --check-report

uv build --wheel --out-dir outputs/wheel
uv run --no-project --python 3.12 python scripts/verify_wheel.py outputs/wheel/*.whl

cd web
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:browser
```

Keep one wheel in `outputs/wheel`. The verifier runs on macOS/Linux and requires the checkout's synthetic input fixtures. It installs into a temporary directory, uses isolated Python imports, checks the installed module location and invokes the installed CLI. It does not use pytest's source-path configuration. The six groups cover installation, conventions/source spans, repeat indexing, lifecycle history, and both legacy schema upgrades.

The verification report records the wheel hash, fixture/script hashes, actual time, Python version, check names and success/failure. The `installed-wheel` CI job uploads the report and wheel together. Rebuilt wheels can differ in bytes; compare their verified behavior and their own recorded hashes, not an assumed universal binary hash.

Saved OCR checks do not execute recognition. Fresh runs need a native Tesseract executable and the pinned language packs. Follow the [image protocol](image-ocr.md) and [original-PDF commands](public-data.md#reproduce). Use `BROWSER_CHANNEL=chrome npm run test:browser` for an installed Chrome browser. Set `WEB_BASE_URL=https://gitlamhoang.github.io/pharma-ocr-date-rag/` to check the hosted app.

## Unfinished Work

No new retrieval comparison shipped after September 28. The proposed real-corpus TF-IDF retrieval experiment remains deferred. There is no Mistral/Phi-2 benchmark, LlamaIndex integration, OCR fine-tuning or independent date annotation study. Real public examples remain English; multilingual evaluation remains synthetic.

No separate September 29, September 30 or October 1 milestone commit was created. The final installation rehearsal took place on October 2. Planned sessions are not evidence of work that did not ship.

The project does not establish clinical safety, production deployment, customer demand, time savings or Pfizer endorsement. It is an AI-assisted public research prototype. Be ready to explain the code and the evaluation limits rather than presenting a perfect template score as general accuracy.

The strongest explanation point is concrete: preserving source evidence, uncertainty and review history is useful even when a learned model adds no measured advantage over rules.
