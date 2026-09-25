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

## Planned Work Sessions

| Date | Priority | Completion evidence |
| --- | --- | --- |
| September 25 | Completed: per-document conventions and adversarial fixtures | See the delivered milestone above |
| September 26 | Exercise real image OCR, starting with Tesseract language configuration | Synthetic rendered image, installed-pack checks, measured extraction results; distinguish missing dependencies |
| September 27 | Build harder multilingual retrieval evaluation | Gold questions, distractors, no-answer cases, top-k metrics and recorded failures |
| September 28 | Extend review-cycle semantics | Explicit re-review and source retirement behavior; preserve existing browser and SQL decision history |
| September 29 | Compare retrieval/model alternatives if prerequisites exist | Reproducible measured comparison; never invent unavailable model results or spend on APIs without authorization |
| September 30 | Refine demo flow and visual documentation | Browser checks on desktop/mobile, reproducible screenshots, concise walkthrough |
| October 1 | Installation and release rehearsal | Clean-environment installation, CI, dependency notes and full demo run |
| October 2 | Final fixes and application-ready release | Verified main branch, exact results, concise limitations and final shareable commit/release |

## Session Checklist

Inspect the current worktree and instructions, preserve user changes, pull safely, choose the next useful milestone, implement, verify, review the diff, and commit/push with the actual timestamp. Update this file with measured results and unresolved gaps.

Keep the README synchronized with what runs. The multilingual path currently consumes text; real image OCR is not yet validated. The public repository has no LlamaIndex index, trained model, Mistral/Phi-2 benchmark or measured customer impact.

The daily Codex schedule runs at 9:00 a.m. America/Los_Angeles through October 2. It depends on the local machine and app being available. Stop the automation after the final session; do not create backdated or empty activity commits.
