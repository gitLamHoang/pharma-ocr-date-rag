# Two-Minute Demo

## Run

Open the [public browser workspace](https://gitlamhoang.github.io/pharma-ocr-date-rag/). No installation is needed. All documents are synthetic fixtures.

## Show

1. Start in Document review. The French audit field is selected and highlighted on its rendered source page. The source says `09/10/2026`; both September 10 and October 9 remain possible.
2. Enter a review note and try Accept without selecting an interpretation. The app prevents an unresolved acceptance. For this demonstration, choose `2026-10-09` and record that the convention was manually selected, not inferred from French.
3. Open Review history. The decision includes the reason, reviewer label, timestamp and source hash. Reload to show local persistence; explain that this is browser storage, not a shared server.
4. Open Date register. Filter to French and Expiry, then search for `expiry`. English field terminology finds the French evidence while leaving the source text unchanged.
5. Search for `astronomy`. There is no matching result; the app does not fill the space with unrelated evidence. Clear the filters and export CSV.
6. Open Benchmark lab. Select Vietnamese and inspect six individual cases. Both vocabulary modes pass the authored fixtures, but this is not a claim about unseen documents or image OCR.
7. Export the session JSON. Point to original text, source spans, hashes, candidates and review events.

For a local extraction demo, run Streamlit using the README commands. Paste synthetic text or select a sample collection, change language/date-order settings, and inspect the recomputed results. Unlike the static browser workspace, this invokes Python on new text.

## Explain the Engineering

A useful explanation, in your own words:

"I started with a document-review problem: one file can contain several dates with different meanings. This public prototype creates a date register with source evidence. The hardest part is deciding what not to normalize automatically. For an ambiguous date, it preserves alternatives until the reviewer supplies a convention."

Then explain the trade-off:

"The current core is deterministic and runs locally. That makes errors easier to reproduce, but its vocabulary and layout coverage are limited. The multilingual tests are synthetic development examples. My next step is to test actual image OCR and a more challenging retrieval dataset."

Be ready to explain how the parser distinguishes month precision from a complete date, why language and date order are separate settings, and why a perfect score on 42 authored cases is not a real-world accuracy claim.

## Evidence You Can Point To

- scripts/benchmark_multilingual.py and data/multilingual_cases.json
- docs/benchmark_results.json, including the fixture hash
- tests/test_multilingual.py for source positions and ambiguity
- tests/test_demo.py for real app-state interactions
- web/scripts/browser-smoke.mjs for production-browser flows and responsive checks
- tests/test_review.py for document versions, append-only SQL history and migration rollback
- GitHub Actions test results and the normal commit history

This repository was developed with AI coding assistance. Review the implementation and run the examples before discussing technical ownership. Separate this public synthetic reconstruction from any original employer work. Do not present future milestones as finished or synthetic scores as employer results.
