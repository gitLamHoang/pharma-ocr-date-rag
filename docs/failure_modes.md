# Failure Mode Notes

These notes are from the public synthetic version of the project.

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
