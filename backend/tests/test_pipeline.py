import logging
import shutil
import threading
import time
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from pharma_dates import pipeline
from pharma_dates.classify import CandidateLabel, ClaudeUnavailable, PageClassification
from pharma_dates.pipeline import PIPELINE_VERSION, JobQueue, run_document
from pharma_dates.store import Store
from pharma_dates.taxonomy import family_of

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")


class FakeClient:
    """Stands in for ClaudeClient: labels every candidate as an expiry date, counts calls."""

    model = "fake-model"

    def __init__(self, transcription="", delay=0.0, transcribe_error=None):
        self.transcription, self.delay, self.transcribe_error = transcription, delay, transcribe_error
        self.classified_pages, self.transcribed = [], 0
        self.running = self.max_running = 0
        self._lock = threading.Lock()

    def transcribe(self, image_png):
        assert image_png.startswith(b"\x89PNG")
        self.transcribed += 1
        if self.transcribe_error is not None:
            raise self.transcribe_error
        return self.transcription

    def classify(self, image_png, page_text, candidates, taxonomy_json):
        assert image_png.startswith(b"\x89PNG")
        with self._lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
            self.classified_pages.append(page_text)
        time.sleep(self.delay)
        with self._lock:
            self.running -= 1
        return PageClassification(
            items=[
                CandidateLabel(
                    candidate_id=c.id, date_type="expiry_date", confidence=0.95, rationale="after 'Expiry'"
                )
                for c in candidates
            ]
        )


class SpyStore(Store):
    def __init__(self, path):
        super().__init__(path)
        self.statuses = []

    def set_run_status(self, run_id, status, error=None):
        self.statuses.append(status)
        super().set_run_status(run_id, status, error)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "db.sqlite")


@pytest.fixture
def zero_page_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "zero.pdf"
    pdfium.PdfDocument.new().save(str(path))
    return path


def test_native_pdf_end_to_end(native_pdf, store, settings):
    client = FakeClient()
    run_id = run_document(native_pdf, "native.pdf", store, settings, client)

    run = store.get_run(run_id)
    assert run.status == "done" and run.error is None and run.finished_at is not None
    assert run.ai_used is True and run.ai_model == "fake-model"
    assert run.pipeline_version == PIPELINE_VERSION == "1.0.0"
    document = store.get_document(run.document_id)
    assert document.status == "done" and document.pages == 1 and document.filename == "native.pdf"

    dates = store.dates_for_run(run_id)
    assert len(dates) >= 1
    expiry = dates[0]
    assert expiry.raw_text == "31/03/2027" and expiry.normalized == "2027-03-31"
    assert expiry.bbox is not None and expiry.bbox.x1 > expiry.bbox.x0
    assert expiry.date_type == "expiry_date" and expiry.family == family_of("expiry_date")
    assert expiry.source == "rules+ai" and expiry.status == "needs_review"

    pages = store.pages_for_run(run_id)
    assert [p.n for p in pages] == [1] and Path(pages[0].image_path).is_file()
    assert client.transcribed == 0  # native text layer: no transcription
    assert len(client.classified_pages) == 1


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("corrupt_pdf", "damaged or incomplete"),
        ("encrypted_pdf", "password-protected"),
        ("zero_page_pdf", "no readable pages"),
    ],
)
def test_corrupt_pdf_marks_failed(request, fixture, message, store, settings):
    path = request.getfixturevalue(fixture)
    run_id = run_document(path, path.name, store, settings, FakeClient())

    run = store.get_run(run_id)
    assert run.status == "failed" and message in run.error and run.finished_at is not None
    assert store.get_document(run.document_id).status == "failed"
    assert store.dates_for_run(run_id) == []
    assert [d.status for d in store.list_documents()] == ["failed"]


def test_unexpected_error_marks_failed_without_details(native_pdf, store, settings, monkeypatch, caplog):
    def broken(dates, today):
        raise RuntimeError(f"cannot compare {dates[0].context}")  # a message quoting the page

    monkeypatch.setattr(pipeline, "validate", broken)
    with caplog.at_level(logging.DEBUG, logger="pharma_dates"):
        run_id = run_document(native_pdf, "native.pdf", store, settings, FakeClient())

    run = store.get_run(run_id)
    assert run.status == "failed" and run.error == "Processing error"
    logged = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("pharma_dates"))
    assert "RuntimeError" in logged and "validate" in logged
    assert "31/03/2027" not in logged and "Expiry" not in logged


def test_offline_run_marks_ai_used_false(native_pdf, store, settings):
    run_id = run_document(native_pdf, "native.pdf", store, settings, None)

    run = store.get_run(run_id)
    assert run.status == "done" and run.ai_used is False and run.ai_model is None
    dates = store.dates_for_run(run_id)
    assert [(d.raw_text, d.source, d.confidence) for d in dates] == [("31/03/2027", "rules", 0.5)]
    assert dates[0].date_type == "expiry_date"  # offline rule label


def test_status_progression(native_pdf, tmp_path, settings):
    store = SpyStore(tmp_path / "spy.sqlite")
    run_id = run_document(native_pdf, "native.pdf", store, settings, FakeClient())

    assert store.statuses == ["reading", "classifying", "validating", "done"]
    assert store.get_run(run_id).status == "done"


def test_status_progression_stops_at_failure(corrupt_pdf, tmp_path, settings):
    store = SpyStore(tmp_path / "spy.sqlite")
    run_document(corrupt_pdf, "corrupt.pdf", store, settings, FakeClient())

    assert store.statuses == ["reading", "failed"]


def test_pages_are_classified_with_bounded_concurrency(tmp_path, make_pdf, store, settings):
    path = make_pdf(tmp_path / "six.pdf", [f"Expiry date: 0{i}/03/2027 page {i}" for i in range(1, 7)])
    client = FakeClient(delay=0.05)
    limited = settings.model_copy(update={"ai_concurrency": 2})

    run_id = run_document(path, "six.pdf", store, limited, client)

    assert store.get_run(run_id).status == "done"
    assert len(client.classified_pages) == 6
    assert 1 < client.max_running <= 2
    assert [d.page for d in store.dates_for_run(run_id)] == [1, 2, 3, 4, 5, 6]


def test_document_order_resolves_ambiguous_dates(tmp_path, make_pdf, store, settings):
    # 25/12/2026 can only be day-first, so 03/04/2026 elsewhere in the document reads as 3 April.
    path = make_pdf(tmp_path / "order.pdf", ["Signed on 25/12/2026", "Effective date 03/04/2026"])
    run_id = run_document(path, "order.pdf", store, settings, None)

    ambiguous = next(d for d in store.dates_for_run(run_id) if d.raw_text == "03/04/2026")
    assert ambiguous.normalized is None and ambiguous.resolved_value == "2026-04-03"
    assert "25/12/2026" in ambiguous.evidence


@needs_tesseract
def test_ocr_page_is_transcribed(scanned_png, store, settings):
    client = FakeClient(transcription="Expiry date: 31/03/2027")
    run_id = run_document(scanned_png, "scan.png", store, settings, client)

    assert store.get_run(run_id).status == "done"
    assert client.transcribed == 1
    page = store.pages_for_run(run_id)[0]
    assert page.text_source == "ocr" and page.transcription == "Expiry date: 31/03/2027"


@needs_tesseract
def test_transcription_failure_keeps_the_run_going(scanned_png, store, settings):
    client = FakeClient(transcribe_error=ClaudeUnavailable("Claude API error (APIConnectionError)"))
    run_id = run_document(scanned_png, "scan.png", store, settings, client)

    assert store.get_run(run_id).status == "done"
    assert store.pages_for_run(run_id)[0].transcription is None


def test_job_queue_runs_in_background_and_reuses_identical_upload(native_pdf, tmp_path, store, settings):
    queue = JobQueue(store, settings, FakeClient())
    try:
        document_id, run_id = queue.submit(native_pdf, "native.pdf")
        assert store.get_run(run_id).document_id == document_id
        queue.wait()
        assert store.get_run(run_id).status == "done"

        copy = tmp_path / "copy.pdf"
        shutil.copyfile(native_pdf, copy)
        assert queue.submit(copy, "copy.pdf") == (document_id, run_id)
    finally:
        queue.shutdown()


def test_job_queue_retries_identical_upload_after_failure(corrupt_pdf, store, settings):
    queue = JobQueue(store, settings, None)
    try:
        document_id, first = queue.submit(corrupt_pdf, "corrupt.pdf")
        queue.wait()
        assert store.get_run(first).status == "failed"
        again = queue.submit(corrupt_pdf, "corrupt.pdf")
        assert again[0] == document_id and again[1] != first
        queue.wait()
    finally:
        queue.shutdown()


def test_job_queue_runs_at_most_two_documents_at_once(tmp_path, make_pdf, store, settings):
    client = FakeClient(delay=0.1)
    queue = JobQueue(store, settings, client)
    try:
        runs = [
            queue.submit(make_pdf(tmp_path / f"d{i}.pdf", [f"Expiry date: 0{i}/03/2027"]), f"d{i}.pdf")[1]
            for i in range(1, 5)
        ]
        queue.wait()
    finally:
        queue.shutdown()
    assert [store.get_run(r).status for r in runs] == ["done"] * 4
    assert 1 < client.max_running <= 2


def test_reprocess_carries_decisions(native_pdf, store, settings):
    queue = JobQueue(store, settings, None)
    try:
        document_id, first = queue.submit(native_pdf, "native.pdf")
        queue.wait()
        old_date = store.dates_for_run(first)[0]
        store.add_review(old_date.id, "accept", "QA Reviewer", "matches the label")

        second = queue.reprocess(document_id)
        assert second != first
        queue.wait()
    finally:
        queue.shutdown()

    run = store.get_run(second)
    assert run.status == "done" and run.document_id == document_id
    assert store.latest_run(document_id).id == second
    (new_date,) = store.dates_for_run(second)
    assert new_date.raw_text == old_date.raw_text
    assert new_date.status == "accepted" and new_date.carried_from_run == first
    assert store.history(new_date.id)[0].reason == f"carried over from run {first}"


def test_reprocess_unknown_document_raises(store, settings):
    queue = JobQueue(store, settings, None)
    try:
        with pytest.raises(LookupError):
            queue.reprocess(999)
    finally:
        queue.shutdown()
