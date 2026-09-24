from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .dates import DATE_ORDERS
from .languages import LANGUAGES
from .pipeline import all_chunks, format_date_report, process_folder
from .rag import answer_question
from .reporting import date_rows, export_csv, export_json
from .review import DECISIONS, history, index_folder, queue, review


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and retrieve dates from pharma-style documents.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract dates from a folder")
    extract_parser.add_argument("folder", type=Path)
    extract_parser.add_argument("--format", choices=["text", "json", "csv"], default="text")

    ask_parser = subparsers.add_parser("ask", help="Ask a retrieval question")
    ask_parser.add_argument("folder", type=Path)
    ask_parser.add_argument("--question", required=True)

    index_parser = subparsers.add_parser("index", help="Index a versioned local review queue")
    index_parser.add_argument("folder", type=Path)
    index_parser.add_argument("--collection")
    queue_parser = subparsers.add_parser("queue", help="List extracted candidates as JSON")
    queue_parser.add_argument("--decision", choices=sorted(DECISIONS | {"pending", "all"}), default="pending")
    queue_parser.add_argument("--label")
    queue_parser.add_argument("--collection")
    queue_parser.add_argument("--limit", type=int, default=100)
    queue_parser.add_argument("--offset", type=int, default=0)
    review_parser = subparsers.add_parser("review", help="Append a human review decision")
    review_parser.add_argument("hit_id", type=int)
    review_parser.add_argument("--decision", choices=sorted(DECISIONS), required=True)
    review_parser.add_argument("--reviewer", required=True)
    review_parser.add_argument("--reason", required=True)
    history_parser = subparsers.add_parser("history", help="Show review events for a hit")
    history_parser.add_argument("hit_id", type=int)
    for command in [index_parser, queue_parser, review_parser, history_parser]:
        command.add_argument("--db", type=Path, default=Path("outputs/review.sqlite"))
    for subparser in (extract_parser, ask_parser, index_parser):
        subparser.add_argument("--language", choices=LANGUAGES, default="auto")
        subparser.add_argument("--date-order", choices=DATE_ORDERS, default="auto")
    args = parser.parse_args()
    try:
        if args.command == "index":
            result = index_folder(
                args.folder, args.db, args.collection, language=args.language, date_order=args.date_order
            )
        elif args.command == "queue":
            result = queue(
                args.db,
                decision=args.decision,
                label=args.label,
                collection=args.collection,
                limit=args.limit,
                offset=args.offset,
            )
        elif args.command == "review":
            result = review(args.db, args.hit_id, args.decision, args.reviewer, args.reason)
        elif args.command == "history":
            result = history(args.db, args.hit_id)
        else:
            result = None
        if result is not None:
            print(json.dumps(result, indent=2))
            return
        documents = process_folder(args.folder, language=args.language, date_order=args.date_order)
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as error:
        parser.error(str(error))

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
