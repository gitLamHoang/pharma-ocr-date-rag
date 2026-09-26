# Portfolio Guide

## One-minute project introduction

Pharma Date Review is a research prototype for turning medicine notices into a source-linked batch/date register. It collects 60 real public MHRA notices, trains a column-role classifier, tests OCR on original PDFs and exposes 742 candidate cells in a TypeScript workspace. A separate synthetic workflow combines five-language Python parsing, source-aware retrieval and versioned SQLite review. The problem is not just finding a date: a reviewer needs its meaning, source evidence and unresolved interpretations.

The live demo starts with real notices: search a batch, inspect its date and source row, and follow the publisher link. Public values are candidates, not approvals or live recall advice. The synthetic Document review view demonstrates an additional workflow: choose between two interpretations of a French audit date, record a reason and export the evidence. The central product decision is to preserve uncertainty until it can be resolved.

## Three engineering decisions to explain

1. **Language is not a date convention.** Recognizing French words does not prove `09/10/2026` is day-first. Vocabulary and numeric order are separate settings, tested separately.
2. **Evidence must survive change.** SQL versions include content hashes and parser settings. Reindexing identical evidence preserves decisions; changed evidence creates a separate version. The migration preserves historical IDs and events and rolls back on failure.
3. **A metric needs a denominator and a scope.** The multilingual report is 42 authored development cases, not 42 vendor documents. Both language modes pass, but the fixtures were used during implementation and do not establish generalization or image-OCR accuracy.

## An experiment to discuss

The [public-data experiment](public-data.md) trained a character TF-IDF/logistic-regression column classifier on 182 examples from 36 real notices. It tied keyword rules at 80/80 held-out column roles, with substantial repeated-template overlap. This is a useful negative result: the simple rules remain competitive, so more complexity needs better evidence. Original PDF OCR recovered 11/11 supported unique table-date interpretations in three notices; native extraction did too. Neither is a general accuracy claim. Be precise: a column classifier was trained, not the OCR engine.

The [image-OCR experiment](image-ocr.md) measures a different boundary: actual Tesseract recognition of three synthetic pages in English, French and Vietnamese. Clean images recover 16/16 fields; after a fixed degradation, only 8/16 match and four predictions are extra. One document date changes from April 23 to June 23, a plausible value that calendar validation cannot catch. Explain why this led to preserving source evidence and treating recognition output as reviewable candidates, not automatic approval. It is a small controlled experiment, not a trained model or real-vendor accuracy claim.

## Product questions still open

- Do supplier-quality reviewers spend enough time on date review to justify a separate tool?
- Which error types matter most, and when is a human review mandatory?
- What source formats, retention rules and approval systems would a pilot need to fit?
- Does the tool reduce review time without increasing missed or incorrectly accepted dates?

No customer interviews, adoption, revenue or time-saving measurements are claimed. An independently annotated set and a consented workflow comparison would be useful next evidence.

## Public project boundaries

The browser consumes generated Python snapshots. It does not run OCR or synchronize with the CLI database. Synthetic browser decisions are localStorage records, not authenticated approvals. Synthetic page highlights come from known rendered layout, not OCR bounding-box predictions. Public-notice evidence highlights an exact HTML table cell, not a detected PDF region.

The repository is an independent, AI-assisted public reconstruction of a workflow idea, not a Pfizer code release. Describe any professional experience separately using only work you actually performed and are allowed to discuss. The public code does not substantiate a trained OCR model, LlamaIndex deployment or measured Mistral/Phi-2 comparison.

## Before an interview

Run the demo yourself. Read `dates.py`, `review.py` and `web/src/data.ts`; trace one field from original text through normalization, review and export. Change a synthetic fixture, explain the failed reproducibility check, regenerate the snapshot and rerun the tests. Be comfortable explaining these boundaries instead of treating a large feature list as the project story.
