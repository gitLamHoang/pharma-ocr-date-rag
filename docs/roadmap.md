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
- 110 tests pass with demo dependencies installed, including documented script entry points.
- Product/design notes, a demo walkthrough, real UI screenshots and explicit limits on public-project claims.

## Planned Work Sessions

| Date | Priority | Completion evidence |
| --- | --- | --- |
| September 25 | Broaden adversarial date fixtures and per-document convention handling | Mixed-convention examples, regression tests, visible source policy |
| September 26 | Exercise real image OCR, starting with Tesseract language configuration | Synthetic rendered image, installed-pack checks, measured extraction results; distinguish missing dependencies |
| September 27 | Build harder multilingual retrieval evaluation | Gold questions, distractors, no-answer cases, top-k metrics and recorded failures |
| September 28 | Improve review decisions and export reproducibility | Reviewer changes tied to source evidence; tests for reset, conflicting settings and exported decisions |
| September 29 | Compare retrieval/model alternatives if prerequisites exist | Reproducible measured comparison; never invent unavailable model results or spend on APIs without authorization |
| September 30 | Refine demo flow and visual documentation | Browser checks on desktop/mobile, reproducible screenshots, concise walkthrough |
| October 1 | Installation and release rehearsal | Clean-environment installation, CI, dependency notes and full demo run |
| October 2 | Final fixes and application-ready release | Verified main branch, exact results, concise limitations and final shareable commit/release |

## Session Checklist

Inspect the current worktree and instructions, preserve user changes, pull safely, choose the next useful milestone, implement, verify, review the diff, and commit/push with the actual timestamp. Update this file with measured results and unresolved gaps.

Keep the README synchronized with what runs. The multilingual path currently consumes text; real image OCR is not yet validated. The public repository has no LlamaIndex index, trained model, Mistral/Phi-2 benchmark or measured customer impact.

The daily Codex schedule runs at 9:00 a.m. America/Los_Angeles through October 2. It depends on the local machine and app being available. Stop the automation after the final session; do not create backdated or empty activity commits.
