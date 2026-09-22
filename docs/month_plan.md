# One Month Work Plan

This file is a truthful plan for future commits. It is not fake commit history.

## Week 1

- Build the basic date extractor.
- Add synthetic documents and expected labels.
- Write first tests for date formats.

## Week 2

- Add OCR adapters for Tesseract and PaddleOCR.
- Collect notes about OCR mistakes.
- Add more noisy synthetic examples.

## Week 3

- Add chunking and retrieval experiments.
- Compare short chunks vs long chunks.
- Write down Mistral and Phi-2 observations from experiments.

Progress note: added a small chunk-size benchmark script that reports hit-rate for a few synthetic retrieval questions.

## Week 4

- Clean up Streamlit demo.
- Improve README screenshots.
- Add final evaluation table and reflection.

Progress note: the evaluation script now reports per-label precision, recall, and F1 in addition to the overall score. This makes weak date categories easier to spot.
