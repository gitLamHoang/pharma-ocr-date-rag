from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import all_chunks, format_date_report, process_folder
from .rag import answer_question


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and retrieve dates from pharma-style documents.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract dates from a folder")
    extract_parser.add_argument("folder", type=Path)

    ask_parser = subparsers.add_parser("ask", help="Ask a retrieval question")
    ask_parser.add_argument("folder", type=Path)
    ask_parser.add_argument("--question", required=True)

    args = parser.parse_args()
    documents = process_folder(args.folder)

    if args.command == "extract":
        for document in documents:
            print(format_date_report(document))
            print()
        return

    if args.command == "ask":
        print(answer_question(all_chunks(documents), args.question))
