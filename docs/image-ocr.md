# Image OCR Experiment

This experiment sends actual image pixels to Tesseract, then passes the recognized text to the date extractor. It is separate from the browser's text-backed snapshot and from the 42-case text regression benchmark. Only synthetic public fixtures are used.

## Question and Protocol

Does a correct text parser still recover the right date fields after image recognition?

- Three existing rendered source pages: English packaging certificate, French certificate, Vietnamese inspection form. They contain 16 manually specified date fields in total.
- Each page is tested unchanged and with the same fixed degradation: grayscale, resize to 55% using bilinear resampling, Gaussian blur radius 0.4, then 1.2-degree bicubic rotation with white fill. These are six image inputs, not six independent documents.
- Gold fields live in [`data/ocr_cases.json`](../data/ocr_cases.json). The experiment never generates gold from the extractor. The original text is scored separately to distinguish a parser regression from OCR-induced errors.
- Tesseract uses its LSTM engine (`--oem 1`) and a single-block segmentation setting (`--psm 6`), with a 30-second recognition timeout per image. This is one fixed setting, not a tuned engine comparison.
- OCR packs are `eng`, `fra`, and `vie`, respectively. The date parser uses `en`, `fr`, and `vi`, with numeric order left at `auto`. French/Vietnamese audit dates must retain both interpretations to count as correct.
- All three `tessdata_fast` models come from one pinned upstream revision and have verified SHA-256 checksums. No model is trained or fine-tuned here.

## Measured Results

Recorded September 26, 2026 on macOS arm64 with Tesseract 5.5.3, pytesseract 0.3.13, Pillow 11.3.0 and Python 3.9. The [complete report](../reports/image_ocr.json) includes exact environment details, raw OCR text, original OCR-text spans, predictions, missed/extra fields, hashes and elapsed time.

| Input | English matches | French matches | Vietnamese matches | Total matches | Extra fields | Exact pages |
| --- | --- | --- | --- | --- | --- | --- |
| Original UTF-8 text | 4/4 | 6/6 | 6/6 | 16/16 | 0 | 3/3 |
| Clean page images | 4/4 | 6/6 | 6/6 | 16/16 | 0 | 3/3 |
| Degraded page images | 1/4 | 3/6 | 4/6 | 8/16 | 4 | 0/3 |

All six OCR runs completed; none was unavailable or failed to execute. For degraded images, micro precision is 8/12 = 0.667, recall is 8/16 = 0.500, and F1 is 0.571. Clean-image field precision/recall/F1 are 1.000 on these three authored pages, **not a general accuracy estimate**.

The unit is an occurrence of `(label, normalized date, candidate interpretations)` within a page. Duplicate predictions count as extras; matches cannot move across pages. A wrong date or label counts as one missed gold field and one extra prediction. Exact-page matching requires no missing or extra fields. This is downstream field evaluation, not character-error rate or layout accuracy. A perfect field score does not mean the whole OCR transcript is correct.

## What Failed

| Source evidence | Degraded OCR output | Downstream effect |
| --- | --- | --- |
| English document date `2026-04-23` | `2026-06-23` | A plausible but wrong date passes calendar validation |
| English manufacture `15 Apr 2026` | `18 Ape 2026` | Missed date: the month word is no longer recognized |
| French received date `24 mars 2026` | `24 mars 2025` | Wrong year still forms a valid date |
| French `Prochaine visite fournisseur` | `Prochaine vit fournisseur` | Ambiguous date remains, but its audit label becomes unknown |
| Vietnamese audit `09/10/2026` | `0/10/2026` | Invalid date is rejected instead of guessed |

The practical lesson: validation can reject impossible dates, but cannot detect every plausible transcription error. Source review is still needed. These failures are retained rather than repaired with rules specific to these pages. Better scan quality, OCR boxes/token scores and an independently labeled dataset are useful next experiments; none has been proven to solve this problem here.

## Reproduce

Install the Tesseract system executable first. On macOS use `brew install tesseract`; on Ubuntu use `sudo apt-get install tesseract-ocr`. The experiment downloads only its three pinned packs, independently of system language-pack defaults. See the upstream [Tesseract CLI documentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html) and [pytesseract API](https://github.com/madmaze/pytesseract).

From the repository root:

```bash
uv sync --frozen --python 3.9 --extra dev --extra tesseract
uv run python scripts/fetch_ocr_models.py
uv run python scripts/benchmark_ocr.py --require-complete --output outputs/my-image-ocr.json
```

Use Python 3.9 to match the checked-in Python/Pillow combination, or 3.12 to exercise the current CI environment. The native Tesseract version is not installed or pinned by `uv`. Different engine, native library or Pillow versions can change pixels and predictions; compare reports instead of expecting identical timestamps, timing or OCR output.

The model fetcher verifies cached files and newly downloaded bytes against [`ocr_models.json`](../data/ocr_models.json). An unexpected checksum is an error, not a reason to silently substitute a model. Models are Apache-2.0-licensed upstream assets, retained under ignored `outputs/tessdata/`, not redistributed in this repo. Upstream [license](https://github.com/tesseract-ocr/tessdata_fast/blob/87416418657359cb625c412a48b6e1d6d41c29bd/LICENSE). Degraded images are generated under ignored `outputs/ocr-images/`; the original committed images are unchanged.

`--require-complete` returns nonzero for an unavailable backend/pack or execution failure. Measured extraction mistakes remain visible results, not skipped tests or command failures. Incomplete reports retain every attempted page and show both attempted and measured denominators; they cannot pass as checked-in evidence. Timing covers image preparation, environment checks, OCR and extraction, not isolated engine throughput.

To verify the checked-in report without installing OCR:

```bash
python scripts/benchmark_ocr.py --check-report
```

This checks source/input/model provenance and recomputes fields and scores from **saved OCR text**. It does not rerun OCR or regenerate degraded image bytes. A separate CI job installs Tesseract, runs all six inputs, and uploads `image-ocr-results`. That job gates execution completeness, not a universal accuracy threshold.

After a relevant parser/adapter/fixture change, rerun `python scripts/benchmark_ocr.py --require-complete` to replace the checked-in report, inspect the differences, and update this result table. Do not copy old measurements under new source hashes.

## Python API and Boundaries

```python
from pharma_ocr_date_rag.dates import extract_dates
from pharma_ocr_date_rag.ocr import read_tesseract, tesseract_info

print(tesseract_info("outputs/tessdata"))
ocr = read_tesseract(
    "web/public/documents/fr_certificat.png",
    language="fra",
    psm=6,
    tessdata_dir="outputs/tessdata",
    timeout=30,
)
fields = extract_dates(ocr.text, language="fr", date_order="auto")
```

`OCRUnavailable` means an optional dependency, executable or requested pack is missing. `OCRExecutionError` means image loading, recognition, or the environment probe failed. The default `read_document(..., engine="auto")` only tries another backend when Tesseract is unavailable, not after corrupt input or timeout. Explicit Tesseract calls never fall back to another language or engine.

The standard folder CLI still defaults to English image OCR; its `--language` controls extraction vocabulary, not OCR packs. Non-English image recognition uses the explicit API above or this benchmark. Streamlit remains UTF-8 text-only, and the hosted workspace does not perform OCR. The existing PaddleOCR adapter is still unverified. German, Spanish, mixed-language pages, real scans, handwriting, PDFs and table layouts have not been measured by this experiment. Character offsets point into the OCR transcript, not image coordinates; OCR confidence remains unset rather than pretending process success is calibrated confidence.
