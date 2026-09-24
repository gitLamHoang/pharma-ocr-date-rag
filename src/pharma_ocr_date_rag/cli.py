from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import all_chunks, format_date_report, process_folder
from .rag import answer_question
from .dates import DATE_ORDERS
from .languages import LANGUAGES
from .reporting import date_rows, export_csv, export_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and retrieve dates from pharma-style documents.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract dates from a folder")
    extract_parser.add_argument("folder", type=Path)
    extract_parser.add_argument("--format", choices=["text", "json", "csv"], default="text")

    ask_parser = subparsers.add_parser("ask", help="Ask a retrieval question")
    ask_parser.add_argument("folder", type=Path)
    ask_parser.add_argument("--question", required=True)

    for subparser in (extract_parser, ask_parser):
        subparser.add_argument("--language", choices=LANGUAGES, default="auto")
        subparser.add_argument("--date-order", choices=DATE_ORDERS, default="auto")

    args = parser.parse_args()
    documents = process_folder(args.folder, language=args.language, date_order=args.date_order)

    if args.command == "extract":
        if args.format != "text":
            rows = date_rows(documents)
            print(export_json(rows) if args.format == "json" else export_csv(rows))
            return
        for document in documents:
            print(format_date_report(document))
            print()
        return

    if args.command == "ask":
        print(answer_question(all_chunks(documents), args.question))
