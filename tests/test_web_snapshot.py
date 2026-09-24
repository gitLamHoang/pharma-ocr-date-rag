import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_snapshot_keeps_exact_source_and_rendered_image_evidence():
    public = ROOT / "web" / "public"
    data = json.loads((public / "data" / "workspace.json").read_text(encoding="utf-8"))
    assert data["schemaVersion"] == 1
    assert len(data["documents"]) == 8
    assert {doc["language"] for doc in data["documents"]} == {"en", "fr", "de", "es", "vi"}
    for doc in data["documents"]:
        assert hashlib.sha256(doc["text"].encode()).hexdigest() == doc["sha256"]
        assert hashlib.sha256((public / doc["image"]).read_bytes()).hexdigest() == doc["imageSha256"]
        for field in doc["fields"]:
            assert doc["text"][field["start"] : field["end"]] == field["raw_text"]
            assert field["source_sha256"] == doc["sha256"]
            x, y, width, height = field["box"]
            assert 0 <= x < x + width <= 1
            assert 0 <= y < y + height <= 1


def test_public_snapshot_is_reproducible():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/export_web.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
