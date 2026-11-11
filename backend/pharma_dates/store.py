"""Step 6: documents, runs, pages, dates, flags and the append-only review log in one SQLite file (WAL).

Every run of the pipeline gets its own rows; only the document's latest run takes new reviews, older
runs are frozen. A date's status and current type/value are read from its review events, which the
database refuses to update or delete.
"""

import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .models import BBox, Flag, LabeledDate, PageLayout, Word
from .taxonomy import ALL_TYPES, family_of

RUN_STATUSES = ("queued", "reading", "classifying", "validating", "done", "failed")
ACTIONS = ("accept", "correct", "reject", "reopen")
_STATUS_OF = {
    None: "needs_review",
    "reopen": "needs_review",
    "accept": "accepted",
    "correct": "corrected",
    "reject": "rejected",
}
_VALUE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")
_SCHEMA = Path(__file__).with_name("schema.sql")


class FrozenRunError(Exception):
    """A review was sent for a date whose run is no longer the document's latest run."""


class Document(BaseModel):
    id: int
    filename: str
    sha256: str
    pages: int
    status: str
    created_at: datetime
    ai_model: str | None
    pipeline_version: str | None


class Run(BaseModel):
    id: int
    document_id: int
    pipeline_version: str
    ai_model: str | None
    ai_used: bool
    started_at: datetime
    finished_at: datetime | None
    status: str
    error: str | None


class DocumentSummary(BaseModel):
    id: int
    name: str
    pages: int
    status: str  # of the latest run
    error: str | None  # of the latest run; safe to show
    n_dates: int
    n_flags: int
    n_needs_review: int
    created_at: datetime


class StoredPage(PageLayout):
    image_path: str | None


class DateWithStatus(LabeledDate):
    """A stored date. `id` is the database id; `date_type`/`family` stay the pipeline's label."""

    id: int
    candidate_id: str
    run_id: int
    document_id: int
    status: Literal["needs_review", "accepted", "corrected", "rejected"]
    current_type: str
    current_family: str
    current_value: str | None
    carried_from_run: int | None


class StoredFlag(Flag):
    id: int
    date_ids: list[int]


class ReviewEvent(BaseModel):
    id: int
    date_id: int
    action: Literal["accept", "correct", "reject", "reopen"]
    new_type: str | None
    new_value: str | None
    reviewer: str
    reason: str
    at: datetime
    carried_from_run: int | None


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA.read_text(encoding="utf-8"))

    @contextmanager
    def _connect(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        """One connection per call (safe across worker threads); `write` holds the write lock."""
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # Documents and runs

    def upsert_document(self, sha256: str, filename: str, page_count: int) -> int:
        """Id of the document with this hash; an identical re-upload reuses the first row and name."""
        with self._connect(write=True) as conn:
            row = conn.execute(
                "INSERT INTO documents (filename, sha256, pages, status, created_at) VALUES (?, ?, ?, 'queued', ?)"
                " ON CONFLICT (sha256) DO UPDATE SET pages = MAX(pages, excluded.pages) RETURNING id",
                (filename, sha256, page_count, _now()),
            ).fetchone()
        return row["id"]

    def get_document(self, document_id: int) -> Document | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return Document(**row) if row else None

    def create_run(self, document_id: int, pipeline_version: str, ai_model: str | None, ai_used: bool) -> int:
        """A new `queued` run; it becomes the latest run and freezes the earlier ones."""
        with self._connect(write=True) as conn:
            run_id = conn.execute(
                "INSERT INTO runs (document_id, pipeline_version, ai_model, ai_used, started_at, status)"
                " VALUES (?, ?, ?, ?, ?, 'queued')",
                (document_id, pipeline_version, ai_model, int(ai_used), _now()),
            ).lastrowid
            conn.execute(
                "UPDATE documents SET status = 'queued', ai_model = ?, pipeline_version = ? WHERE id = ?",
                (ai_model, pipeline_version, document_id),
            )
        return run_id

    def set_run_status(self, run_id: int, status: str, error: str | None = None) -> None:
        if status not in RUN_STATUSES:
            raise ValueError(f"unknown run status {status!r}")
        finished = _now() if status in ("done", "failed") else None
        with self._connect(write=True) as conn:
            updated = conn.execute(
                "UPDATE runs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                (status, error, finished, run_id),
            ).rowcount
            if not updated:
                raise LookupError(f"run {run_id} not found")
            conn.execute(
                "UPDATE documents SET status = ? WHERE id = (SELECT document_id FROM runs WHERE id = ?)"
                " AND ? = (SELECT MAX(id) FROM runs WHERE document_id = documents.id)",
                (status, run_id, run_id),
            )

    def get_run(self, run_id: int) -> Run | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return Run(**row) if row else None

    def latest_run(self, document_id: int) -> Run | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE document_id = ? ORDER BY id DESC LIMIT 1", (document_id,)
            ).fetchone()
        return Run(**row) if row else None

    def list_documents(self) -> list[DocumentSummary]:
        """Newest first, with counts from each document's latest run."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.filename AS name, d.pages, d.created_at,
                       COALESCE(r.status, d.status) AS status, r.error,
                       (SELECT COUNT(*) FROM dates WHERE run_id = r.id) AS n_dates,
                       (SELECT COUNT(*) FROM flags WHERE run_id = r.id) AS n_flags,
                       (SELECT COUNT(*) FROM dates x WHERE x.run_id = r.id AND COALESCE(
                           (SELECT action FROM review_events e WHERE e.date_id = x.id ORDER BY e.id DESC LIMIT 1),
                           'reopen') = 'reopen') AS n_needs_review
                FROM documents d
                LEFT JOIN runs r ON r.id = (SELECT MAX(id) FROM runs WHERE document_id = d.id)
                ORDER BY d.created_at DESC, d.id DESC
                """
            ).fetchall()
        return [DocumentSummary(**row) for row in rows]

    # Pipeline output

    def save_pages(
        self, run_id: int, layouts: list[PageLayout], image_paths: list[Path] | None = None
    ) -> None:
        paths = [str(p) for p in image_paths] if image_paths is not None else [None] * len(layouts)
        with self._connect(write=True) as conn:
            document_id = _document_of_run(conn, run_id)
            conn.executemany(
                "INSERT INTO pages (run_id, document_id, n, image_path, width, height, text, text_source,"
                " words_json, transcription) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        document_id,
                        p.n,
                        path,
                        p.width,
                        p.height,
                        p.text,
                        p.text_source,
                        json.dumps([w.model_dump() for w in p.words]),
                        p.transcription,
                    )
                    for p, path in zip(layouts, paths, strict=True)
                ],
            )

    def pages_for_run(self, run_id: int) -> list[StoredPage]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM pages WHERE run_id = ? ORDER BY n", (run_id,)).fetchall()
        return [
            StoredPage(
                n=r["n"],
                width=r["width"],
                height=r["height"],
                text=r["text"],
                text_source=r["text_source"],
                words=[Word(**w) for w in json.loads(r["words_json"])],
                transcription=r["transcription"],
                image_path=r["image_path"],
            )
            for r in rows
        ]

    def save_results(
        self, run_id: int, dates: list[LabeledDate], flags: list[Flag], discarded: list[dict]
    ) -> None:
        """Store a run's dates, flags (whose candidate ids become date ids) and discarded AI suggestions."""
        with self._connect(write=True) as conn:
            document_id = _document_of_run(conn, run_id)
            ids: dict[str, int] = {}
            for d in dates:
                ids[d.id] = conn.execute(
                    "INSERT INTO dates (run_id, document_id, candidate_id, page, raw_text, normalized,"
                    " candidates_json, precision, date_type, family, qualifier, resolved_value, evidence,"
                    " bbox_json, source, confidence, rationale, context, char_start, char_end, rule_label)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        document_id,
                        d.id,
                        d.page,
                        d.raw_text,
                        d.normalized,
                        json.dumps(d.candidates),
                        d.precision,
                        d.date_type,
                        d.family,
                        d.qualifier,
                        d.resolved_value,
                        d.evidence,
                        d.bbox.model_dump_json() if d.bbox else None,
                        d.source,
                        d.confidence,
                        d.rationale,
                        d.context,
                        d.char_start,
                        d.char_end,
                        d.rule_label,
                    ),
                ).lastrowid
            for f in flags:
                unknown = [i for i in f.date_ids if i not in ids]
                if unknown:
                    raise ValueError(f"flag {f.rule} refers to unknown dates {unknown}")
                conn.execute(
                    "INSERT INTO flags (run_id, document_id, date_ids, rule, severity, message)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        document_id,
                        json.dumps([ids[i] for i in f.date_ids]),
                        f.rule,
                        f.severity,
                        f.message,
                    ),
                )
            conn.executemany(
                "INSERT INTO discarded (run_id, page, payload_json) VALUES (?, ?, ?)",
                [(run_id, item.get("page"), json.dumps(item, ensure_ascii=False)) for item in discarded],
            )

    def dates_for_run(self, run_id: int) -> list[DateWithStatus]:
        """The run's dates in reading order, with status and current type/value from their reviews."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM dates WHERE run_id = ? ORDER BY page, char_start, id", (run_id,)
            ).fetchall()
            events = defaultdict(list)
            for e in conn.execute(
                "SELECT e.* FROM review_events e JOIN dates d ON d.id = e.date_id WHERE d.run_id = ?"
                " ORDER BY e.id",
                (run_id,),
            ):
                events[e["date_id"]].append(e)
        return [_date_with_status(row, events[row["id"]]) for row in rows]

    def flags_for_run(self, run_id: int) -> list[StoredFlag]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM flags WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [
            StoredFlag(
                id=r["id"],
                rule=r["rule"],
                severity=r["severity"],
                message=r["message"],
                date_ids=json.loads(r["date_ids"]),
            )
            for r in rows
        ]

    def discarded_for_run(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM discarded WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    # Reviews

    def add_review(
        self,
        date_id: int,
        action: str,
        reviewer: str,
        reason: str,
        new_type: str | None = None,
        new_value: str | None = None,
    ) -> ReviewEvent:
        """Append a reviewer decision. `ValueError` for invalid input, `LookupError` for an unknown
        date, `FrozenRunError` if the date's run is not its document's latest run; nothing is written
        in any of those cases."""
        reviewer, reason = (reviewer or "").strip(), (reason or "").strip()
        if action not in ACTIONS:
            raise ValueError(f"unknown review action {action!r}")
        if not reviewer:
            raise ValueError("a reviewer name is required")
        if not reason:
            raise ValueError("a reason is required")
        if action == "correct":
            if new_type is None and new_value is None:
                raise ValueError("a correction needs a new type or a new value")
        elif new_type is not None or new_value is not None:
            raise ValueError("only a correction can change the type or value")
        if new_type is not None and new_type not in ALL_TYPES:
            raise ValueError(f"date type {new_type!r} is not in the taxonomy")
        if new_value is not None and not _valid_value(new_value):
            raise ValueError("a value must be a date written YYYY-MM-DD, or YYYY-MM for month precision")

        with self._connect(write=True) as conn:
            row = conn.execute(
                "SELECT d.run_id, (SELECT MAX(id) FROM runs WHERE document_id = d.document_id) AS latest"
                " FROM dates d WHERE d.id = ?",
                (date_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"date {date_id} not found")
            if row["run_id"] != row["latest"]:
                raise FrozenRunError(
                    f"run {row['run_id']} is frozen; review the document's latest run {row['latest']}"
                )
            return _insert_event(conn, date_id, action, new_type, new_value, reviewer, reason, None)

    def history(self, date_id: int) -> list[ReviewEvent]:
        """Every review event of a date, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM review_events WHERE date_id = ? ORDER BY id", (date_id,)
            ).fetchall()
        return [ReviewEvent(**r) for r in rows]

    def carry_over(self, old_run_id: int, new_run_id: int) -> int:
        """Copy reviewer decisions to the new run's dates that match an old date exactly (page, raw text
        and normalized value). Repeated identical dates pair up in reading order. Returns the number of
        decisions carried; dates without a match, or whose last event is a reopen, stay `needs_review`."""
        old = self.dates_for_run(old_run_id)
        new = self.dates_for_run(new_run_id)
        if old and new and old[0].document_id != new[0].document_id:
            raise ValueError("runs belong to different documents")
        by_key: dict[tuple, list[DateWithStatus]] = defaultdict(list)
        for d in old:
            by_key[(d.page, d.raw_text, d.normalized)].append(d)
        with self._connect(write=True) as conn:
            last_events = {
                r["date_id"]: r
                for r in conn.execute(
                    "SELECT e.* FROM review_events e JOIN dates d ON d.id = e.date_id WHERE d.run_id = ?"
                    " ORDER BY e.id",
                    (old_run_id,),
                )
            }
            carried = 0
            for d in new:
                matches = by_key.get((d.page, d.raw_text, d.normalized))
                if not matches:
                    continue
                source = matches.pop(0)
                last = last_events.get(source.id)
                if last is None or last["action"] == "reopen":
                    continue
                _insert_event(
                    conn,
                    d.id,
                    last["action"],
                    source.current_type if source.current_type != d.date_type else None,
                    source.current_value if source.current_value != _value_of(d) else None,
                    last["reviewer"],
                    f"carried over from run {old_run_id}",
                    old_run_id,
                )
                carried += 1
        return carried


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _document_of_run(conn: sqlite3.Connection, run_id: int) -> int:
    row = conn.execute("SELECT document_id FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise LookupError(f"run {run_id} not found")
    return row["document_id"]


def _valid_value(value: str) -> bool:
    if not _VALUE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value if len(value) == 10 else f"{value}-01")
    except ValueError:
        return False
    return True


def _value_of(d: LabeledDate) -> str | None:
    return d.normalized or d.resolved_value


def _insert_event(
    conn, date_id, action, new_type, new_value, reviewer, reason, carried_from_run
) -> ReviewEvent:
    row = conn.execute(
        "INSERT INTO review_events (date_id, action, new_type, new_value, reviewer, reason, at, carried_from_run)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
        (date_id, action, new_type, new_value, reviewer, reason, _now(), carried_from_run),
    ).fetchone()
    return ReviewEvent(**row)


def _date_with_status(row: sqlite3.Row, events: list[sqlite3.Row]) -> DateWithStatus:
    labeled = LabeledDate(
        id=row["candidate_id"],
        page=row["page"],
        raw_text=row["raw_text"],
        normalized=row["normalized"],
        candidates=json.loads(row["candidates_json"]),
        precision=row["precision"],
        char_start=row["char_start"],
        char_end=row["char_end"],
        bbox=BBox.model_validate_json(row["bbox_json"]) if row["bbox_json"] else None,
        context=row["context"],
        rule_label=row["rule_label"],
        source=row["source"],
        date_type=row["date_type"],
        family=row["family"],
        qualifier=row["qualifier"],
        resolved_value=row["resolved_value"],
        evidence=row["evidence"],
        confidence=row["confidence"],
        rationale=row["rationale"],
    )
    current_type, current_value = labeled.date_type, _value_of(labeled)
    for e in events:  # corrections stay in effect through later accepts and reopens
        current_type = e["new_type"] or current_type
        current_value = e["new_value"] or current_value
    last = events[-1] if events else None
    return DateWithStatus(
        **(labeled.model_dump() | {"id": row["id"]}),
        candidate_id=row["candidate_id"],
        run_id=row["run_id"],
        document_id=row["document_id"],
        status=_STATUS_OF[last["action"] if last else None],
        current_type=current_type,
        current_family=family_of(current_type),
        current_value=current_value,
        carried_from_run=last["carried_from_run"] if last else None,
    )
