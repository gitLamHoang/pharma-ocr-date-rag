from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .dates import DATE_ORDERS
from .languages import LANGUAGES
from .pipeline import all_chunks, format_date_report, process_folder
from .policies import load_date_order_map
from .rag import answer_question
from .reporting import date_rows, export_csv, export_json
from .review import (
    DECISIONS,
    DOCUMENT_ACTIONS,
    DOCUMENT_STATES,
    document_action,
    document_history,
    document_versions,
    history,
    index_folder,
    queue,
    review,
)


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
    documents_parser = subparsers.add_parser(
        "documents", help="List local document versions and source state"
    )
    documents_parser.add_argument("--collection")
    documents_parser.add_argument("--state", choices=sorted(DOCUMENT_STATES), default="active")
    documents_parser.add_argument("--limit", type=int, default=100)
    documents_parser.add_argument("--offset", type=int, default=0)
    document_parser = subparsers.add_parser("document", help="Reopen, retire or restore one document version")
    document_parser.add_argument("action", choices=sorted(DOCUMENT_ACTIONS))
    document_parser.add_argument("document_id", type=int)
    document_parser.add_argument("--reviewer", required=True)
    document_parser.add_argument("--reason", required=True)
    document_history_parser = subparsers.add_parser("document-history", help="Show document lifecycle events")
    document_history_parser.add_argument("document_id", type=int)
    for command in [
        index_parser,
        queue_parser,
        review_parser,
        history_parser,
        documents_parser,
        document_parser,
        document_history_parser,
    ]:
        command.add_argument("--db", type=Path, default=Path("outputs/review.sqlite"))
    for subparser in (extract_parser, ask_parser, index_parser):
        subparser.add_argument("--language", choices=LANGUAGES, default="auto")
        subparser.add_argument("--date-order", choices=DATE_ORDERS, default="auto")
        subparser.add_argument(
            "--date-order-map",
            type=Path,
            help="JSON object of exact filenames to auto/dmy/mdy; overrides the batch default",
        )
    args = parser.parse_args()
    try:
        policy_path = getattr(args, "date_order_map", None)
        policies = load_date_order_map(policy_path) if policy_path is not None else None
        if args.command == "index":
            result = index_folder(
                args.folder,
                args.db,
                args.collection,
                language=args.language,
                date_order=args.date_order,
                date_order_map=policies,
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
        elif args.command == "documents":
            result = document_versions(
                args.db, collection=args.collection, state=args.state, limit=args.limit, offset=args.offset
            )
        elif args.command == "document":
            result = document_action(args.db, args.document_id, args.action, args.reviewer, args.reason)
        elif args.command == "document-history":
            result = document_history(args.db, args.document_id)
        else:
            result = None
        if result is not None:
            print(json.dumps(result, indent=2))
            return
        documents = process_folder(
            args.folder,
            language=args.language,
            date_order=args.date_order,
            date_order_map=policies,
        )
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
