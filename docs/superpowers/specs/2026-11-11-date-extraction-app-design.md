# Pharma Date Extraction App — Design

Date: 2026-11-11 · Branch: `rebuild/refractor-ui-and-model`

## 1. Intent

A quality or regulatory reviewer on a pharmaceutical quality team uploads a pharmaceutical document (PDF or scan) and gets back every date in it, labeled with what the date *means*, located on the page, and checked for consistency. The reviewer confirms or corrects each date, and the result can be exported.

Why: pharma documents carry many kinds of dates (manufacture, expiry, retest, signature, approval, effective, certificate issue/validity, notarization, apostille, legalization…). Finding a date string is easy; knowing which date is which, and noticing when they don't add up (an expired certificate, an apostille dated before the document it certifies), is the slow manual work this app removes.

The rebuild replaces the current portfolio prototype in this repo.

## 2. Goals, non-goals, anti-goals

**Goals**
- Upload PDF (native-text or scanned) or image (PNG/JPG/TIFF) → labeled dates in under ~1 minute for a 10-page document.
- Every date has: type, family, original text, normalized ISO value (or explicit ambiguity), page, bounding box when locatable, evidence snippet, source (rules / AI-only), confidence.
- Consistency flags (see §5.5).
- Human review: accept, correct type/value, reject, with reviewer name and reason; append-only history.
- Export CSV and JSON per document.
- Works offline in degraded mode (no API key → rules + Tesseract only).

**Non-goals (v1)**
- SSO / multi-tenant / role-based access. Reviewer name is a typed label.
- Integration with company systems (Veeva, LIMS, DMS).
- Hosting at scale; v1 is a pilot on one machine or one internal server.
- The old public MHRA notices corpus, recall classifier, benchmark lab, Streamlit sandbox and RAG retrieval.

**Anti-goals (would be failure even if it "works")**
- A date shown to a reviewer that does not exist in the document (hallucination).
- An ambiguous numeric date (`09/10/2026`) silently resolved without evidence.
- A month-only expiry (`03/2027`) turned into a specific day.
- Losing or overwriting a reviewer decision.

## 3. Constraints

- Cloud AI is allowed. Provider must be configurable: Anthropic API (default), Amazon Bedrock, or Google Vertex AI — the deploying company's IT decides which channel is approved.
- No real company documents available yet; build and evaluate on public documents.
- Must run on macOS (developer) and Linux (Docker).
- Languages: English, French, German, Spanish, Vietnamese already supported by the rules; legalization pages may contain other scripts — the AI layer handles those, rules mark them unknown.

- **No secrets or sensitive data in the repo, ever:** API keys and cloud credentials only in a git-ignored `.env` (an `.env.example` with placeholders is committed); uploads, page images, SQLite files and logs are git-ignored; logs never print keys or document text; a pre-commit secret scan (gitleaks) runs locally and in CI; eval set uses public documents only.

## 4. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| A | Rules find dates, AI labels them | Fully traceable, cheap; misses unusual formats (handwriting, `12.III.2026`). |
| B | AI reads page and returns dates + types | Simplest, best recall; can misread or invent dates, no exact location. Poor fit for GMP traceability. |
| **C (chosen)** | **Hybrid: A, plus AI may report dates the rules missed; those are marked "AI-only, verify" and must pass verification** | Traceability of A with recall close to B; more to build and test. |

Chosen by the user on 2026-11-11.

## 5. The pipeline

```
upload → 1 ingest → 2 text+layout → 3 candidates (rules) → 4 classify (Claude) → 5 validate → 6 store → review UI
```

### 5.1 Ingest
- Accept PDF, PNG, JPG, TIFF up to 50 MB / 100 pages. Compute SHA-256; identical file re-upload reuses the stored result.
- Render each page to PNG (pypdfium2, 200 DPI) for the viewer and the AI.

### 5.2 Text and layout per page
- **Native-text PDF page** (has a text layer with enough characters): words + boxes from pdfplumber.
- **Scanned page / image:** Tesseract `image_to_data` for words + boxes (language packs eng+fra+deu+spa+vie). If Claude is available, also ask Claude for a faithful transcription of the page (used in step 4).
- Output per page: `text`, list of `words(text, x0, y0, x1, y1, char_start, char_end)`.

### 5.3 Candidates (rules)
- Port the existing `dates.py`, `languages.py`, `conventions.py` logic into the new package (keep their tests). It finds date strings, normalizes them, keeps ambiguity (`candidates`), precision (day/month), and document-level order evidence.
- Run over each page's text layer (pdfplumber or Tesseract), and over Claude's transcription if present; merge duplicates by normalized value + overlapping location.
- Each candidate gets an id, page, char span, box (union of overlapping word boxes), raw text, normalized/candidates, ±200 chars context, and a rule-based label from `classify_context` as a fallback.

### 5.4 Classify (Claude)
- One call per page (pages in parallel, bounded concurrency 4). Input: page image + page text + numbered candidate list. Model `claude-opus-5-5`, structured output via `output_config.format` (JSON schema), adaptive thinking, effort `medium`, server-side refusal fallbacks enabled.
- Output per candidate: `date_type` (from taxonomy §6), `role/qualifier` (e.g. signer name & signature meaning, which certificate a validity date belongs to), `resolved_value` only if the page gives evidence for an ambiguous date (with the evidence quoted), `confidence` (0–1), short `rationale`.
- Output `missed_dates[]`: dates the model sees that are not in the candidate list, with verbatim text and type.
- **Verification of AI-only dates:** the verbatim text must parse to a valid date with the rules parser (or a looser parser for roman-numeral / spelled-out months), and must appear (fuzzy match ≥ 0.85) in the Tesseract or pdfplumber text of that page. Pass → stored with `source = ai_only`, status `needs_review`, box from the matched words. Fail → discarded and logged.
- Claude may not change a candidate's raw text or invent a normalized value; a disagreement is stored as a flag.
- **Offline / no key / API error:** fall back to rule labels; document shows a banner "AI classification unavailable".

### 5.5 Validate
Deterministic rules over the labeled dates of one document; each produces a flag with severity (error / warning / info):
- Expiry ≤ manufacture; retest ≤ manufacture.
- Signature date before document effective/issue date where the signature is an approval of that document (warning).
- Legalization chain out of order: certificate issue ≤ notarization ≤ apostille / consular legalization ≤ translation certification.
- Certificate validity/expiry already passed relative to today (or a reviewer-supplied reference date).
- Date in the future where it should be past (signature, manufacture, inspection) — warning.
- Ambiguous numeric date unresolved — info, requires reviewer choice.
- AI and rules disagree on a value — warning.

### 5.6 Store
SQLite (one file, WAL), schema:
- `documents` (id, filename, sha256, pages, status, created_at, ai_model, pipeline_version)
- `pages` (document_id, n, image_path, text, text_source, words_json)
- `runs` (id, document_id, pipeline_version, ai_model, ai_used, started_at, finished_at, status)
- `dates` (id, run_id, document_id, page, raw_text, normalized, candidates_json, precision, date_type, family, qualifier, bbox_json, source[rules|ai_only|rules+ai], confidence, rationale, context)
- `flags` (document_id, date_ids, rule, severity, message)
- `review_events` append-only (date_id, action[accept|correct|reject|reopen], new_type, new_value, reviewer, reason, at) — DB triggers block update/delete.
Uploaded files and page images under `data/uploads/<sha256>/`.

Processing runs as a background task; the API exposes status (`queued → reading → classifying → validating → done | failed`) for the UI to poll.

## 6. Date taxonomy

| Family | Types |
|---|---|
| Product / batch | manufacture_date, expiry_date, retest_date, packaging_date, release_date (incl. QP certification), sampling_date, test_date, analysis_report_date |
| Document control | effective_date, issue_date, version_date, approval_date, review_date, next_review_date, superseded_date |
| Signature | signature_date (qualifier: signer, meaning author/reviewer/approver/witness/QP) |
| Legal / regulatory | certificate_issue_date, certificate_valid_until, notarization_date, apostille_date, legalization_date (consular/embassy), translation_certification_date, authorization_date (marketing authorization/licence grant or renewal) |
| Audit / inspection | inspection_date, audit_date, next_audit_date, capa_due_date |
| Logistics | shipping_date, receipt_date |
| Other | other_date (with free-text qualifier), unknown |

Taxonomy lives in one Python module and is exported to the frontend via the API so both stay in sync.

## 7. Interface

React app, three screens:

1. **Documents** — drag-and-drop upload area; table of documents (name, pages, status, # dates, # flags, # needing review, uploaded at). Processing status updates live.
2. **Review** — split view. Left: page viewer (zoom, page thumbnails, highlight boxes colored by family; clicking a box selects the date). Right: dates grouped by family, each row showing type, value, page, source badge (Rules / AI-only), confidence, status; flags panel at top. Selecting a row scrolls to its box. Actions per date: Accept, Correct (type, value, or choose interpretation for ambiguous), Reject — each asks for reviewer + reason (reviewer remembered per browser). Keyboard: ↑/↓ move, A accept, E edit.
3. **Export** — from the Review screen: CSV / JSON of current state + full review history.

Look: professional, clean, dense tool UI — no generic "AI-made" look (no purple gradients, glassmorphism soup, emoji icons, filler copy). Palette chosen by the user, used 60 / 30 / 10:
- **Midnight Navy** (~`#1B2447`, main, 60%) — app background in dark theme, text and chrome in light theme.
- **Powder Blue** (~`#C5D0EE`, second, 30%) — surfaces, panels, secondary text, light-theme background tint.
- **Sunflower** `#FFC93C` (accent, 10%) — primary action, selected date, focus ring, "needs review" count. Never for body text on light backgrounds.
Bold condensed display type for headings, a clean grotesk for UI text, a mono for dates/IDs. Family highlight colors are derived to sit inside this palette and pass contrast checks. Light and dark themes, readable at 1280px and usable on a tablet. No company branding in v1.

Design process: art direction and a quality pass with the `taste-skill:design-taste-frontend` skill (app-screens run), and UI build/critique/polish/hardening with `impeccable:impeccable`; motion kept minimal (Emil's `animate` / `review-animations` only where it aids state changes like upload progress and selection).

## 8. Stack (my calls)

- **Backend:** Python 3.12, FastAPI, Pydantic v2, `anthropic` SDK (with Bedrock/Vertex clients selected by env), pdfplumber, pypdfium2, pytesseract + system Tesseract, Pillow, SQLite (stdlib). Background tasks via FastAPI + a small in-process worker queue. `uv` for dependencies.
- **Frontend:** React 18 + TypeScript + Vite, TanStack Query for API state, plain CSS with design tokens (no component framework), Vitest + Playwright smoke test.
- **Packaging:** `docker compose up` runs API + built frontend (served by FastAPI) with Tesseract installed; `make dev` for local hot reload.
- **Config:** `.env` — `ANTHROPIC_API_KEY` or `CLAUDE_PROVIDER=bedrock|vertex` + their settings; `AI_ENABLED=false` for offline mode.

## 9. Repo after the rebuild

Delete: Streamlit demo, `web/` static app, MHRA collector/classifier/benchmarks, RAG module, old scripts, reports, portfolio docs, screenshots, old CLI and SQLite review layer (replaced). Keep: license, the date-parsing logic and its tests (ported), changelog (new entry). New layout:

```
backend/  pharma_dates/{ingest,layout,candidates,classify,validate,store,api,taxonomy,config}.py + tests/
frontend/ src/{pages,components,api}/ …
eval/     public sample documents, gold labels, run_eval.py
docker-compose.yml  Makefile  README.md
```

README: short — what it does, a screenshot, quick start (Docker and local), configuration, how it works (the 6 steps in one paragraph each line), limits, license.

## 10. Testing and evaluation

- Unit tests: date parsing (ported), candidate merge, AI-only verification, every validation rule, store append-only triggers, API endpoints (Claude mocked).
- Eval set: ~15 public documents (FDA/EMA/MHRA certificates and notices, published CoAs, a public apostille sample) with hand-written gold labels; `run_eval.py` reports per-type precision/recall, hallucination count (must be 0), and ambiguous-silently-resolved count (must be 0). Run with and without AI.
- Frontend: Vitest for components with logic; one Playwright smoke test: upload sample → wait done → accept a date → export.

## 11. Decisions settled after review (my calls — check these)

1. **Dates found only in Claude's transcription are AI-only.** A candidate counts as `rules` only if it is found in the pdfplumber/Tesseract text layer. A candidate found only in Claude's transcription is `ai_only` and must pass the §5.4 verification, otherwise it is discarded. Hallucination in the eval = any stored date with no gold match whose text is not on the page.
2. **Non-Latin scripts.** Tesseract also loads `ara`, `rus`, `chi_sim`, `jpn` packs so AI-only dates on those pages can still be verified. Dates that still fail verification are discarded (logged, shown in a per-document "discarded AI suggestions" debug list, never as dates).
3. **Reprocessing.** v1 supports "Reprocess" (new pipeline/model version, or first run was offline). Each run is stored in a `runs` table; dates belong to a run; old runs are frozen, never deleted. A reviewer decision carries over to the new run when page + raw text + normalized value match exactly; it's marked "carried over from run N". Everything else starts as `needs_review`. Re-uploading an identical file opens the latest run.
4. **Providers.** One client adapter. Anthropic API is the primary target and gets all features. On Bedrock/Vertex the same request is sent; if structured output is unsupported there, fall back to a strict tool definition with `tool_choice: auto` plus schema validation and one retry; refusal fallback uses the SDK's client-side middleware. Feature parity is not a hard requirement.
5. **Month-only dates** compare as the last day of that month (standard pharma reading of `EXP 03/2027`), but are still displayed and stored as month precision (`2027-03`). Flags on them say "month precision".
6. **Offline labeling** covers the existing rule labels mapped to the new taxonomy (expiry, manufacture, audit, receipt, document issue) plus English keywords for signature, effective, approval, retest, certificate validity, apostille, notarization. Everything else is `unknown`. Offline eval targets are reported separately and are not a release gate.

## 12. Left to the builder

- Exact prompts and JSON schema wording; concurrency/timeouts; page DPI.
- Which public documents form the eval set (must be redistributable or fetched by script, not committed if license unclear).
- Visual details within §7.
