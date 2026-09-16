from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pharma_ocr_date_rag.experiments import RetrievalCase, evaluate_chunk_sizes
from pharma_ocr_date_rag.pipeline import process_folder


CASES = [
    RetrievalCase(
        question="Which document mentions the expiry date for the Delta cold chain vendor?",
        expected_doc="delta_noisy_scan.txt",
        expected_label="expiry",
    ),
    RetrievalCase(
        question="When was the supplier audit planned?",
        expected_doc="beta_excipient_report.txt",
        expected_label="audit",
    ),
    RetrievalCase(
        question="Find the QA or chamber check date.",
        expected_doc="gamma_stability_notice.txt",
        expected_label="qa_check",
    ),
]


def main() -> None:
    docs = process_folder(ROOT / "data" / "synthetic_docs")
    rows = evaluate_chunk_sizes(docs, CASES, chunk_sizes=[35, 60, 90], top_k=3)

    print("chunk_words,hits,total,hit_rate")
    for row in rows:
        print(f"{row.chunk_words},{row.hits},{row.total},{row.hit_rate:.2f}")


if __name__ == "__main__":
    main()
