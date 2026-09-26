"""Bounded, attributed collection of public MHRA medicine notices, not medical advice."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "PharmaDateReview/0.4 (+https://github.com/gitLamHoang/pharma-ocr-date-rag)"
HOSTS = {"www.gov.uk", "assets.publishing.service.gov.uk"}
LICENCE = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
ATTRIBUTION = "Contains public sector information licensed under the Open Government Licence v3.0. Source: MHRA / GOV.UK."


def allowed_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Only HTTPS GOV.UK content and publishing-service assets are allowed")
    if parsed.fragment:
        raise ValueError("Source URLs must not have fragments")
    return url


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"Source redirected; review the new URL before collecting it: {newurl}")


class PublicClient:
    """One request/second, robots checks, bounded downloads and an immutable local cache."""

    def __init__(self, cache: Path):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.opener = urllib.request.build_opener(NoRedirects())
        self.robots = {}
        self.last_request = 0.0

    def _request(self, url: str, limit: int) -> bytes:
        time.sleep(max(0.0, 1.0 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        request = urllib.request.Request(allowed_url(url), headers={"User-Agent": USER_AGENT})
        with self.opener.open(request, timeout=45) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"Source exceeds the {limit}-byte download limit")
        return data

    def get(self, url: str, limit: int = 2_000_000) -> tuple[bytes, dict]:
        allowed_url(url)
        origin = "https://" + urllib.parse.urlsplit(url).netloc
        if origin not in self.robots:
            robot = urllib.robotparser.RobotFileParser()
            try:
                raw = self._request(origin + "/robots.txt", 200_000)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                raw = b"User-agent: *\nAllow: /\n"
            robot.parse(raw.decode("utf-8").splitlines())
            self.robots[origin] = robot
        if not self.robots[origin].can_fetch(USER_AGENT, url):
            raise ValueError(f"robots.txt does not permit this request: {url}")
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / f"{key}.bin"
        metadata = self.cache / f"{key}.json"
        if path.exists() and metadata.exists():
            data = path.read_bytes()
            info = json.loads(metadata.read_text(encoding="utf-8"))
            if info["url"] != url or hashlib.sha256(data).hexdigest() != info["sha256"]:
                raise ValueError("Cached source failed integrity check")
            if len(data) > limit:
                raise ValueError("Cached source exceeds the requested size limit")
            return data, info
        data = self._request(url, limit)
        info = {
            "url": url,
            "sha256": hashlib.sha256(data).hexdigest(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_bytes(data)
        metadata.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        return data, info


def extract_tables(body: str) -> tuple[list[dict], list[dict]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body, "html.parser")
    tables, excluded = [], []
    for index, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        if not rows:
            continue
        cells = [row.find_all(["th", "td"], recursive=False) for row in rows]
        headers = [cell.get_text(" ", strip=True) for cell in cells[0]]
        reason = None
        if any(
            int(cell.get("rowspan", 1)) != 1 or int(cell.get("colspan", 1)) != 1
            for row in cells
            for cell in row
        ):
            reason = "merged_cells"
        elif not cells[0] or not any(cell.name == "th" for cell in cells[0]):
            reason = "no_explicit_header"
        elif len(headers) != len(set(headers)) or any(len(row) != len(headers) for row in cells):
            reason = "irregular_columns"
        if reason:
            excluded.append({"table_index": index, "reason": reason})
            continue
        heading = table.find_previous(["h2", "h3", "h4"])
        tables.append(
            {
                "table_index": index,
                "heading": heading.get_text(" ", strip=True) if heading else "",
                "headers": headers,
                "rows": [[cell.get_text(" ", strip=True) for cell in row] for row in cells[1:]],
            }
        )
        if not any("batch" in header.casefold() or "lot" in header.casefold() for header in headers):
            tables[-1]["rows"] = []
            tables[-1]["rows_omitted"] = "non_batch_table; headings retained as classifier negatives"
    return tables, excluded


def notice_record(item: dict, provenance: dict) -> dict:
    if item.get("document_type") != "medical_safety_alert" or not item.get("base_path", "").startswith(
        "/drug-device-alerts/"
    ):
        raise ValueError("Source is not a GOV.UK medical safety alert")
    organisations = item.get("links", {}).get("organisations", [])
    if not any(org.get("details", {}).get("acronym") == "MHRA" for org in organisations):
        raise ValueError("Source is not published by MHRA")
    body = item.get("details", {}).get("body", "")
    tables, excluded = extract_tables(body)
    pdfs = [
        allowed_url(a["url"])
        for a in item.get("details", {}).get("attachments", [])
        if a.get("content_type") == "application/pdf"
    ]
    return {
        "id": item["content_id"],
        "title": item["title"],
        "url": "https://www.gov.uk" + item["base_path"],
        "published_at": item.get("first_published_at"),
        "updated_at": item.get("public_updated_at"),
        "language": item.get("locale"),
        "source": provenance,
        "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "licence": LICENCE,
        "tables": tables,
        "excluded_tables": excluded,
        "pdf_urls": pdfs,
    }
