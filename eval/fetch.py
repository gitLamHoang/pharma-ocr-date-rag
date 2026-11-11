"""Download the public evaluation documents listed in `sources.json` into `eval/cache/` (git-ignored).

    uv run --project backend python eval/fetch.py

The documents are never committed: each is fetched from its publisher and kept only if its
SHA-256 matches the one recorded when the gold labels were written. A publisher that replaces a
file (a new certificate revision, say) makes that document fail here; its gold labels then need
re-checking against the new file before the hash in `sources.json` is updated.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
CACHE_DIR = EVAL_DIR / "cache"
USER_AGENT = "pharma-dates-eval/1.0 (evaluation set download)"
TIMEOUT_S = 60


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(source: dict) -> str:
    """Make sure one document is cached with the right hash; returns what happened."""
    target = CACHE_DIR / f"{source['id']}{source['ext']}"
    if target.exists() and sha256(target.read_bytes()) == source["sha256"]:
        return "cached"
    request = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        data = response.read()
    digest = sha256(data)
    if digest != source["sha256"]:
        raise ValueError(f"sha256 mismatch: expected {source['sha256']}, got {digest}")
    target.write_bytes(data)
    return f"downloaded ({len(data) // 1024} KB)"


def main() -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    sources = json.loads((EVAL_DIR / "sources.json").read_text(encoding="utf-8"))
    failed = 0
    for source in sources:
        try:
            print(f"{source['id']}: {fetch(source)}")
        except (OSError, ValueError) as exc:  # URLError and HTTPError are OSErrors
            failed += 1
            print(f"{source['id']}: FAILED {exc}", file=sys.stderr)
    if failed:
        sys.exit(f"{failed} of {len(sources)} documents could not be fetched")


if __name__ == "__main__":
    main()
