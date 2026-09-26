# Public MHRA Data and Model Card

## Problem and Product

Medicine recall and defect notices publish batch identifiers alongside expiry and distribution dates. A reviewer needs those relationships, not a bag of date strings. Month-only expiry values, ambiguous numeric dates, and statements such as `Not yet distributed` must survive extraction without becoming invented dates.

This experiment builds a searchable, source-linked batch/date register from **real public notices**, then checks actual OCR on original PDF attachments. The intended research workflow is locating evidence across notices. It is not a live recall monitor, inventory clearance tool, medical recommendation, or validated quality-management system. A defect notice does not necessarily announce a recall; read the original notice for its meaning and current status.

Open the [public-notice workspace](https://gitlamhoang.github.io/pharma-ocr-date-rag/#recalls). Search batch `0162858`, select Expiry, and inspect the source row: `05/2028` stays `2028-05`, not an invented day. The original MHRA notice is one click away. Switch to unresolved values to see where automation stops.

## Source and Reuse

- Publisher: UK Medicines and Healthcare products Regulatory Agency (MHRA), on GOV.UK.
- Collection: 60 notices selected by the `medicines-recall-notification` search filter, ordered by latest public update, retrieved September 26, 2026. This category includes defect notifications. The search returned 589 available notices at collection time; this is a bounded sample, not complete coverage.
- Access: official [GOV.UK Content API](https://content-api.publishing.service.gov.uk/reference.html) plus the search endpoint recorded in the dataset's `selection.url`. Search interface stability is not guaranteed.
- Reuse basis: [GOV.UK reuse guidance](https://www.gov.uk/help/reuse-govuk-content) and the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), subject to its exclusions. See [data attribution](../data/public_mhra/LICENSE.md).
- No employer documents, patient records, credentials or private systems were used. Public product and organization names are source facts, not endorsement.

The collector identifies itself, checks robots rules, allows only two official HTTPS hosts, refuses redirects, spaces requests by at least one second, and caps collection at 100 notices. JSON downloads are limited to 2 MB and PDFs to 20 MB. It stops on access errors rather than bypassing them. Verified cached responses are reused, with URL, retrieval time and SHA-256 provenance. A fresh collection needs a separate cache; never silently replace the frozen evaluation corpus.

Published data retains notice metadata and batch tables. Non-batch tables retain headings only, providing negative column examples without redistributing their prose or contact details. Raw API responses, PDFs, rendered pages and fitted joblib models remain in ignored local `outputs/`. No government logos or PDF page images are redistributed in this dataset.

## Dataset

| Item | Count / scope |
| --- | --- |
| Notices | 60, English, one agency |
| Retained tables | 83, including 6 header-only non-batch tables |
| Batch rows | 371 |
| Column examples | 321 instances, only 15 distinct heading strings |
| Unsupported tables | 3 without explicit header cells; recorded, not silently guessed |
| Candidate date-column cells | 742; not 742 independently verified dates |
| No single normalized value | 203: 123 ambiguous and 80 unparsed/non-date cells |

Every candidate stores notice URL, source response hash, table/row/date-column/batch-column indices, exact raw value and batch identifier, model score, date precision and review flags. Leading zeros in batch IDs are preserved. **All 742 records require review**, including normalized values. This register covers supported tables only; omitted layouts and notices without tables remain visible in the dataset/report, not fabricated into records.

The 15 heading-to-role annotations in `header_labels.json` were explicitly reviewed with AI assistance. They label schema roles (`batch`, `expiry`, `distribution`, `other`), not independently adjudicated date values. There was no second annotator or agreement study. New headings must be annotated explicitly; training refuses unknown labels.

## What Was Actually Trained

A scikit-learn pipeline fits character 3-5-gram TF-IDF features and class-balanced logistic regression on **182 column instances from 36 real notices**. Features contain heading text only, not medicine names, document IDs, dates, or labels. This is a learned table-column classifier, **not OCR fine-tuning**. Tesseract uses existing pretrained language packs.

`protocol.json` fixes the split, model settings, 0.60 abstention threshold and PDF selection procedure. Documents are ordered chronologically for a 60/20/20 train/validation/test split; identical whole-table payloads stay together. TF-IDF fitting sees training headings only. Validation has 12 notices/59 columns; test has 12 notices/80 columns. No model or threshold search was performed.

| Predictor | Validation accuracy | Test accuracy |
| --- | --- | --- |
| Training-majority role | See saved report | 23/80 (28.75%) |
| Keyword rules | 59/59 | 80/80 |
| Trained classifier, forced prediction | 59/59 | 80/80 |

**The model does not outperform rules on this sample.** 76 of 80 test heading instances already occur in training. The four unseen headings are all `other`, so this does not test generalization to new expiry or batch terminology. Identical headers across documents are disclosed template overlap; document separation is not a template-disjoint benchmark. Test labels were available to the developer, so a future independently held-out set is still needed.

At the fixed 0.60 threshold, 76/80 test columns receive a role and four abstain. Scores are uncalibrated and do not express clinical certainty. Macro-F1 always averages the four declared classes; the unseen-only slice has F1 0.25 despite 4/4 correct because only `other` is represented and absent classes score zero. Use its class supports, not the aggregate in isolation.

For these structured templates, rules are the simpler choice. The learned model is a reproducible experimental comparator, not evidence of an AI advantage. Next evidence should come from independently annotated, template-diverse documents before increasing model complexity.

## Actual Original-PDF OCR

The predeclared selection takes the three newest test notices with PDF attachments: B. Braun meropenem, Martindale clobazam, and Zentiva fingolimod. Original PDFs are hashed and their first two pages rendered at 150 DPI. Tesseract 5.5.3 runs with the pinned English pack, OEM 1, PSM 3. Native PDF text extraction is a second baseline.

| Source | Supported unique HTML-table date interpretations | OCR recovered | Native text recovered |
| --- | --- | --- | --- |
| B. Braun meropenem | 5 | 5 | 5 |
| Martindale clobazam | 4 | 4 | 4 |
| Zentiva fingolimod | 2 | 2 | 2 |
| Total: 3 PDFs, 6 pages | 11 | 11 | 11 |

This is **11/11 date-interpretation coverage**, not 100% OCR accuracy. Duplicate values within a document collapse into one key. Numeric ambiguity is preserved as a candidate pair; the experiment does not decide which interpretation is correct. Five `Not yet distributed` cells are excluded from this denominator and listed explicitly. The reference uses supported HTML date cells parsed by the same normalization code, not independent human date gold. It does not measure false positives, batch/date association, table layout accuracy, every date on a page, degraded scans, or unseen suppliers. Native extraction ties OCR; OCR is unnecessary when reliable native text is available.

The [PDF report](../reports/mhra_pdf_ocr.json) includes source URLs/hashes, page transcripts, coverage and exclusions. Its offline checker recomputes document selection, expected values and exclusions from the frozen corpus, then rescores saved transcripts. It does not rerun Tesseract or authenticate a remote file that has since changed.

## Reproduce

Use Python 3.12 and the lockfile for the recorded model experiment. No API key or paid service is needed.

```bash
uv sync --frozen --python 3.12 --extra dev --extra research --extra tesseract
uv run python scripts/train_mhra.py --check
uv run python scripts/benchmark_mhra_pdf.py --check-report
uv run pytest tests/test_public_data.py tests/test_recalls.py -q

# Fit locally and export the model plus reports from the frozen corpus
uv run python scripts/train_mhra.py --model-output outputs/mhra/column-role-model.joblib

# Requires the native Tesseract executable; fetch pinned upstream packs first
uv run python scripts/fetch_ocr_models.py
uv run python scripts/benchmark_mhra_pdf.py

# Optional NEW network collection, kept separate from the frozen benchmark
uv run python scripts/collect_mhra.py --count 60 \
  --cache outputs/mhra/new-cache --output outputs/mhra/new-documents.json
```

Never load untrusted joblib/pickle files. Fresh collection may change source content and selection; annotate and version it separately before drawing new comparisons. CI retrains from the checked-in snapshot without network collection. Dependency versions, protocol, source hashes, split membership, predictions and top learned character features are in [the training report](../reports/mhra_training.json).

## Remaining Gaps

Public MHRA English is not a substitute for multilingual supplier documents. Five-language parsing and English/French/Vietnamese degraded-image checks remain **synthetic** experiments. There is no PaddleOCR verification, LlamaIndex deployment, Mistral/Phi-2 benchmark, trained OCR recognizer, independently measured user benefit, or production medical validation. Next steps are template-diverse public sources, independent annotations, explicit range/non-date handling, and occurrence-level PDF batch/date association tests.
