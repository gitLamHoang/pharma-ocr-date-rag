"""One run of the pipeline over a document, and the background queue that runs documents.

A run moves `queued -> reading -> classifying -> validating -> done`, or to `failed` with a message
that is safe to show: the ingest message for a file that cannot be read, "Processing error" for
anything else (the details go to the server log, without document text).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from .candidates import apply_document_order, page_candidates, transcription_candidates
from .classify import ClaudeUnavailable, label_page
from .config import Settings
from .ingest import IngestError, ingest, sha256_of
from .layout import layout_page
from .models import Candidate, LabeledDate, PageLayout
from .store import Store
from .validate import validate

if TYPE_CHECKING:
    from .claude_client import ClaudeClient

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.0.0"
MAX_PARALLEL_DOCUMENTS = 2
PROCESSING_ERROR = "Processing error"

# PDFium is not thread-safe, and two documents can be ingested at once.
_PDFIUM_LOCK = threading.Lock()


def run_document(
    path: Path,
    filename: str,
    store: Store,
    settings: Settings,
    client: ClaudeClient | None,
    *,
    run_id: int | None = None,
    carry_from: int | None = None,
) -> int:
    """Process one file and return its run id; the run ends `done` or `failed` (a file that
    cannot be processed fails the run, it does not raise). Without `run_id` the file is hashed
    and a new run created for its document (`OSError` if it cannot be opened). With `carry_from`,
    reviewer decisions from that earlier run are carried over before the run is marked `done`."""
    path = Path(path)
    if run_id is None:
        run_id = _new_run(store, store.upsert_document(sha256_of(path), filename, 0), client)
    try:
        _process(run_id, path, filename, store, settings, client, carry_from)
    except IngestError as exc:
        store.set_run_status(run_id, "failed", str(exc))
    except Exception as exc:
        # Type and stack only: exception messages can quote document text.
        stack = "".join(traceback.format_tb(exc.__traceback__))
        logger.error("run %d failed: %s\n%s", run_id, type(exc).__name__, stack)
        store.set_run_status(run_id, "failed", PROCESSING_ERROR)
    return run_id


def _process(
    run_id: int,
    path: Path,
    filename: str,
    store: Store,
    settings: Settings,
    client: ClaudeClient | None,
    carry_from: int | None,
) -> None:
    store.set_run_status(run_id, "reading")
    with _PDFIUM_LOCK:
        ingested = ingest(path, settings)
    store.upsert_document(ingested.sha256, filename, ingested.page_count)  # records the page count
    images = ingested.page_images
    layouts = [layout_page(ingested, n, settings) for n in range(1, ingested.page_count + 1)]
    if client is not None:
        layouts = asyncio.run(_transcribe_scans(layouts, images, client, settings.ai_concurrency))
    cands = []
    for layout in layouts:
        rules = page_candidates(layout)
        cands.append(rules + transcription_candidates(layout, rules))

    store.set_run_status(run_id, "classifying")
    labeled = asyncio.run(_label_pages(layouts, cands, images, client, settings.ai_concurrency))
    dates = apply_document_order([d for page_dates, _ in labeled for d in page_dates])
    discarded = [item for _, page_discarded in labeled for item in page_discarded]

    store.set_run_status(run_id, "validating")
    flags = validate(dates, date.today())
    store.save_pages(run_id, layouts, images)
    store.save_results(run_id, dates, flags, discarded)
    if carry_from is not None:
        carried = store.carry_over(carry_from, run_id)
        logger.info("run %d: %d decisions carried over from run %d", run_id, carried, carry_from)
    store.set_run_status(run_id, "done")
    logger.info("run %d: %d pages, %d dates, %d flags", run_id, len(layouts), len(dates), len(flags))


async def _transcribe_scans(
    layouts: list[PageLayout], images: list[Path], client: ClaudeClient, limit: int
) -> list[PageLayout]:
    """Claude's transcription on every OCR page; a page whose transcription fails keeps none."""
    semaphore = asyncio.Semaphore(limit)

    async def one(layout: PageLayout, image: Path) -> PageLayout:
        if layout.text_source != "ocr":
            return layout
        async with semaphore:
            text = await asyncio.to_thread(_transcribe, client, image, layout.n)
        return layout.model_copy(update={"transcription": text})

    return list(await asyncio.gather(*(one(layout, image) for layout, image in zip(layouts, images))))


def _transcribe(client: ClaudeClient, image: Path, n: int) -> str | None:
    try:
        return client.transcribe(image.read_bytes()) or None
    except ClaudeUnavailable as exc:
        logger.warning("page %d: transcription unavailable (%s)", n, type(exc).__name__)
        return None


async def _label_pages(
    layouts: list[PageLayout],
    cands: list[list[Candidate]],
    images: list[Path],
    client: ClaudeClient | None,
    limit: int,
) -> list[tuple[list[LabeledDate], list[dict]]]:
    semaphore = asyncio.Semaphore(limit)

    async def one(layout: PageLayout, page_cands: list[Candidate], image: Path):
        async with semaphore:
            return await asyncio.to_thread(_label, layout, page_cands, client, image)

    return list(await asyncio.gather(*(one(*page) for page in zip(layouts, cands, images))))


def _label(layout: PageLayout, cands: list[Candidate], client: ClaudeClient | None, image: Path):
    return label_page(layout, cands, client, image.read_bytes() if client is not None else None)


def _new_run(store: Store, document_id: int, client: ClaudeClient | None) -> int:
    model = client.model if client is not None else None
    return store.create_run(document_id, PIPELINE_VERSION, model, client is not None)


class JobQueue:
    """Runs documents in background threads, at most `MAX_PARALLEL_DOCUMENTS` at once."""

    def __init__(self, store: Store, settings: Settings, client: ClaudeClient | None):
        self.store, self.settings, self.client = store, settings, client
        self._pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL_DOCUMENTS, thread_name_prefix="pipeline")
        self._lock = threading.Lock()
        self._jobs: dict[int, Future] = {}  # run id -> unfinished job

    def submit(self, path: Path, filename: str) -> tuple[int, int]:
        """Queue an uploaded file; returns (document id, run id) at once. The file must stay in
        place until the run has read it. An identical file whose latest run is done or still
        running here returns that run; otherwise (failed, or left unfinished by a restart) a
        new run starts."""
        sha256 = sha256_of(Path(path))
        with self._lock:
            document_id = self.store.upsert_document(sha256, filename, 0)
            latest = self.store.latest_run(document_id)
            if latest is not None and (latest.status == "done" or latest.id in self._jobs):
                return document_id, latest.id
            run_id = _new_run(self.store, document_id, self.client)
            self._start(run_id, Path(path), filename, None)
        return document_id, run_id

    def reprocess(self, document_id: int) -> int:
        """A new run over the stored upload, carrying reviewer decisions over from the newest run
        that finished `done` (a failed run has no dates, so it would carry nothing). Returns the
        latest run instead while that run is still running here. `LookupError` for an unknown
        document."""
        document = self.store.get_document(document_id)
        if document is None:
            raise LookupError(f"document {document_id} not found")
        folder = self.settings.data_dir / "uploads" / document.sha256
        # A file rejected at ingest was never stored; its run then fails as unreadable.
        source = next(iter(sorted(folder.glob("original.*"))), folder / "original")
        with self._lock:
            latest = self.store.latest_run(document_id)
            if latest is not None and latest.id in self._jobs:
                return latest.id
            carry_from = self.store.latest_done_run(document_id)
            run_id = _new_run(self.store, document_id, self.client)
            self._start(run_id, source, document.filename, carry_from.id if carry_from else None)
        return run_id

    def wait(self) -> None:
        """Block until every queued run has finished."""
        with self._lock:
            jobs = list(self._jobs.values())
        wait_for(jobs)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)

    def _start(self, run_id: int, path: Path, filename: str, carry_from: int | None) -> None:
        job = self._pool.submit(self._run, run_id, path, filename, carry_from)
        self._jobs[run_id] = job
        job.add_done_callback(lambda _: self._jobs.pop(run_id, None))

    def _run(self, run_id: int, path: Path, filename: str, carry_from: int | None) -> None:
        try:
            run_document(
                path, filename, self.store, self.settings, self.client, run_id=run_id, carry_from=carry_from
            )
        except Exception as exc:  # e.g. the database was unreachable while marking the run failed
            logger.error("run %d: job stopped (%s)", run_id, type(exc).__name__)
