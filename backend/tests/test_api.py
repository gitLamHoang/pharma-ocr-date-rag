import csv
import io
import json
from pathlib import Path

import httpx
import pytesseract
import pytest

from pharma_dates import api, taxonomy
from pharma_dates.api import create_app
from pharma_dates.classify import CandidateLabel, MissedDate, PageClassification
from pharma_dates.config import Settings

FAKE_KEY = "sk-ant-api03-test-only-not-a-real-key-0000"  # pragma: allowlist secret


class FakeClient:
    """Stands in for ClaudeClient: every candidate is an expiry date, plus one invented date."""

    model = "fake-model"

    def transcribe(self, image_png):
        return ""

    def classify(self, image_png, page_text, candidates, taxonomy_json):
        return PageClassification(
            items=[
                CandidateLabel(candidate_id=c.id, date_type="expiry_date", confidence=0.9, rationale="label")
                for c in candidates
            ],
            missed_dates=[
                MissedDate(verbatim_text="01/01/2030", date_type="issue_date", confidence=0.5, rationale="x")
            ],
        )


@pytest.fixture
def make_app(tmp_path):
    apps = []

    def make(client=None, dist=None, **overrides):
        settings = Settings(data_dir=tmp_path / "data", ai_enabled=client is not None, **overrides)
        app = create_app(settings, client=client, frontend_dist=dist or tmp_path / "no-dist")
        apps.append(app)
        return app

    yield make
    for app in apps:
        app.state.queue.shutdown()


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
async def http(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def upload(http, app, path: Path, name: str | None = None) -> dict:
    response = await http.post(
        "/api/documents", files={"file": (name or path.name, path.read_bytes(), "application/pdf")}
    )
    assert response.status_code == 202, response.text
    app.state.queue.wait()
    return response.json()


def stored_files(data_dir: Path) -> list[Path]:
    """Files kept on disk besides the database."""
    return [p for p in data_dir.rglob("*") if p.is_file() and not p.name.startswith("store.sqlite")]


async def first_date(http, run_id: int) -> dict:
    dates = (await http.get(f"/api/runs/{run_id}/dates")).json()
    assert dates
    return dates[0]


async def review(http, date_id: int, **body) -> httpx.Response:
    return await http.post(
        f"/api/dates/{date_id}/review", json={"reviewer": "QA One", "reason": "checked"} | body
    )


# Health and taxonomy


async def test_health_offline(http, monkeypatch):
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["eng", "osd"])
    response = await http.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "ai_enabled": False,
        "provider": "anthropic",
        "model": None,
        "tesseract_langs_missing": [],
    }


async def test_health_reports_ai_model(make_app):
    app = make_app(client=FakeClient())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        body = (await http.get("/api/health")).json()
    assert body["ai_enabled"] is True
    assert body["model"] == "fake-model"


async def test_health_reports_missing_tesseract_packs(http, monkeypatch):
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["osd"])
    assert (await http.get("/api/health")).json()["tesseract_langs_missing"] == ["eng"]

    def not_installed(config=""):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_languages", not_installed)
    assert (await http.get("/api/health")).json()["tesseract_langs_missing"] == ["eng"]


async def test_health_never_contains_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("AI_ENABLED", "true")
    settings = Settings(data_dir=tmp_path / "data")
    app = create_app(settings, frontend_dist=tmp_path / "no-dist")  # client built from the settings
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            response = await http.get("/api/health")
    finally:
        app.state.queue.shutdown()
    assert response.status_code == 200
    assert response.json()["ai_enabled"] is True
    assert FAKE_KEY not in response.text
    assert "sk-ant" not in response.text


async def test_taxonomy(http):
    response = await http.get("/api/taxonomy")
    assert response.status_code == 200
    assert response.json() == taxonomy.as_json()


# Upload and documents


async def test_upload_processes_in_background(make_app, native_pdf):
    app = make_app(client=FakeClient())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        body = await upload(http, app, native_pdf, "batch 42.pdf")
        assert set(body) == {"document_id", "run_id", "status"}
        assert body["status"] in ("queued", "reading", "classifying", "validating", "done")
        docs = (await http.get("/api/documents")).json()
    assert len(docs) == 1
    assert docs[0]["id"] == body["document_id"]
    assert docs[0]["name"] == "batch 42.pdf"
    assert docs[0]["status"] == "done"
    assert docs[0]["n_dates"] == 1
    assert docs[0]["n_needs_review"] == 1


async def test_upload_identical_file_returns_latest_run(http, app, native_pdf):
    first = await upload(http, app, native_pdf)
    again = await upload(http, app, native_pdf, "renamed.pdf")
    assert again == {**first, "status": "done"}
    assert len((await http.get("/api/documents")).json()) == 1


async def test_upload_rejects_exe_415(http, app, tmp_path):
    response = await http.post(
        "/api/documents",
        files={"file": ("setup.exe", b"MZ\x90\x00" + b"\x00" * 200, "application/octet-stream")},
    )
    assert response.status_code == 415
    assert "PDF, PNG, JPG or TIFF" in response.json()["detail"]
    assert (await http.get("/api/documents")).json() == []
    assert stored_files(tmp_path / "data") == []


async def test_upload_oversize_413(make_app, tmp_path):
    app = make_app(max_upload_mb=1)
    big = b"%PDF-1.7\n" + b"0" * (1024 * 1024 + 10)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post("/api/documents", files={"file": ("big.pdf", big, "application/pdf")})
        assert response.status_code == 413
        assert "1 MB" in response.json()["detail"]
        assert (await http.get("/api/documents")).json() == []
    assert stored_files(tmp_path / "data") == []


async def test_upload_oversize_by_content_length_413(make_app):
    app = make_app(max_upload_mb=1)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(
            "/api/documents",
            content=b"x",
            headers={
                "content-type": "multipart/form-data; boundary=b",
                "content-length": str(5 * 1024 * 1024),
            },
        )
    assert response.status_code == 413


async def test_chunked_upload_over_the_limit_stops_reading_413(make_app, tmp_path):
    app = make_app(max_upload_mb=1)
    sent = 0

    async def body():  # no Content-Length: the request is sent chunked
        nonlocal sent
        head = b'--b\r\nContent-Disposition: form-data; name="file"; filename="big.pdf"\r\n\r\n%PDF-1.7\n'
        sent += len(head)
        yield head
        for _ in range(20):
            chunk = b"0" * (1024 * 1024)
            sent += len(chunk)
            yield chunk
        yield b"\r\n--b--\r\n"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(
            "/api/documents", content=body(), headers={"content-type": "multipart/form-data; boundary=b"}
        )
    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]
    assert sent < 3 * 1024 * 1024  # the server stopped reading soon after the limit
    assert stored_files(tmp_path / "data") == []


async def test_upload_without_file_422(http):
    response = await http.post("/api/documents", data={"other": "1"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


async def test_failed_document_reports_message(http, app, corrupt_pdf):
    body = await upload(http, app, corrupt_pdf)
    detail = (await http.get(f"/api/documents/{body['document_id']}")).json()
    assert detail["run"]["status"] == "failed"
    assert detail["run"]["error"] == "This file is damaged or incomplete and cannot be read."
    assert detail["pages"] == []


async def test_get_document(http, app, native_pdf):
    body = await upload(http, app, native_pdf)
    response = await http.get(f"/api/documents/{body['document_id']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["document"]["id"] == body["document_id"]
    assert detail["document"]["filename"] == "native.pdf"
    assert detail["document"]["pages"] == 1
    assert detail["run"] == {
        "id": body["run_id"],
        "status": "done",
        "error": None,
        "ai_used": False,
        "ai_model": None,
    }
    assert len(detail["pages"]) == 1
    page = detail["pages"][0]
    assert set(page) == {"n", "width", "height"}
    assert page["n"] == 1 and page["width"] > 1000 and page["height"] > 1000


async def test_get_unknown_document_404(http):
    response = await http.get("/api/documents/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Document 999 not found."}


async def test_page_image(http, app, native_pdf):
    body = await upload(http, app, native_pdf)
    response = await http.get(f"/api/documents/{body['document_id']}/pages/1.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert (await http.get(f"/api/documents/{body['document_id']}/pages/2.png")).status_code == 404
    assert (await http.get("/api/documents/999/pages/1.png")).status_code == 404


async def test_run_pages_stay_viewable_while_a_reprocess_reads(http, app, native_pdf):
    body = await upload(http, app, native_pdf)
    old_run = body["run_id"]
    newer = app.state.store.create_run(body["document_id"], "1.0.0", None, False)  # queued: no pages yet
    assert (await http.get(f"/api/documents/{body['document_id']}")).json()["pages"] == []

    pages = (await http.get(f"/api/runs/{old_run}/pages")).json()
    assert [set(p) for p in pages] == [{"n", "width", "height"}]
    assert pages[0]["n"] == 1 and pages[0]["width"] > 1000
    response = await http.get(f"/api/runs/{old_run}/pages/1.png")
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    assert (await http.get(f"/api/runs/{old_run}/pages/2.png")).status_code == 404
    assert (await http.get(f"/api/runs/{newer}/pages")).json() == []
    assert (await http.get("/api/runs/999/pages")).status_code == 404
    assert (await http.get("/api/runs/999/pages/1.png")).status_code == 404


# Run results


async def test_run_dates_flags_discarded(make_app, native_pdf):
    app = make_app(client=FakeClient())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        run_id = (await upload(http, app, native_pdf))["run_id"]
        dates = (await http.get(f"/api/runs/{run_id}/dates")).json()
        flags = await http.get(f"/api/runs/{run_id}/flags")
        discarded = (await http.get(f"/api/runs/{run_id}/discarded")).json()
    assert len(dates) == 1
    d = dates[0]
    assert d["raw_text"] == "31/03/2027"
    assert d["normalized"] == "2027-03-31"
    assert d["date_type"] == d["current_type"] == "expiry_date"
    assert d["status"] == "needs_review"
    assert d["run_id"] == run_id
    assert set(d["bbox"]) == {"x0", "y0", "x1", "y1"}
    assert flags.status_code == 200 and flags.json() == []
    assert len(discarded) == 1
    assert discarded[0]["verbatim_text"] == "01/01/2030"
    assert discarded[0]["reason"] == "not found in the page text"


@pytest.mark.parametrize("what", ["dates", "flags", "discarded", "export?format=json"])
async def test_unknown_run_404(http, what):
    response = await http.get(f"/api/runs/999/{what}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Run 999 not found."}


# Reviews


async def test_review_and_history(http, app, native_pdf):
    run_id = (await upload(http, app, native_pdf))["run_id"]
    date = await first_date(http, run_id)
    response = await review(http, date["id"], action="correct", new_type="retest_date", new_value="2027-03")
    assert response.status_code == 201
    event = response.json()
    assert event["date_id"] == date["id"]
    assert event["action"] == "correct"
    assert event["reviewer"] == "QA One"
    updated = await first_date(http, run_id)
    assert updated["status"] == "corrected"
    assert updated["current_type"] == "retest_date"
    assert updated["current_value"] == "2027-03"
    history = (await http.get(f"/api/dates/{date['id']}/history")).json()
    assert [e["id"] for e in history] == [event["id"]]


@pytest.mark.parametrize(
    "body, message",
    [
        ({"action": "accept", "reason": " "}, "a reason is required"),
        ({"action": "approve"}, "unknown review action 'approve'"),
        ({"action": "correct", "new_type": "birthday"}, "date type 'birthday' is not in the taxonomy"),
        ({"action": "correct", "new_value": "2027-02-30"}, "YYYY-MM-DD"),
        ({"action": "accept", "new_value": "2027-03-31"}, "only a correction"),
    ],
)
async def test_review_invalid_422(http, app, native_pdf, body, message):
    run_id = (await upload(http, app, native_pdf))["run_id"]
    date = await first_date(http, run_id)
    response = await review(http, date["id"], **body)
    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert (await http.get(f"/api/dates/{date['id']}/history")).json() == []


async def test_review_missing_fields_422(http, app, native_pdf):
    run_id = (await upload(http, app, native_pdf))["run_id"]
    date = await first_date(http, run_id)
    response = await http.post(f"/api/dates/{date['id']}/review", json={"action": "accept"})
    assert response.status_code == 422
    assert "reviewer" in response.json()["detail"]


async def test_review_unknown_date_404(http):
    response = await review(http, 999, action="accept")
    assert response.status_code == 404
    assert response.json() == {"detail": "Date 999 not found."}


async def test_review_frozen_run_409(http, app, native_pdf):
    body = await upload(http, app, native_pdf)
    old = await first_date(http, body["run_id"])
    response = await http.post(f"/api/documents/{body['document_id']}/reprocess")
    assert response.status_code == 202
    app.state.queue.wait()

    response = await review(http, old["id"], action="accept")
    assert response.status_code == 409
    assert "frozen" in response.json()["detail"]
    assert (await http.get(f"/api/dates/{old['id']}/history")).json() == []
    assert (await first_date(http, body["run_id"]))["status"] == "needs_review"


async def test_reprocess_carries_decisions(http, app, native_pdf):
    body = await upload(http, app, native_pdf)
    old = await first_date(http, body["run_id"])
    assert (await review(http, old["id"], action="accept")).status_code == 201

    response = await http.post(f"/api/documents/{body['document_id']}/reprocess")
    assert response.status_code == 202
    new_run = response.json()["run_id"]
    assert response.json() == {"run_id": new_run}
    assert new_run != body["run_id"]
    app.state.queue.wait()

    detail = (await http.get(f"/api/documents/{body['document_id']}")).json()
    assert detail["run"]["id"] == new_run and detail["run"]["status"] == "done"
    carried = await first_date(http, new_run)
    assert carried["status"] == "accepted"
    assert carried["carried_from_run"] == body["run_id"]


async def test_run_left_unfinished_by_a_restart_fails_and_can_be_reprocessed(http, app, make_app, native_pdf):
    body = await upload(http, app, native_pdf)
    stuck = app.state.store.create_run(body["document_id"], "1.0.0", None, False)
    app.state.store.set_run_status(stuck, "reading")  # the process was killed mid-run

    restarted = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as again:
        detail = (await again.get(f"/api/documents/{body['document_id']}")).json()
        assert detail["run"]["id"] == stuck and detail["run"]["status"] == "failed"
        assert "interrupted" in detail["run"]["error"]
        response = await again.post(f"/api/documents/{body['document_id']}/reprocess")
        assert response.status_code == 202
        restarted.state.queue.wait()
        assert restarted.state.store.get_run(response.json()["run_id"]).status == "done"


async def test_reprocess_unknown_document_404(http):
    response = await http.post("/api/documents/999/reprocess")
    assert response.status_code == 404


# Export


async def test_export_json_includes_history(http, app, native_pdf):
    body = await upload(http, app, native_pdf)
    date = await first_date(http, body["run_id"])
    await review(http, date["id"], action="accept")

    response = await http.get(f"/api/runs/{body['run_id']}/export?format=json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    assert f"run-{body['run_id']}.json" in response.headers["content-disposition"]
    exported = json.loads(response.content)
    assert exported["document"]["id"] == body["document_id"]
    assert exported["run"]["id"] == body["run_id"]
    assert exported["flags"] == []
    [d] = exported["dates"]
    assert d["status"] == "accepted"
    assert [e["action"] for e in d["history"]] == ["accept"]
    assert d["history"][0]["reviewer"] == "QA One"


async def test_export_csv_escapes_formula(http, app, native_pdf):
    body = await upload(http, app, native_pdf, "=cmd.pdf")
    date = await first_date(http, body["run_id"])
    await review(http, date["id"], action="accept", reviewer="@admin", reason='=HYPERLINK("http://x")')

    response = await http.get(f"/api/runs/{body['run_id']}/export?format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "accepted"
    assert row["raw_text"] == "31/03/2027"
    assert row["current_value"] == "2027-03-31"
    assert row["last_reviewer"] == "'@admin"
    assert row["last_reason"] == '\'=HYPERLINK("http://x")'
    assert row["document"] == "'=cmd.pdf"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("=1+2", "'=1+2"),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("@x", "'@x"),
        ("\tx", "'\tx"),
        ("\rx", "'\rx"),
        ("2027-03", "2027-03"),
        ("", ""),
        (None, ""),
        (0.9, "0.9"),
    ],
)
def test_csv_cell(value, expected):
    assert api.csv_cell(value) == expected


async def test_export_bad_format_422(http, app, native_pdf):
    body = await upload(http, app, native_pdf)
    response = await http.get(f"/api/runs/{body['run_id']}/export?format=xlsx")
    assert response.status_code == 422


# Frontend


async def test_serves_frontend_dist(make_app, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "outside.txt").write_text("not public")
    app = make_app(dist=dist)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        root = await http.get("/")
        asset = await http.get("/assets/app.js")
        route = await http.get("/documents/3")
        missing_api = await http.get("/api/nope")
        traversal = await http.get("/..%2Foutside.txt")
    assert root.status_code == 200 and "<title>app</title>" in root.text
    assert asset.status_code == 200 and asset.text == "console.log(1)"
    assert route.status_code == 200 and "<title>app</title>" in route.text  # client-side route
    assert missing_api.status_code == 404 and missing_api.json() == {"detail": "Not Found"}
    assert "not public" not in traversal.text


async def test_no_frontend_dist(http):
    assert (await http.get("/")).status_code == 404


# Request hardening


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "http://evil.example", "sec-fetch-site": "cross-site"},
        {"origin": "http://evil.example"},
        {"sec-fetch-site": "same-site"},
        {"origin": "null"},
    ],
)
async def test_cross_site_state_changes_are_refused(http, app, native_pdf, headers):
    body = await upload(http, app, native_pdf)
    response = await http.post(f"/api/documents/{body['document_id']}/reprocess", headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "Cross-site requests are not allowed."}
    response = await http.post(
        "/api/documents",
        files={"file": ("x.pdf", native_pdf.read_bytes(), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 403
    assert app.state.store.latest_run(body["document_id"]).id == body["run_id"]


async def test_same_origin_state_changes_are_allowed(http, app, native_pdf):
    body = await upload(http, app, native_pdf)
    headers = {"origin": "http://test", "sec-fetch-site": "same-origin"}
    response = await http.post(f"/api/documents/{body['document_id']}/reprocess", headers=headers)
    assert response.status_code == 202


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/runs/99999999999999999999/dates"),
        ("GET", "/api/documents/99999999999999999999"),
        ("GET", "/api/dates/99999999999999999999/history"),
        ("POST", "/api/documents/99999999999999999999/reprocess"),
        ("GET", "/api/documents/1/pages/99999999999999999999.png"),
        ("GET", "/api/runs/0/flags"),
    ],
)
async def test_out_of_range_ids_are_a_json_422(http, method, path):
    response = await http.request(method, path)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


async def test_out_of_range_review_id_is_a_json_422(http):
    response = await review(http, 99999999999999999999, action="accept")
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


async def test_unexpected_error_is_a_json_500(app, monkeypatch):
    def boom():
        raise RuntimeError("database file is locked: /secret/path")

    monkeypatch.setattr(app.state.store, "list_documents", boom)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/api/documents")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal error."}
