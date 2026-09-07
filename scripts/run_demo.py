from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pharma_ocr_date_rag.pipeline import all_chunks, format_date_report, process_folder
from pharma_ocr_date_rag.rag import answer_question, try_llama_index_summary


def main() -> None:
    docs = process_folder(ROOT / "data" / "synthetic_docs")
    for doc in docs:
        print(format_date_report(doc))
        print()

    print(try_llama_index_summary(all_chunks(docs)))
    print()
    print(answer_question(all_chunks(docs), "Which dates look like expiry dates?"))


if __name__ == "__main__":
    main()
