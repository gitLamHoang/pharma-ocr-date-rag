# Portfolio Guide

## One-minute project introduction

Pharma Date Review is a public prototype for reviewing dates in pharmaceutical-style vendor documents. The problem is not just finding a date: a reviewer needs its meaning, source evidence and any unresolved interpretation. The project combines a five-language Python parser, source-aware retrieval, a versioned SQLite review queue and a TypeScript browser workspace. All public data is synthetic.

The live demo is intentionally easy to inspect. It begins with a French audit date that can mean September 10 or October 9. The parser keeps both possibilities. The reviewer chooses an interpretation, records a reason and exports the evidence with the decision. This is the central product decision: preserve uncertainty until someone can resolve it.

## Three engineering decisions to explain

1. **Language is not a date convention.** Recognizing French words does not prove `09/10/2026` is day-first. Vocabulary and numeric order are separate settings, tested separately.
2. **Evidence must survive change.** SQL versions include content hashes and parser settings. Reindexing identical evidence preserves decisions; changed evidence creates a separate version. The migration preserves historical IDs and events and rolls back on failure.
3. **A metric needs a denominator and a scope.** The multilingual report is 42 authored development cases, not 42 vendor documents. Both language modes pass, but the fixtures were used during implementation and do not establish generalization or image-OCR accuracy.

## An experiment to discuss

The [image-OCR experiment](image-ocr.md) measures a different boundary: actual Tesseract recognition of three synthetic pages in English, French and Vietnamese. Clean images recover 16/16 fields; after a fixed degradation, only 8/16 match and four predictions are extra. One document date changes from April 23 to June 23, a plausible value that calendar validation cannot catch. Explain why this led to preserving source evidence and treating recognition output as reviewable candidates, not automatic approval. It is a small controlled experiment, not a trained model or real-vendor accuracy claim.

## Product questions still open

- Do supplier-quality reviewers spend enough time on date review to justify a separate tool?
- Which error types matter most, and when is a human review mandatory?
- What source formats, retention rules and approval systems would a pilot need to fit?
- Does the tool reduce review time without increasing missed or incorrectly accepted dates?

No customer interviews, adoption, revenue or time-saving measurements are claimed. An independently annotated set and a consented workflow comparison would be useful next evidence.

## Public project boundaries

The browser consumes a generated Python snapshot. It does not run OCR or synchronize with the CLI database. Browser decisions are localStorage records, not authenticated approvals. The page highlights are computed from rendered fixture layout, not OCR bounding-box predictions.

The repository is an independent, AI-assisted public reconstruction of a workflow idea, not a Pfizer code release. Describe any professional experience separately using only work you actually performed and are allowed to discuss. The public code does not substantiate a trained OCR model, LlamaIndex deployment or measured Mistral/Phi-2 comparison.

## Before an interview

Run the demo yourself. Read `dates.py`, `review.py` and `web/src/data.ts`; trace one field from original text through normalization, review and export. Change a synthetic fixture, explain the failed reproducibility check, regenerate the snapshot and rerun the tests. Be comfortable explaining these boundaries instead of treating a large feature list as the project story.
