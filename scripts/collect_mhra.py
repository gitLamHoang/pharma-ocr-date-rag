"""Collect a bounded snapshot of real MHRA medicine notices using official GOV.UK APIs."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pharma_ocr_date_rag.public_data import ATTRIBUTION, LICENCE, PublicClient, notice_record


def collect(count: int, output: Path, cache: Path) -> dict:
    if not 1 <= count <= 100:
        raise ValueError("Choose between 1 and 100 notices per collection")
    client = PublicClient(cache)
    query = urllib.parse.urlencode(
        {
            "filter_format": "medical_safety_alert",
            "filter_alert_type": "medicines-recall-notification",
            "order": "-public_timestamp",
            "count": count,
            "fields": "title,link,public_timestamp",
        }
    )
    raw, search_source = client.get("https://www.gov.uk/api/search.json?" + query)
    found = json.loads(raw)
    documents, seen = [], set()
    for result in found["results"]:
        path = result["link"]
        if not path.startswith("/drug-device-alerts/") or "?" in path or "#" in path:
            raise ValueError("Unexpected path in search response")
        raw, source = client.get("https://www.gov.uk/api/content" + path)
        item = json.loads(raw)
        if item["base_path"] != path:
            raise ValueError("Content API returned a different document")
        record = notice_record(item, source)
        if record["id"] in seen:
            raise ValueError("Duplicate source content identity")
        seen.add(record["id"])
        documents.append(record)
        print(
            f"{len(documents)}/{count}: {len(record['tables'])} tables | {record['title'][:90]}", flush=True
        )
    snapshot = {
        "schema_version": 1,
        "attribution": ATTRIBUTION,
        "licence": LICENCE,
        "scope": "Public MHRA medicine recall/defect notices. Table excerpts only; no patient records, safety recommendations or contact details. Not a live recall service.",
        "selection": search_source,
        "available_notices": found["total"],
        "documents": documents,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--output", type=Path, default=ROOT / "data/public_mhra/documents.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "outputs/mhra/cache")
    args = parser.parse_args()
    collect(args.count, args.output, args.cache)
