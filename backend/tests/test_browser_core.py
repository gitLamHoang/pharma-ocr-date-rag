"""The pure core the static build runs in Pyodide: self-contained, and the same results as the server."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pharma_dates import browser
from pharma_dates.pipeline import run_document
from pharma_dates.store import Store

BACKEND = Path(__file__).resolve().parents[1]
MANIFEST = BACKEND.parent / "frontend" / "src" / "engine" / "pycore-modules.json"
MODULES = json.loads(MANIFEST.read_text(encoding="utf-8"))["modules"]
needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")

# Run in a fresh interpreter that holds only the bundled files and refuses any import outside the
# standard library and pydantic (and pydantic's own dependencies), as Pyodide would.
_ISOLATED = r"""
import sys
ALLOWED = {"pydantic", "pydantic_core", "typing_extensions", "annotated_types", "typing_inspection"}

class Guard:
    def find_spec(self, name, path=None, target=None):
        top = name.split(".")[0]
        if top in sys.stdlib_module_names or top in ALLOWED or top == "pharma_dates" or top.startswith("_"):
            return None
        raise ImportError(f"the browser core imported {name!r}")

sys.meta_path.insert(0, Guard())
sys.path.insert(0, sys.argv[1])
from pharma_dates import browser
out = browser.process('[{"n": 1, "width": 100, "height": 20, "text": "Expiry date: 31/03/2027",'
                      ' "text_source": "pdf", "words": []}]', "2026-11-11")
print(out)
"""


def test_manifest_lists_every_core_module():
    for rel in MODULES:
        assert (BACKEND / rel).is_file(), rel
    for core in ("models", "taxonomy", "candidates", "classify", "validate", "browser"):
        assert f"pharma_dates/{core}.py" in MODULES
    rules = sorted(
        p.relative_to(BACKEND).as_posix() for p in (BACKEND / "pharma_dates" / "rules").glob("*.py")
    )
    assert set(rules) <= set(MODULES)


def test_bundled_modules_import_with_only_stdlib_and_pydantic(tmp_path):
    for rel in MODULES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BACKEND / rel, target)
    result = subprocess.run(
        [sys.executable, "-I", "-c", _ISOLATED, str(tmp_path)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    dates = json.loads(result.stdout)["dates"]
    assert [d["normalized"] for d in dates] == ["2027-03-31"]
    assert dates[0]["date_type"] == "expiry_date"


def test_taxonomy_json_matches_the_api():
    from pharma_dates import taxonomy

    assert json.loads(browser.taxonomy_json()) == taxonomy.as_json()


def _server_and_browser(path: Path, name: str, settings) -> tuple[list[dict], list[dict], list, list]:
    store = Store(settings.data_dir / "store.sqlite")
    run_id = run_document(path, name, store, settings, None)
    assert store.get_run(run_id).status == "done"
    layouts = [p.model_dump(exclude={"image_path"}) for p in store.pages_for_run(run_id)]
    out = json.loads(browser.process(json.dumps(layouts)))
    server_dates = [
        d.model_dump(include=_COMPARED, mode="json") | {"candidate_id": d.candidate_id}
        for d in store.dates_for_run(run_id)
    ]
    browser_dates = [{k: d[k] for k in _COMPARED} | {"candidate_id": d["id"]} for d in out["dates"]]
    by_candidate = {d.id: d.candidate_id for d in store.dates_for_run(run_id)}
    server_flags = [
        (f.rule, f.severity, f.message, sorted(by_candidate[i] for i in f.date_ids))
        for f in store.flags_for_run(run_id)
    ]
    browser_flags = [(f["rule"], f["severity"], f["message"], sorted(f["date_ids"])) for f in out["flags"]]
    return server_dates, browser_dates, server_flags, browser_flags


_COMPARED = {
    "page", "raw_text", "normalized", "candidates", "precision", "char_start", "char_end", "bbox",
    "line_boxes", "context", "rule_label", "source", "date_type", "family", "qualifier",
    "resolved_value", "evidence", "confidence", "rationale",
}  # fmt: skip


def test_browser_core_matches_the_offline_server_pipeline(tmp_path, make_pdf, settings):
    pdf = make_pdf(
        tmp_path / "doc.pdf",
        [
            "Manufacturing date: 12 March 2026",
            "Expiry date: 31/03/2025 Approved on 09/10/2026",
            "Signed 13/04/2026 and 05/06/2026",
        ],
    )
    server, local, server_flags, local_flags = _server_and_browser(pdf, "doc.pdf", settings)
    assert len(server) >= 4
    assert local == server
    assert local_flags == server_flags


@needs_tesseract
def test_browser_core_matches_the_server_on_an_ocr_page(scanned_png, settings):
    server, local, server_flags, local_flags = _server_and_browser(scanned_png, "scan.png", settings)
    assert [d["normalized"] for d in server] == ["2027-03-31"]
    assert local == server and local_flags == server_flags
