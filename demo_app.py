from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st

from pharma_ocr_date_rag.languages import LANGUAGES
from pharma_ocr_date_rag.pipeline import all_chunks, process_document, process_text
from pharma_ocr_date_rag.rag import retrieve
from pharma_ocr_date_rag.reporting import date_rows, export_csv, export_json

st.set_page_config(page_title="Pharma Date Review", layout="wide")
st.html("""
<style>
@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"] {
        width: 100%;
        min-width: 0;
    }
}
</style>
""")
st.title("Pharma Date Review")
st.caption("SYNTHETIC VENDOR DOCUMENTS  |  EN / FR / DE / ES / VI")

with st.sidebar:
    st.subheader("Document workspace")
    source = st.radio("Source", ["Sample library", "Paste text", "Upload text"], key="source")
    language = st.selectbox("Field language", list(LANGUAGES), format_func=LANGUAGES.get, key="language")
    orders = {"auto": "Unconfirmed", "dmy": "Day / month / year", "mdy": "Month / day / year"}
    date_order = st.selectbox(
        "Numeric date convention", list(orders), format_func=orders.get, key="date_order"
    )
    st.divider()
    st.caption("Research prototype. Synthetic examples. Human review required.")

docs = []
if source == "Sample library":
    collection = st.selectbox(
        "Collection",
        ["All samples", "English", "French", "German", "Spanish", "Vietnamese"],
        key="collection",
    )
    paths = sorted((ROOT / "data" / "synthetic_docs").glob("*.txt"))
    multi_paths = sorted((ROOT / "data" / "multilingual_docs").glob("*.txt"))
    if collection == "All samples":
        paths += multi_paths
    elif collection != "English":
        code = {"French": "fr", "German": "de", "Spanish": "es", "Vietnamese": "vi"}[collection]
        paths = [path for path in multi_paths if path.name.startswith(code + "_")]
    docs = [process_document(path, language=language, date_order=date_order) for path in paths]
elif source == "Paste text":
    text = st.text_area("Document text", height=180, key="document_text")
    if text:
        docs = [process_text("pasted-document.txt", text, language, date_order)]
else:
    uploaded = st.file_uploader("UTF-8 document", type=["txt", "md"], key="upload")
    if uploaded is not None:
        if uploaded.size > 1_000_000:
            st.error("Document exceeds the 1 MB text limit.")
        else:
            try:
                text = uploaded.getvalue().decode("utf-8-sig")
                docs = [process_text(Path(uploaded.name).name, text, language, date_order)]
            except UnicodeDecodeError:
                st.error("This document is not valid UTF-8 text.")

if not docs:
    st.info("No document selected.")
    st.stop()

rows = date_rows(docs)
review_count = sum(row["needs_review"] for row in rows)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Documents", len(docs))
c2.metric("Date fields", len(rows))
c3.metric("Needs review", review_count)
c4.metric("Ambiguous dates", sum(row["normalized"] is None for row in rows))

review_tab, evidence_tab, search_tab = st.tabs(["Date register", "Source evidence", "Search"])
with review_tab:
    left, right = st.columns([2, 1])
    with left:
        selected_labels = st.multiselect("Date types", sorted({row["label"] for row in rows}), key="labels")
    with right:
        only_review = st.checkbox("Needs review only", key="only_review")
    visible = [
        row
        for row in rows
        if (not selected_labels or row["label"] in selected_labels)
        and (not only_review or row["needs_review"])
    ]
    display = [
        {
            "Document": row["document"],
            "Line": row["line"],
            "Date": row["normalized"] or "Unresolved",
            "Type": row["label"],
            "Source text": row["raw_text"],
            "Review": ", ".join(reason.replace("_", " ") for reason in row["review_reasons"]) or "Clear",
        }
        for row in visible
    ]
    if display:
        st.dataframe(display, hide_index=True, use_container_width=True)
    else:
        st.info("No date fields match these filters.")
    st.caption(f"{len(visible)} of {len(rows)} fields")
    csv_col, json_col = st.columns(2)
    csv_col.download_button(
        "Export CSV", export_csv(visible), "date-register.csv", "text/csv", icon=":material/download:"
    )
    json_col.download_button(
        "Export JSON",
        export_json(visible),
        "date-evidence.json",
        "application/json",
        icon=":material/download:",
    )

with evidence_tab:
    name = st.selectbox("Document", [doc.path.name for doc in docs], key="evidence_document")
    doc = next(doc for doc in docs if doc.path.name == name)
    if doc.dates:
        index = st.selectbox(
            "Date field",
            list(range(len(doc.dates))),
            format_func=lambda i: f"{doc.dates[i].raw_text} | {doc.dates[i].label}",
            key=f"evidence_field_{name}",
        )
        hit = doc.dates[index]
        left, right = st.columns([2, 1])
        with left:
            highlighted = (
                html.escape(doc.ocr.text[: hit.start])
                + "<mark>"
                + html.escape(doc.ocr.text[hit.start : hit.end])
                + "</mark>"
                + html.escape(doc.ocr.text[hit.end :])
            )
            st.html(
                '<pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;'
                'line-height:1.6;padding:16px;background:#f4f6f5;color:#182b26;border-radius:6px">'
                + highlighted
                + "</pre>",
            )
        with right:
            st.subheader(hit.normalized or "Unresolved date")
            st.write("Field type:", hit.label)
            st.write("Precision:", hit.precision)
            if hit.review_reasons:
                for reason in hit.review_reasons:
                    st.warning(reason.replace("_", " ").capitalize())
            if len(hit.candidates) > 1:
                st.write("Possible dates:", ", ".join(hit.candidates))
            st.caption(f"Characters {hit.start}:{hit.end} | Label heuristic {hit.confidence:.2f}")
    else:
        st.code(doc.ocr.text, language=None)

with search_tab:
    question = st.text_input("Search document dates", "expiry", key="question")
    results = retrieve(all_chunks(docs), question)
    if not results:
        st.info("No matching evidence found.")
    for result in results:
        chunk = result.chunk
        with st.expander(f"{chunk.doc_id} / chunk {chunk.chunk_id}", expanded=True):
            st.caption(f"Characters {chunk.start}:{chunk.end} | Lexical score {result.score:.3f}")
            st.code(chunk.text, language=None)
