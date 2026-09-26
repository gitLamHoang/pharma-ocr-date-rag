# Failure Mode Notes

These notes are from the public synthetic version of the project.

## September 26 Image Findings

Actual Tesseract recognition on the three synthetic English/French/Vietnamese pages matched 16/16 fields when clean and 8/16 after fixed degradation, with four extra predictions. The full [image experiment](image-ocr.md) retains the raw text and wrong predictions. All six OCR runs completed.

- `2026-04-23` became `2026-06-23`: both pass calendar validation. Valid syntax cannot establish transcription accuracy.
- `24 mars 2026` became `24 mars 2025`: the right label and day/month still hide a wrong year.
- A damaged French audit label produced an unknown label even while the date's numeric ambiguity was preserved.
- Vietnamese `09/10/2026` became invalid `0/10/2026` and was rejected. That is a missed field, not a correctly recovered date.
- Missing packs and execution failures are recorded separately from measured extraction misses. Neither is counted as a successful page.

These are controlled rendered pages, not real scans or an independently held-out benchmark. The findings motivate source review, not an accuracy claim about production documents.

## September 24 Findings

- Numeric dates with two valid interpretations now stay unresolved until the user chooses a convention. The original English evaluation explicitly uses MDY.
- OCR repairs now preserve source positions and expose the original characters with review reasons.
- Multilingual field terms and month names are supported for five languages, but decomposed Unicode and complex layouts need further coverage.
- Retrieval now abstains on zero lexical overlap. The shared field vocabulary supports limited cross-language search, not arbitrary semantic translation.
- Chunk sizes now count words accurately; overlap no longer means a hard-coded pair of lines. Field fragments at chunk boundaries remain a limitation.
- Perfect development-fixture results do not establish performance on real scans. Image OCR and model comparisons remain unmeasured.

## OCR Problems

- `EXP` can be read as `E XP`, especially when the scan is low resolution.
- `2026/07/21` may be split across lines, which breaks simple regex matching.
- Month names work better than numeric dates because `07/08/2026` can mean different things in different countries.

## Extraction Problems

- Month/year dates like `07/2029` are valid expiry dates, but they do not have a day.
- Document dates are common and can distract retrieval from product dates.
- A context window can include two labels, for example `quality review` near an `EXP` field.

## Retrieval Problems

- Short chunks keep date context close, but they can miss the document title.
- Large chunks improve recall but can mix multiple date types together.
- Keyword retrieval is easy to debug but not very semantic.

## Next Improvements

- Add confidence calibration by OCR engine.
- Store page number and bounding boxes for each date.
- Add a second-pass classifier for ambiguous date context.
- Compare a small local model against API models using the same eval file.

## Week 1 Update

I added a small OCR-noise repair step for date-looking tokens. It fixes examples like `2O26.O8.21` before the regex parser runs, but it avoids replacing every letter `O` in the whole document. This is safer for fields like lot numbers and material names.
