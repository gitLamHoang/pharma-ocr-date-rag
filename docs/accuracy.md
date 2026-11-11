# Accuracy on synthetic scans

This page records how well the offline pipeline (rules only, `--ai off`) finds dates on
synthetic scanned pages, before and after the OCR preprocessing and date-format work. All numbers
come from generated pages. No real document text is reproduced here.

## How it is measured

```sh
uv run --project backend python eval/synth.py generate --n 300 --seed 7 --out eval/synth
uv run --project backend python eval/run_eval.py --ai off --set synth
```

- **Pages.** 300 made-up English pages: certificates of analysis, certificates of a pharmaceutical
  product with notarization, apostille and legalization stamps, SOP signature blocks, and batch
  labels. They hold 1,319 dates in 21 printed formats, from `2026-03-12` and `12/03/2026` to
  `12.III.2026`, `12 . 03 . 2026`, `12MAR2026`, `EXP03/2027` and `MAR 2027`. Every page also
  carries look-alikes that are not dates, such as lot numbers, standard numbers and phone numbers.
- **Degradation levels.** Each level covers 36 to 40 pages:
  - clean: the 200 DPI render as is;
  - 150 DPI: resampled to 150 DPI;
  - blur: Gaussian blur, radius 0.6;
  - rotate: rotated 0.5 to 2 degrees either way;
  - JPEG: saved at JPEG quality 40;
  - salt: 1% salt-and-pepper noise;
  - stamp: a translucent round stamp over one date;
  - mixed: three of the above together.
- **Gold labels.** The generator writes them from the values it printed. Nothing comes from the
  extractor.
- **Detection.** A found date matches a gold date on the same page when both have the same
  possible values. An ambiguous `12/03/2026` must keep both readings. Precision is the share of
  found dates that match a gold date. Recall is the share of gold dates that were found. The date
  type is not scored here, because offline type labels are not a release target (spec §11.6).
- **Gate.** Every run has 0 hallucinations (a date whose text is not on the page) and 0 silent
  resolutions (an ambiguous date given one value without evidence).

## Before and after, per degradation level

| Level | Pages | Gold dates | Precision before | Recall before | Precision after | Recall after |
|---|---:|---:|---:|---:|---:|---:|
| clean | 40 | 179 | 0.99 | 0.56 | 1.00 | 0.98 |
| 150 DPI | 40 | 180 | 0.98 | 0.61 | 0.99 | 0.97 |
| blur 0.6 | 40 | 174 | 0.99 | 0.50 | 0.98 | 0.96 |
| rotate ±2° | 36 | 155 | 0.99 | 0.53 | 1.00 | 0.98 |
| JPEG q40 | 36 | 159 | 0.97 | 0.56 | 1.00 | 0.99 |
| salt noise | 36 | 160 | 0.98 | 0.55 | 0.99 | 0.95 |
| stamp over a date | 36 | 157 | 0.87 | 0.34 | 0.98 | 0.54 |
| mixed | 36 | 155 | 0.97 | 0.36 | 0.97 | 0.75 |
| **all** | **300** | **1,319** | **0.971** | **0.504** | **0.989** | **0.894** |

Hallucinations and silent resolutions were 0 before and after at every level.

## What each change added

Each change was kept only if overall recall went up, precision fell by no more than 1 point,
and hallucinations and silent resolutions stayed at 0. Each row adds one change to the row above.

| Step | Precision | Recall |
|---|---:|---:|
| Baseline | 0.971 | 0.504 |
| Date formats: roman months, spaced numerics, noisy month abbreviations and compact forms, month and year, label-adjacent `EXP`/`MFG`/`MFD`, and OCR digit repair (O, I, l, S, B) inside date-shaped tokens | 0.986 | 0.866 |
| Second OCR pass on a cleaned image, keeping the pass with the higher mean word confidence. The cleaning is grayscale, median denoise, projection-profile deskew, upscaling when the x-height is under 20 px, and an adaptive threshold. | 0.990 | 0.873 |
| OCR repair inside roman months (`1V`, `X11`, `Ill`) | 0.989 | 0.894 |

With the final rules and no second pass, the result is precision 0.987 and recall 0.888. The
second pass therefore adds 0.6 points of recall overall. It helps most on salt noise (+7.5 points)
and mixed pages (+5.8). It costs recall on stamped pages (−5.8) and doubles OCR time on scanned
pages.

## Known gaps

- A stamp over a date is still the hardest case. Recall there is 0.54.
- Roman-month dates are the weakest format, with recall from 0.76 to 0.80. Tesseract reads `I` as
  `1`, `l` or `|`. A lone `l` month is left unread on purpose, because it could be `I` or `1`.
- These pages are synthetic. They use one typeface and draw stamps in flat ink, so they show the
  direction of a change more reliably than real-world accuracy.
