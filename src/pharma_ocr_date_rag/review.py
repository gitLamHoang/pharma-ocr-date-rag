"""Local, versioned human review with parameterized SQL and append-only events."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

from .languages import validate_language
from .pipeline import document_paths, process_document
from .policies import resolve_date_orders

EXTRACTOR_VERSION = "dates-v2-multilingual"
DECISIONS = {"accepted", "rejected", "needs_review"}


def _execute_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute complete SQL statements without executescript's implicit commit."""
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""


@contextmanager
def database(path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = OFF")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError(f"Unsupported database schema {version}")
            if version == 1:
                migration = files("pharma_ocr_date_rag").joinpath("migrate_v1.sql").read_text()
                _execute_script(connection, migration)
            _execute_script(connection, files("pharma_ocr_date_rag").joinpath("schema.sql").read_text())
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Database migration failed foreign key validation")
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


def index_folder(
    folder: str | Path,
    db: str | Path,
    collection: str | None = None,
    language: str = "auto",
    date_order: str = "auto",
    date_order_map: Mapping[str, str] | None = None,
) -> dict:
    """Atomically add/update files; identical versions retain their review history.

    Missing files are not deleted. Use one logical collection per source folder.
    """
    folder = Path(folder)
    validate_language(language)
    collection = (collection or folder.name).strip()
    if not collection:
        raise ValueError("Collection must not be empty")
    paths = document_paths(folder)
    orders = resolve_date_orders(paths, date_order, date_order_map)
    result = {"collection": collection, "indexed": 0, "unchanged": 0, "reactivated": 0, "new_hits": 0}
    with database(db) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        for path in paths:
            order = orders[path.name]
            extractor_version = f"{EXTRACTOR_VERSION};language={language};date_order={order}"
            digest = sha256(path.read_bytes()).hexdigest()
            existing = connection.execute(
                "SELECT id, active FROM documents WHERE collection=? AND path=? "
                "AND content_sha256=? AND extractor_version=?",
                (collection, path.name, digest, extractor_version),
            ).fetchone()
            if existing and existing["active"]:
                result["unchanged"] += 1
                continue
            if existing:
                connection.execute(
                    "UPDATE documents SET active=0 WHERE collection=? AND path=?", (collection, path.name)
                )
                connection.execute("UPDATE documents SET active=1 WHERE id=?", (existing["id"],))
                result["reactivated"] += 1
                continue
            document = (
                process_document(path)
                if language == order == "auto"
                else process_document(path, language=language, date_order=order)
            )
            if sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Source changed during extraction: {path.name}")
            connection.execute(
                "UPDATE documents SET active=0 WHERE collection=? AND path=?", (collection, path.name)
            )
            cursor = connection.execute(
                "INSERT INTO documents(collection,path,content_sha256,extractor_version,engine) "
                "VALUES(?,?,?,?,?)",
                (collection, path.name, digest, extractor_version, document.ocr.engine),
            )
            connection.executemany(
                "INSERT INTO date_hits(document_id,normalized,label,extracted_text,context,heuristic_confidence,"
                "candidates_json,precision,review_reasons_json,source_start,source_end) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        cursor.lastrowid,
                        h.normalized,
                        h.label,
                        h.raw_text,
                        h.context,
                        h.confidence,
                        json.dumps(h.candidates),
                        h.precision,
                        json.dumps(h.review_reasons),
                        h.start,
                        h.end,
                    )
                    for h in document.dates
                ],
            )
            result["indexed"] += 1
            result["new_hits"] += len(document.dates)
    return result


def queue(
    db: str | Path,
    *,
    decision: str = "pending",
    label: str | None = None,
    collection: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    if decision not in DECISIONS | {"pending", "all"} or not 1 <= limit <= 1000 or offset < 0:
        raise ValueError("Invalid queue filter or pagination")
    clauses, parameters = [], []
    for column, value in [
        ("decision", None if decision == "all" else decision),
        ("label", label),
        ("collection", collection),
    ]:
        if value is not None:
            clauses.append(f"{column}=?")  # column names come only from this fixed allowlist
            parameters.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with database(db) as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM review_queue" + where + " ORDER BY id LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            )
        ]
        for row in rows:
            row["candidates"] = json.loads(row.pop("candidates_json")) or (
                [row["normalized"]] if row["normalized"] else []
            )
            row["review_reasons"] = json.loads(row.pop("review_reasons_json"))
        return rows


def review(db: str | Path, hit_id: int, decision: str, reviewer: str, reason: str) -> dict:
    if decision not in DECISIONS or not reviewer.strip() or not reason.strip():
        raise ValueError("A valid decision, reviewer and reason are required")
    with database(db) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        hit = connection.execute("SELECT * FROM review_queue WHERE id=?", (hit_id,)).fetchone()
        if not hit:
            raise ValueError("Hit does not exist or belongs to an inactive document version")
        if decision == "accepted" and hit["normalized"] is None:
            raise ValueError("Resolve the ambiguous date convention and reindex before accepting")
        cursor = connection.execute(
            "INSERT INTO review_events(hit_id,decision,reviewer,reason) VALUES(?,?,?,?)",
            (hit_id, decision, reviewer.strip(), reason.strip()),
        )
        return dict(
            connection.execute("SELECT * FROM review_events WHERE id=?", (cursor.lastrowid,)).fetchone()
        )


def history(db: str | Path, hit_id: int) -> list[dict]:
    with database(db) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM review_events WHERE hit_id=? ORDER BY id",
                (hit_id,),
            )
        ]
