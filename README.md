# Pharma OCR Date RAG Lab

Freshman portfolio project for finding important dates in pharmaceutical vendor documents.

This is a public, anonymized version of an OCR-to-retrieval pipeline. It uses only synthetic sample documents, so there are no Pfizer files, vendor names, patient data, or confidential details in this repository.

## Why I Made This

Pharmaceutical documents contain lots of dates: expiry dates, manufacturing dates, review dates, audit dates, and check dates. A small OCR mistake can change how a document is understood, so I wanted to build a simple pipeline that:

- reads a document with OCR or plain text
- extracts dates with nearby context
- classifies what each date probably means
- retrieves the most relevant chunks for a question
- evaluates where the pipeline fails

## Tech Used

- Python
- Tesseract OCR, optional
- PaddleOCR, optional
- LlamaIndex, optional
- Regex and simple retrieval fallback
- Pytest for small tests
- Streamlit demo, optional

The lightweight version runs with just Python. The OCR/RAG libraries are optional because they are heavy and can be hard to install on a small laptop.

## Project Structure

```text
src/pharma_ocr_date_rag/
  cli.py          command line entry point
  dates.py        date parsing and context classification
  ocr.py          OCR/text loading adapters
  pipeline.py     connects OCR, extraction, and retrieval
  rag.py          simple chunk retrieval plus optional LlamaIndex hook

data/synthetic_docs/
  fake vendor document text files

scripts/
  run_demo.py     quick demo
  evaluate.py     evaluation script

tests/
  unit tests for date extraction and retrieval
```

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/run_demo.py
pytest
```

Ask a question from the command line:

```bash
pharma-date-rag ask data/synthetic_docs --question "Which dates look like expiry dates?"
```

Run the evaluation:

```bash
python scripts/evaluate.py
```

Optional Streamlit demo:

```bash
pip install -e ".[demo]"
streamlit run demo_app.py
```

## Example Output

```text
alpha_packaging_coa.txt
  2026-04-15  manufacture  "Manufacture Date: 15 Apr 2026"
  2028-04-14  expiry       "Expiry Date: 14 Apr 2028"
  2026-04-22  qa_check     "QA check completed on 04/22/2026"
```

## What I Benchmarked

The public repo keeps the benchmarking small, but the workflow is the same idea:

- OCR engine comparison: clean text vs noisy OCR text
- chunk size comparison: short chunks vs larger chunks
- retrieval comparison: keyword retrieval vs optional LlamaIndex index
- model notes: Mistral-style instruction following vs Phi-2-style smaller model behavior

I tracked failure modes like:

- OCR confusing `1`, `I`, and `l`
- OCR confusing `O` and `0` inside date fields
- month/day ambiguity
- expiry dates written as only month/year
- document dates being confused with product dates
- retrieval returning the right page but wrong nearby date

## Limits

This is a learning project, not a validated medical device or production quality system. It does not make release decisions. It is meant to show the engineering workflow and how I thought through the problem.

## LinkedIn-Friendly Summary

Built an anonymized OCR-to-RAG prototype for pharmaceutical-style vendor documents using Tesseract/PaddleOCR adapters, date extraction, lightweight retrieval, and an evaluation workflow. Compared chunking and retrieval settings, documented OCR/date-classification failure modes, and built a small demo for reviewing model trade-offs.
