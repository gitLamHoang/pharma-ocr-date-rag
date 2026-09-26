# Daily Development Roadmap

Sprint: September 24 through October 2, 2026. Application deadline: October 3.

Each date is a planned work session, not a promise that an untested feature already exists. Priorities may change when a regression or installation problem is found. Each session should ship a useful tested change and record the actual result here.

## Delivered: September 24

- Five-language text date extraction: English, French, German, Spanish and Vietnamese.
- Explicit numeric date-order policy, alternative candidates and review reasons.
- Original source text and positions preserved through OCR repair.
- Review workspace with filters, highlighted evidence, pasted/uploaded text, and CSV/JSON.
- Cross-language date-field vocabulary for lexical retrieval, no-match responses and bounded word chunking.
- 42 authored benchmark cases in two language modes; all cases pass.
- Custom TypeScript browser workspace: source-page highlights, field inspector, per-field interpretation, reasoned review decisions, local history, date register and benchmark lab.
- Integrated the versioned SQLite review workflow; added ambiguity-aware storage, settings identity, and a rollback-tested v1-to-v2 migration that preserves historical decisions.
- Nine browser unit tests plus production-browser checks for image assets, persistence, exports and desktop/mobile layouts. Python regression coverage includes both UIs and database migration.
- Product/design notes, a demo walkthrough, real UI screenshots and explicit limits on public-project claims.

## Delivered: September 25

- Added explicit per-document date-order maps shared by folder extraction, retrieval and SQLite indexing. Sparse maps inherit the batch default; an explicit `auto` preserves uncertainty even under a DMY/MDY default.
- Added document convention controls to the local Streamlit sandbox, including session-persistent overrides, reset, and effective settings in the register/evidence view. The hosted browser demo remains a fixed snapshot with separate per-field decisions.
- Added three synthetic mixed-convention documents with eight date candidates, including leap-day, invalid-calendar and month-precision cases. Explicit source-confirmed policies reduce unresolved candidates from five to one without altering source text; this is policy application, not a model accuracy measurement.
- Reject duplicate JSON keys, malformed policies, paths and missing/unsupported filenames before extraction or database mutation. Changing one document's effective setting versions only that document; prior review history, unchanged documents and atomic rollback are covered.
- Verification: 156 Python tests pass on Python 3.9 and a fresh locked Python 3.12 environment (30 added); nine TypeScript tests and the production-browser smoke flow pass. Original evaluation remains 18/18 field tuples, multilingual regression remains 42/42 in each mode, and retrieval remains 3/3 at all three word budgets.
- Exercised the local UI in Chrome, checked desktop/mobile layout and source-policy display, and inspected an actual eight-field JSON download with one unresolved date. Added a screenshot and [policy walkthrough](date-conventions.md).

Explanation point: the same date token can legitimately have different meanings in two documents. Confirming one file's convention must not silently resolve every other file in the batch.

## Delivered: September 26

- Added an explicit Tesseract API for language packs, page segmentation, language-directory selection and bounded recognition time. Missing packages/executable/packs are distinct from image or recognizer failures; automatic fallback does not swallow execution errors. The optional `tesseract` extra avoids installing the unverified PaddleOCR stack.
- Added three manually annotated synthetic image cases in English, French and Vietnamese, each tested clean and with a fixed downsampling/blur/rotation recipe. Downloaded and verified only the three required upstream language packs at a pinned revision; no trained model or confidential data was used.
- Measured actual Tesseract 5.5.3 image recognition: all six runs completed. Clean pages recovered 16/16 fields with no extras; degraded pages recovered 8/16 with four extras (micro precision 0.667, recall 0.500, F1 0.571). The 16-field original-text baseline is exact. These are three development pages, not six independent documents or real-scan accuracy evidence.
- Saved raw OCR text, source spans, missed/extra fields, settings, package/engine versions, timing and input/source/model hashes. Added a dependency-free saved-evidence check and a separate CI job that performs fresh image recognition and uploads its results. Execution completeness is distinct from extraction correctness.
- Added 43 regression tests. All 199 Python tests pass on Python 3.9 and a fresh locked Python 3.12 environment. Both environments produced the same field counts in the image experiment; the checked-in measurement is the Python 3.9/Pillow 11.3 run. Native missing-pack and forced-timeout probes returned the intended distinct errors, and the default English image pipeline recovered four fields.
- Ruff, nine TypeScript tests, type checking/production build, browser formatting and production-browser desktop/mobile flows pass. Original benchmarks remain 18/18 English field tuples, 42/42 multilingual cases in each mode, and 3/3 retrieval questions at every word budget. Refreshed existing source-hashed reports without changing the browser's text-backed behavior.
- Added the [image experiment protocol and failure analysis](image-ocr.md), updated portfolio talking points and kept unsupported OCR/model claims explicit. German/Spanish OCR, real scans, complex layouts and PaddleOCR remain unmeasured.

Explanation point: OCR changed an April 23 document date into June 23. Both are valid calendar dates, so passing a parser does not establish transcription accuracy. Reviewable source evidence matters even when the clean-page score is perfect.

## Delivered: September 26, Public-Data Milestone

The user explicitly expanded the scope to real public pharmaceutical documents and actual training. This supersedes the earlier synthetic-only collection policy; confidentiality and honest measurement remain required.

- Collected 60 real public MHRA medicine recall/defect notices through official GOV.UK APIs. The bounded collector checks robots rules, limits requests and downloads, verifies cached bytes and retains retrieval/source hashes. Published 83 tables (six headings-only negatives) and 371 batch rows with OGL attribution; raw downloads and models stay ignored locally.
- Added an explicit 15-heading annotation map and fixed experiment protocol. Fitted a character TF-IDF/logistic-regression column classifier on 182 column instances from 36 training documents; validation and test each contain 12 chronologically separated notices. Duplicate whole-table payloads are grouped, and a regression test confirms held-out headings never enter fitting.
- Measured 80/80 forced test role predictions, tied by keyword rules; majority baseline scores 23/80. Disclosed that 76/80 test headings repeat training templates and the four unseen examples are all `other`. The fixed 0.60 threshold abstains on four test columns. This does not establish an advantage over rules, date accuracy or OCR fine-tuning.
- Built 742 batch-linked date-column candidates with exact source cells, batch-column indices, precision, ambiguity and review flags. 123 cells are ambiguous and 80 are unparsed/non-date; no single date is invented for them. Every public record still requires review.
- Ran actual Tesseract on the first two pages of three original test PDF attachments. OCR and native text each recover 11/11 supported unique HTML-table date interpretations; five non-date cells are excluded explicitly. Saved six page transcripts and source/model hashes. The checker recomputes protocol selection and HTML reference values; tests reject altered references, exclusions, sources, pages and duplicated documents. Coverage is not precision, batch-link accuracy or independent gold.
- Added a default Public notices view with batch/medicine search, split/type/unresolved filters, pagination, source table evidence, original links and CSV/JSON exports. Retained the separate synthetic review UI. Fixed a search-input change event that caused recursive rerendering in browser testing.
- Verification: 233 Python tests pass in the locked Python 3.12 research/demo environment; Python 3.9 passes 228 with five optional research-dependency tests skipped. Twelve TypeScript tests, production build and browser workflows cover original evidence, attributed exports, empty results, typing and responsive layouts. Source-hashed reports were regenerated; CI retrains from frozen data without crawling.
- Added a dataset/model card, source licence boundaries, reproducible crawl/train/OCR commands, actual UI screenshot and portfolio walkthrough. Updated the daily automation to prioritize evidence-driven public-data work while retaining synthetic multilingual regressions.

Explanation point: the important discovery was not a perfect model score. Real notices mostly repeat the same headings, so keyword rules work equally well. The useful engineering is source-linked batch/date evidence, honest uncertainty, and an evaluation that reveals when machine learning adds no demonstrated value.

Release follow-up: the Linux retraining check exposed unstable ordering in the top-feature explanation, where many coefficients tie. Added an explicit rounded-weight/alphabetical tie-break, a regression test, and useful comparison diagnostics. Fitting and prediction checks remain unchanged; the explanation is not a model improvement. The complete Python 3.12 suite now has 234 tests.

## Planned Work Sessions

| Date | Priority | Completion evidence |
| --- | --- | --- |
| September 25 | Completed: per-document conventions and adversarial fixtures | See the delivered milestone above |
| September 26 | Completed: synthetic image OCR plus real public-data training/UI | See both delivered milestones and their separate reports |
| September 27 | Improve public-date handling and evaluation diversity | Range/non-date cases from frozen public tables; independent labels or template-diverse sources where available; retain multilingual regressions |
| September 28 | Extend review-cycle semantics | Explicit re-review and source retirement behavior; preserve existing browser and SQL decision history |
| September 29 | Compare retrieval/model alternatives if prerequisites exist | Reproducible measured comparison; never invent unavailable model results or spend on APIs without authorization |
| September 30 | Refine demo flow and visual documentation | Browser checks on desktop/mobile, reproducible screenshots, concise walkthrough |
| October 1 | Installation and release rehearsal | Clean-environment installation, CI, dependency notes and full demo run |
| October 2 | Final fixes and application-ready release | Verified main branch, exact results, concise limitations and final shareable commit/release |

## Session Checklist

Inspect the current worktree and instructions, preserve user changes, pull safely, choose the next useful milestone, implement, verify, review the diff, and commit/push with the actual timestamp. Update this file with measured results and unresolved gaps.

Keep the README synchronized with what runs. The five-language demo consumes synthetic text; separate experiments measure synthetic multilingual images and three original English MHRA PDFs. A real-data column classifier is trained, but no OCR recognizer is fine-tuned. There is no LlamaIndex index, Mistral/Phi-2 benchmark, clinical validation or measured customer impact. New real sources require documented reuse terms, attribution, bounded collection and reviewable provenance. Preserve frozen test data and disclose template overlap rather than treating repeated headings as proof of generalization.

The daily Codex schedule runs at 9:00 a.m. America/Los_Angeles through October 2. It depends on the local machine and app being available. Stop the automation after the final session; do not create backdated or empty activity commits.
