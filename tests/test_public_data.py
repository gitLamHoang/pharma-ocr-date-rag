import json
import urllib.robotparser

import pytest

from pharma_ocr_date_rag.public_data import PublicClient, allowed_url, extract_tables


@pytest.mark.parametrize(
    "url",
    [
        "http://www.gov.uk/a",
        "https://evil.test/a",
        "https://www.gov.uk.evil.test/a",
        "https://user:secret@www.gov.uk/a",
        "https://www.gov.uk:444/a",
        "file:///etc/passwd",
        "https://www.gov.uk/a#fragment",
    ],
)
def test_collector_rejects_non_allowlisted_sources(url):
    with pytest.raises(ValueError):
        allowed_url(url)


def test_crawler_cache_is_hashed_and_never_silently_replaced(tmp_path, monkeypatch):
    client = PublicClient(tmp_path)
    robot = urllib.robotparser.RobotFileParser()
    robot.parse(["User-agent: *", "Allow: /"])
    client.robots["https://www.gov.uk"] = robot
    calls = []
    monkeypatch.setattr(
        client, "_request", lambda url, limit: calls.append(url) or b'{"real":"cached bytes"}'
    )
    url = "https://www.gov.uk/api/content/drug-device-alerts/example"
    first = client.get(url)
    assert client.get(url) == first
    assert calls == [url]
    next(tmp_path.glob("*.bin")).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity"):
        client.get(url)


def test_collector_honors_robots_before_download(tmp_path, monkeypatch):
    client = PublicClient(tmp_path)
    monkeypatch.setattr(client, "_request", lambda url, limit: b"User-agent: *\nDisallow: /api/\n")
    with pytest.raises(ValueError, match="robots.txt"):
        client.get("https://www.gov.uk/api/content/drug-device-alerts/example")


def test_tables_preserve_cells_and_omit_non_batch_prose():
    pytest.importorskip("bs4")
    body = "<h2>Lots</h2><table><tr><th>Batch No.</th><th>Expiry Date</th></tr><tr><td>001</td><td>05/2028</td></tr></table><table><tr><th>Advice</th></tr><tr><td>Excluded prose</td></tr></table>"
    tables, excluded = extract_tables(body)
    assert excluded == []
    assert tables[0]["rows"] == [["001", "05/2028"]]
    assert tables[0]["heading"] == "Lots"
    assert tables[1]["rows"] == [] and "rows_omitted" in tables[1]
    assert "Excluded prose" not in json.dumps(tables)


@pytest.mark.parametrize(
    "body,reason",
    [
        ('<table><tr><th colspan="2">Batch</th></tr><tr><td>A</td><td>B</td></tr></table>', "merged_cells"),
        ("<table><tr><td>Batch</td></tr><tr><td>A</td></tr></table>", "no_explicit_header"),
        ("<table><tr><th>Batch</th><th>Date</th></tr><tr><td>A</td></tr></table>", "irregular_columns"),
    ],
)
def test_unsupported_table_layouts_are_reported(body, reason):
    pytest.importorskip("bs4")
    tables, excluded = extract_tables(body)
    assert not tables
    assert excluded == [{"table_index": 0, "reason": reason}]
