"""HTTP API: upload, processing status, results, reviews and export; serves the built frontend at `/`.

Run with `uvicorn --factory pharma_dates.api:create_app`. Every error body is `{"detail": message}`.
"""

import csv
import hashlib
import io
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

import pytesseract
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from . import taxonomy
from .claude_client import ClaudeClient, make_client
from .config import Settings, get_settings
from .ingest import UNSUPPORTED, file_kind
from .pipeline import JobQueue
from .store import Document, FrozenRunError, Run, Store

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
DB_FILE = "store.sqlite"
_CHUNK = 1 << 20
_FORM_OVERHEAD = 64 * 1024  # multipart boundaries and headers around the file
_FROM_SETTINGS = object()
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# A database id: SQLite integers are 64-bit, so a larger path id is refused (422), not a crash.
Id = Annotated[int, PathParam(ge=1, le=2**63 - 1)]
CROSS_SITE = "Cross-site requests are not allowed."

CSV_COLUMNS = [
    "document",
    "run_id",
    "date_id",
    "page",
    "raw_text",
    "status",
    "current_type",
    "current_family",
    "current_value",
    "date_type",
    "normalized",
    "candidates",
    "precision",
    "qualifier",
    "resolved_value",
    "evidence",
    "source",
    "confidence",
    "flags",
    "carried_from_run",
    "last_action",
    "last_reviewer",
    "last_reason",
    "last_reviewed_at",
    "context",
]


class ReviewIn(BaseModel):
    action: str
    reviewer: str
    reason: str
    new_type: str | None = None
    new_value: str | None = None


def create_app(
    settings: Settings | None = None,
    *,
    client: ClaudeClient | None | object = _FROM_SETTINGS,
    frontend_dist: Path | None = FRONTEND_DIST,
) -> FastAPI:
    """The app with its store and job queue. `client` defaults to the one the settings configure
    (None when AI is off or no credentials are set)."""
    settings = settings or get_settings()
    if client is _FROM_SETTINGS:
        client = make_client(settings)
    store = Store(settings.data_dir / DB_FILE)
    queue = JobQueue(store, settings, client)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        queue.shutdown()

    app = FastAPI(title="Pharma dates", lifespan=lifespan)
    app.state.store, app.state.queue = store, queue

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "Internal error."})  # logged by the server

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{e['loc'][-1]}: {e['msg']}" if e["loc"] else e["msg"] for e in exc.errors())
        return JSONResponse(status_code=422, content={"detail": detail})

    def get_run(run_id: int) -> Run:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, f"Run {run_id} not found.")
        return run

    def get_document(document_id: int) -> Document:
        document = store.get_document(document_id)
        if document is None:
            raise HTTPException(404, f"Document {document_id} not found.")
        return document

    @app.get("/api/health")
    def health():
        return {
            "ai_enabled": client is not None,
            "provider": settings.claude_provider,
            "model": client.model if client is not None else None,
            "tesseract_langs_missing": _missing_langs(settings.tesseract_langs),
        }

    @app.get("/api/taxonomy")
    def get_taxonomy():
        return taxonomy.as_json()

    @app.post("/api/documents", status_code=202, dependencies=[Depends(_same_origin)])
    async def upload(request: Request):
        limit = settings.max_upload_mb * 1024 * 1024
        too_large = HTTPException(413, f"This file is larger than {settings.max_upload_mb} MB.")
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > limit + _FORM_OVERHEAD:
            raise too_large
        async with _capped(request, limit + _FORM_OVERHEAD, too_large).form(
            max_files=1, max_fields=10
        ) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise HTTPException(422, "file: send the document as the multipart field 'file'")
            path = await _save_upload(file, settings.data_dir, limit, too_large)
            filename = _display_name(file.filename)
        document_id, run_id = await run_in_threadpool(queue.submit, path, filename)
        return {"document_id": document_id, "run_id": run_id, "status": store.get_run(run_id).status}

    @app.get("/api/documents")
    def list_documents():
        return store.list_documents()

    @app.get("/api/documents/{document_id}")
    def document_detail(document_id: Id):
        document = get_document(document_id)
        run = store.latest_run(document_id)
        pages = store.pages_for_run(run.id) if run else []
        summary = run.model_dump(include={"id", "status", "error", "ai_used", "ai_model"}) if run else None
        return {
            "document": document,
            "run": summary,
            "pages": [{"n": p.n, "width": p.width, "height": p.height} for p in pages],
        }

    @app.get("/api/documents/{document_id}/pages/{n}.png")
    def page_image(document_id: Id, n: Id):
        get_document(document_id)
        run = store.latest_run(document_id)
        page = next((p for p in store.pages_for_run(run.id) if p.n == n), None) if run else None
        if page is None or not page.image_path or not Path(page.image_path).is_file():
            raise HTTPException(404, f"Page {n} not found.")
        return FileResponse(page.image_path, media_type="image/png")

    @app.post("/api/documents/{document_id}/reprocess", status_code=202, dependencies=[Depends(_same_origin)])
    def reprocess(document_id: Id):
        try:
            return {"run_id": queue.reprocess(document_id)}
        except LookupError:
            raise HTTPException(404, f"Document {document_id} not found.") from None

    @app.get("/api/runs/{run_id}/dates")
    def run_dates(run_id: Id):
        get_run(run_id)
        return store.dates_for_run(run_id)

    @app.get("/api/runs/{run_id}/flags")
    def run_flags(run_id: Id):
        get_run(run_id)
        return store.flags_for_run(run_id)

    @app.get("/api/runs/{run_id}/discarded")
    def run_discarded(run_id: Id):
        get_run(run_id)
        return store.discarded_for_run(run_id)

    @app.post("/api/dates/{date_id}/review", status_code=201, dependencies=[Depends(_same_origin)])
    def review(date_id: Id, body: ReviewIn):
        try:
            return store.add_review(date_id, **body.model_dump())
        except FrozenRunError as exc:
            raise HTTPException(409, str(exc)) from None
        except LookupError:
            raise HTTPException(404, f"Date {date_id} not found.") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/dates/{date_id}/history")
    def history(date_id: Id):
        return store.history(date_id)

    @app.get("/api/runs/{run_id}/export")
    def export(run_id: Id, format: Literal["csv", "json"] = Query()):
        run = get_run(run_id)
        document = store.get_document(run.document_id)
        dates = store.dates_for_run(run_id)
        flags = store.flags_for_run(run_id)
        histories = {d.id: store.history(d.id) for d in dates}
        stem = _UNSAFE_NAME.sub("_", Path(document.filename).stem).strip("._") or "document"
        headers = {"Content-Disposition": f'attachment; filename="{stem}-run-{run_id}.{format}"'}
        if format == "json":
            body = {
                "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "document": document.model_dump(mode="json"),
                "run": run.model_dump(mode="json"),
                "dates": [
                    d.model_dump(mode="json")
                    | {"history": [e.model_dump(mode="json") for e in histories[d.id]]}
                    for d in dates
                ],
                "flags": [f.model_dump(mode="json") for f in flags],
            }
            content = json.dumps(body, ensure_ascii=False, indent=2)
            return Response(content, media_type="application/json", headers=headers)

        flag_rules: dict[int, list[str]] = {}
        for f in flags:
            for date_id in f.date_ids:
                flag_rules.setdefault(date_id, []).append(f.rule)
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(CSV_COLUMNS)
        for d in dates:
            last = histories[d.id][-1] if histories[d.id] else None
            row = {
                "document": document.filename,
                "run_id": run_id,
                "date_id": d.id,
                "page": d.page,
                "raw_text": d.raw_text,
                "status": d.status,
                "current_type": d.current_type,
                "current_family": d.current_family,
                "current_value": d.current_value,
                "date_type": d.date_type,
                "normalized": d.normalized,
                "candidates": " | ".join(d.candidates),
                "precision": d.precision,
                "qualifier": d.qualifier,
                "resolved_value": d.resolved_value,
                "evidence": d.evidence,
                "source": d.source,
                "confidence": d.confidence,
                "flags": " | ".join(flag_rules.get(d.id, [])),
                "carried_from_run": d.carried_from_run,
                "last_action": last and last.action,
                "last_reviewer": last and last.reviewer,
                "last_reason": last and last.reason,
                "last_reviewed_at": last and last.at.isoformat(),
                "context": d.context,
            }
            writer.writerow([csv_cell(row[c]) for c in CSV_COLUMNS])
        # A byte-order mark so spreadsheet programs read the file as UTF-8.
        return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)

    if frontend_dist is not None and (frontend_dist / "index.html").is_file():
        dist = frontend_dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "Not Found")
            target = (dist / path).resolve()
            if path and target.is_relative_to(dist) and target.is_file():
                return FileResponse(target)
            return FileResponse(dist / "index.html")  # client-side routes such as /documents/3

    return app


def csv_cell(value: object) -> str:
    """A CSV cell that a spreadsheet will not run as a formula (leading = + - @ tab or CR get a `'`)."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def _missing_langs(langs: str) -> list[str]:
    """Configured Tesseract packs that are not installed (all of them if Tesseract is missing)."""
    wanted = [lang for lang in langs.split("+") if lang]
    try:
        installed = set(pytesseract.get_languages(config=""))
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, OSError):
        installed = set()
    return [lang for lang in wanted if lang not in installed]


def _same_origin(request: Request) -> None:
    """Refuse a state-changing request a page on another site made the browser send.

    An upload or a reprocess is a CORS-simple request, so a page elsewhere could otherwise start
    paid AI runs or freeze the run a reviewer is working in. Browsers say where a request came
    from (`Sec-Fetch-Site`, `Origin`); clients that send neither (curl, scripts) are let through."""
    if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
        raise HTTPException(403, CROSS_SITE)
    origin = request.headers.get("origin")
    if origin is None:
        return
    hosts = {request.headers.get("host"), request.headers.get("x-forwarded-host")} - {None}
    if urlsplit(origin).netloc not in hosts:
        raise HTTPException(403, CROSS_SITE)


def _capped(request: Request, cap: int, too_large: HTTPException) -> Request:
    """The request with its body counted as it arrives: past `cap` bytes, `too_large` is raised.

    A chunked upload has no Content-Length to check first, and the form parser would otherwise
    spool the whole file part to a temporary file before `_save_upload` sees it."""
    received = 0

    async def receive():
        nonlocal received
        message = await request.receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > cap:
                raise too_large
        return message

    return Request(request.scope, receive)


def _display_name(filename: str | None) -> str:
    """The uploaded file's base name without control characters, as shown in the documents list."""
    name = _CONTROL.sub("", Path((filename or "").replace("\\", "/")).name).strip()
    return name[:200] or "document"


async def _save_upload(file: UploadFile, data_dir: Path, limit: int, too_large: HTTPException) -> Path:
    """Stream the upload to `<data_dir>/uploads/<sha256>/original<suffix>` (where ingest keeps it),
    checking its type from the first bytes and its size; nothing is kept on refusal. The request
    body is already capped as it arrives (`_capped`)."""
    incoming = data_dir / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    temp = incoming / uuid.uuid4().hex
    digest, size, suffix = hashlib.sha256(), 0, None
    try:
        with temp.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                if suffix is None:
                    kind = file_kind(chunk[:16])
                    if kind is None:
                        raise HTTPException(415, UNSUPPORTED)
                    suffix = kind[1]
                size += len(chunk)
                if size > limit:
                    raise too_large
                digest.update(chunk)
                out.write(chunk)
        if suffix is None:
            raise HTTPException(415, UNSUPPORTED)  # an empty file
        target = data_dir / "uploads" / digest.hexdigest() / f"original{suffix}"
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp, target)
        return target
    finally:
        temp.unlink(missing_ok=True)
