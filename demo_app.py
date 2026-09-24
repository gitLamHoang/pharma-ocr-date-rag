from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st

from pharma_ocr_date_rag.pipeline import all_chunks, format_date_report, process_folder
from pharma_ocr_date_rag.rag import answer_question

st.set_page_config(page_title="Document Date Review", layout="wide")
st.title("Document Date Review")
st.caption(
    "Four synthetic text documents · local extraction and retrieval · review queue available in the CLI"
)

sample_folder = ROOT / "data" / "synthetic_docs"
docs = process_folder(sample_folder)

question = st.text_input("Question", "Which dates look like expiry dates?")
left, right = st.columns(2)

with left:
    st.subheader("Date Extraction")
    for doc in docs:
        st.code(format_date_report(doc))

with right:
    st.subheader("Retrieval")
    st.code(answer_question(all_chunks(docs), question))
