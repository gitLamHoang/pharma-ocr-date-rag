# Daily Development Roadmap

Sprint: September 24 through October 2, 2026. Application deadline: October 3.

Sprint work concludes with the October 2 release verification below. Planned sessions without shipped work are marked explicitly. No missing activity is backdated or fabricated.

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

Hosted-site verification also exposed a browser-test race: source highlights render before an image finishes loading over the network. The test now waits for image decoding before checking dimensions, without treating a broken image as success. The complete browser flow then passed against GitHub Pages; the hosted public snapshot also matched all committed source hashes and 742 records.

## Delivered: September 27

- Inspected the frozen real-data failures rather than expanding the crawl or changing the classifier. Of 80 cells with no date candidates, 39 are source distribution statements and three are inclusive expiry cutoffs. Added explicit value kinds for these meanings; 38 cells remain unsupported. The no-single-date count stays 203.
- Recognize only complete, role-appropriate statements and an explicit inclusive expiry cutoff with an unambiguous valid endpoint. Preserve month precision, null single-date values and empty candidate lists. Do not infer a lower bound, century, date convention or footnote meaning. Unsupported exceptions, ranges and invalid dates remain unresolved.
- Show a source footnote warning when either the date cell or batch cell contains the cutoff qualifier marker. Added value-kind filters and explicit interpretations in the public UI. Schema-v2 JSON and separate CSV columns retain cutoff, statement and review information without converting it into a normalized expiry date.
- Added six explicitly authored, source-coordinate-checked development cases covering the six distinct phrases, with a reproducible 6/6 report. These cases were selected after inspecting all splits; they are not independent gold or held-out parsing accuracy. Added 24 Python tests and three frontend tests for semantic boundaries and invalid combinations.
- Confirmed all 742 original IDs, source cells/hashes, batch identifiers, normalized values, candidates and review statuses are unchanged. Frozen corpus bytes, training split, model settings, classifier predictions and scores are unchanged. No new source collection, OCR fine-tuning or model improvement is claimed.
- Verification: 258 Python tests pass with locked Python 3.12 research/demo dependencies; Python 3.9 passes 253 with five optional research tests skipped. Fifteen frontend tests, production build and desktop/mobile browser workflows pass, including kind filters, source qualifiers and JSON/CSV bounds. Re-ran actual recognition on the same three original PDFs; both OCR and native date coverage remain 11/11. Existing English (18/18), multilingual (42/42 in both modes) and retrieval (3/3 at all budgets) regressions remain unchanged. Regenerated source-hashed reports and added the cell benchmark check to CI.
- Updated the dataset/model card, README, demo walkthrough and portfolio explanation; captured actual desktop/mobile screenshots. Broader date formats, independent labels and template-diverse sources remain future work.

Explanation point: a date-looking token can be a boundary, not an event date. The program should preserve that distinction instead of turning every recognized month into an exact expiry value. Likewise, a source statement is not missing data or a claim about current stock status.

## Delivered: September 28

- Added explicit local document re-review, retirement, restoration and lifecycle history. Version listings include source state and field counts, including zero-field and missing-file sources. Actions require an exact document version ID, reviewer and reason.
- Retirement blocks routine indexing for every version of the same collection/filename, including changed content and settings. Restoration accepts only the last retired version, reactivates stored evidence and marks all its fields `needs_review`. Ordinary source changes and missing files keep their earlier semantics.
- Preserved previous field decisions and added append-only document events. Reopen/restore field reasons link to the document event ID. Active-state changes and new events share one transaction; simulated partial-write failures roll back everything. Schema v3 upgrades v1/v2 databases without renumbering evidence or inventing historical lifecycle events.
- Added a browser confirmation for whole-document re-review. It covers all fields, including hidden filter results, groups events in JSON and clears previous manual date choices. Earlier events remain compatible and visible in history. Failed storage leaves the session unchanged. Public MHRA records remain a separate, review-only snapshot; source retirement is a local SQLite operation.
- Verification: 267 Python tests pass with locked Python 3.12 research/demo dependencies; Python 3.9 passes 262 with five optional research tests skipped. Added nine Python cases and two frontend tests; all 17 frontend tests, production build, formatting and desktop/mobile browser workflows pass. Checked dialog layouts at 320, 768, 1024 and 1920 pixels, including confirmation, storage failure, reload and exports.
- Built a wheel and installed it into a fresh dependency-free Python 3.12 environment. The installed CLI indexed four synthetic documents / 24 fields, reopened six fields, skipped one retired source, restored those six to review, and preserved both field and document history.
- Reproduced frozen MHRA training results (80/80 roles, still tied by keyword rules), six source-anchored cell cases, English 18/18, multilingual 42/42 in both modes and retrieval 3/3 at each budget. Verified saved OCR reports without rerunning OCR locally. Frozen public data, extraction semantics, model protocol and scores are unchanged. Regenerated only the source-hashed synthetic reports.
- Added the [lifecycle contract and walkthrough](review-lifecycle.md), an actual confirmation screenshot, README controls and portfolio explanation. Authenticated reviewers, cross-tab synchronization, independent date labels and clinical validation remain outside this prototype.

Explanation point: preserving evidence does not mean treating an old decision as permanent approval. Re-review adds a new decision without erasing history; retirement is an explicit source action, not an assumption based on a missing file.

## Delivered: October 2

- Completed the final installation rehearsal with a fresh locked Python 3.12 environment and a fresh frontend dependency installation. Added a repeatable installed-wheel verifier so CI checks the distributed CLI and SQL resources outside the source checkout, without optional runtime dependencies or index access during installation.
- Six installed-package checks pass: isolated import/entry point, mixed conventions/source spans, repeat indexing, document lifecycle history, and v1/v2 upgrades. All preserve unresolved evidence and earlier review IDs. Added eight verifier regression tests for errors, timeout configuration, source import leakage, cleanup failure and stale reports. A deliberately incomplete wheel without `schema.sql` correctly fails. CI uploads the valid wheel with its hash-bearing verification report.
- Verification: 275 Python tests pass with research/demo/Tesseract extras. Python 3.9 passes 270 with five optional research tests skipped. All 17 frontend tests, production build, formatting, local desktop/mobile browser flows and saved-evidence checks pass. The full browser smoke test also covers the public hosted demo.
- Reproduced English 18/18, multilingual 42/42 in each mode, retrieval 3/3 at every existing word budget, six source-anchored cell cases and frozen model roles 80/80, still tied by rules. Reran actual synthetic image OCR (16/16 clean; 8/16 degraded with four extras) and original public-PDF OCR/native extraction (both 11/11 supported unique date interpretations). Fresh OCR output stays separate from frozen checked-in evidence.
- Added the [final release checklist](release-checklist.md), clean-install commands, scope boundaries and a concise demo sequence. Corrected stale documentation and explicitly deferred the proposed real-data retrieval comparison. No separate September 29, September 30 or October 1 milestone shipped; this session does not claim otherwise.
- This is the final scheduled session. The automation is to be deleted after publishing and checking this commit. Remaining research is documented, not automatically scheduled beyond the application deadline.

Explanation point: tests inside a checkout can accidentally rely on unpackaged files. The new verification installs only the wheel, invokes its real CLI and proves that database upgrades and source evidence work for someone installing the project.

## Session Outcomes

| Date | Priority | Completion evidence |
| --- | --- | --- |
| September 25 | Completed: per-document conventions and adversarial fixtures | See the delivered milestone above |
| September 26 | Completed: synthetic image OCR plus real public-data training/UI | See both delivered milestones and their separate reports |
| September 27 | Completed: conditional dates and non-date statements | Six source-anchored cases, typed exports, source qualifiers and negative tests; independent labels remain future work |
| September 28 | Completed: explicit re-review and source retirement | Append-only history, v1/v2 upgrade and failed-write tests, browser confirmation, and installed-wheel lifecycle walkthrough |
| September 29 | Deferred: retrieval/model alternatives | Scoping only; no new experiment or comparison shipped |
| September 30 | No separate milestone shipped | Existing demo flow verified in the final session |
| October 1 | Rehearsal moved to October 2 | No separate milestone shipped |
| October 2 | Completed: final installation and demo verification | Fresh environments, installed-wheel CI, reproducible measurements and final release checklist |

## Session Checklist

Inspect the current worktree and instructions, preserve user changes, pull safely, choose the next useful milestone, implement, verify, review the diff, and commit/push with the actual timestamp. Update this file with measured results and unresolved gaps.

Keep the README synchronized with what runs. The five-language demo consumes synthetic text; separate experiments measure synthetic multilingual images and three original English MHRA PDFs. A real-data column classifier is trained, but no OCR recognizer is fine-tuned. There is no LlamaIndex index, Mistral/Phi-2 benchmark, clinical validation or measured customer impact. New real sources require documented reuse terms, attribution, bounded collection and reviewable provenance. Preserve frozen test data and disclose template overlap rather than treating repeated headings as proof of generalization.

The daily Codex schedule was limited to October 2 and depended on local machine/app availability. The sprint ends after the final session; no backdated, empty or post-deadline activity commits are planned.
