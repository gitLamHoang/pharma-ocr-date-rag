# Two-Minute Demo

## Run

Follow the README installation commands, then start Streamlit with demo_app.py. Use the bundled sample library.

## Show

1. Open the date register. There are eight synthetic documents and 42 candidate date fields. Filter to fields needing review.
2. Select the French collection. Open Source evidence and select the supplier-visit field. The source says 09/10/2026; the result contains both September 10 and October 9.
3. Change Numeric date convention to Day / month / year. The value becomes 2026-10-09. Explain that the reviewer supplied a convention; the parser did not infer one from the language.
4. Select the Vietnamese collection. Inspect the manufacture field and its original accented source text.
5. Return to All samples and search for expiry. English terminology can retrieve matching field concepts from the other supported vocabularies.
6. Search for astronomy. The search returns no matching evidence.
7. Export JSON. Point to the original text, source span, document text hash and candidate list.

## Explain the Engineering

A useful explanation, in your own words:

"I started with a document-review problem: one file can contain several dates with different meanings. This public prototype creates a date register with source evidence. The hardest part is deciding what not to normalize automatically. For an ambiguous date, it preserves alternatives until the reviewer supplies a convention."

Then explain the trade-off:

"The current core is deterministic and runs locally. That makes errors easier to reproduce, but its vocabulary and layout coverage are limited. The multilingual tests are synthetic development examples. My next step is to test actual image OCR and a more challenging retrieval dataset."

Be ready to explain how the parser distinguishes month precision from a complete date, why language and date order are separate settings, and why a perfect score on 42 authored cases is not a real-world accuracy claim.

## Evidence You Can Point To

- scripts/benchmark_multilingual.py and data/multilingual_cases.json
- docs/benchmark_results.json, including the fixture hash
- tests/test_multilingual.py for source positions and ambiguity
- tests/test_demo.py for real app-state interactions
- GitHub Actions test results and the normal commit history

This repository was developed with AI coding assistance. Review the implementation and run the examples before discussing technical ownership. Separate this public synthetic reconstruction from any original employer work. Do not present future milestones as finished or synthetic scores as employer results.
