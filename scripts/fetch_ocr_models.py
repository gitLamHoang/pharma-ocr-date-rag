"""Download only the three pinned public language packs used in the OCR experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "ocr_models.json"


def model_hashes(directory: Path) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    hashes = {}
    for language, expected in manifest["models"].items():
        path = directory / f"{language}.traineddata"
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if actual is not None and actual != expected:
            raise ValueError(f"Unexpected SHA-256 for {path}; refusing to use an unpinned model")
        hashes[language] = actual
    return hashes


def fetch(directory: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    current = model_hashes(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for language, expected in manifest["models"].items():
        if current[language] == expected:
            print(f"{language}: verified cached model")
            continue
        url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{manifest['revision']}/{language}.traineddata"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Download checksum mismatch for {language}; no model written")
        (directory / f"{language}.traineddata").write_bytes(data)
        print(f"{language}: downloaded and verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "tessdata")
    args = parser.parse_args()
    fetch(args.output)
