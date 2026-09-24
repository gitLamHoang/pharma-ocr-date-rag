"""Local, versioned human review with parameterized SQL and append-only events."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

from .pipeline import process_document

EXTRACTOR_VERSION = "dates-v1"
DECISIONS = {"accepted", "rejected", "needs_review"}


@contextmanager
def database(path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValueError(f"Unsupported database schema {version}")
        connection.executescript(files("pharma_ocr_date_rag").joinpath("schema.sql").read_text())
        yield connection
    finally:
        connection.close()


def index_folder(folder: str | Path, db: str | Path, collection: str | None = None) -> dict:
    """Atomically add/update files; identical versions retain their review history.

    Missing files are not deleted. Use one logical collection per source folder.
    """
    folder = Path(folder)
    collection = (collection or folder.name).strip()
    if not collection:
        raise ValueError("Collection must not be empty")
    paths = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".txt", ".md", ".png", ".jpg", ".jpeg"}
    )
    result = {"collection": collection, "indexed": 0, "unchanged": 0, "reactivated": 0, "new_hits": 0}
    with database(db) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        for path in paths:
            digest = sha256(path.read_bytes()).hexdigest()
            existing = connection.execute(
                "SELECT id, active FROM documents WHERE collection=? AND path=? "
                "AND content_sha256=? AND extractor_version=?",
                (collection, path.name, digest, EXTRACTOR_VERSION),
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
            document = process_document(path)
            if sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Source changed during extraction: {path.name}")
            connection.execute(
                "UPDATE documents SET active=0 WHERE collection=? AND path=?", (collection, path.name)
            )
            cursor = connection.execute(
                "INSERT INTO documents(collection,path,content_sha256,extractor_version,engine) "
                "VALUES(?,?,?,?,?)",
                (collection, path.name, digest, EXTRACTOR_VERSION, document.ocr.engine),
            )
            connection.executemany(
                "INSERT INTO date_hits(document_id,normalized,label,extracted_text,context,heuristic_confidence) "
                "VALUES(?,?,?,?,?,?)",
                [
                    (cursor.lastrowid, h.normalized, h.label, h.raw_text, h.context, h.confidence)
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
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM review_queue" + where + " ORDER BY id LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            )
        ]


def review(db: str | Path, hit_id: int, decision: str, reviewer: str, reason: str) -> dict:
    if decision not in DECISIONS or not reviewer.strip() or not reason.strip():
        raise ValueError("A valid decision, reviewer and reason are required")
    with database(db) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if not connection.execute("SELECT id FROM review_queue WHERE id=?", (hit_id,)).fetchone():
            raise ValueError("Hit does not exist or belongs to an inactive document version")
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
