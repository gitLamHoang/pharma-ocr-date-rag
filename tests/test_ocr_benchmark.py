import copy
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from pharma_ocr_date_rag.ocr import OCRExecutionError, OCRResult, OCRUnavailable

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("benchmark_ocr")


def test_hand_authored_gold_matches_text_baseline(experiment):
    cases = json.loads(experiment.DATASET.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 3 and sum(len(case["expected"]) for case in cases) == 16
    for case in cases:
        text = (ROOT / case["source"]).read_text(encoding="utf-8")
        assert experiment.score_fields(case["expected"], experiment.field_records(text, case))["exact"]


def test_metrics_count_duplicates_and_preserve_ambiguity(experiment):
    gold = [{"label": "audit", "normalized": None, "candidates": ["2026-09-10", "2026-10-09"]}]
    assert experiment.score_fields(gold, gold * 2)["false_positive"] == 1
    guessed = [{"label": "audit", "normalized": "2026-10-09", "candidates": ["2026-10-09"]}]
    score = experiment.score_fields(gold, guessed)
    assert (score["true_positive"], score["false_positive"], score["false_negative"]) == (0, 1, 1)
    assert experiment.score_fields(gold, [])["recall"] == 0


def test_degradation_is_repeatable_without_changing_source(experiment, tmp_path):
    pytest.importorskip("PIL")
    source = ROOT / "web/public/documents/fr_certificat.png"
    original = source.read_bytes()
    first = experiment.prepare_image(source, "degraded", tmp_path / "first.png")
    second = experiment.prepare_image(source, "degraded", tmp_path / "second.png")
    assert first.read_bytes() == second.read_bytes() != original
    assert source.read_bytes() == original
    assert experiment.prepare_image(source, "clean", tmp_path / "unused.png") == source


@pytest.mark.parametrize(
    "error,status", [(OCRUnavailable("missing"), "unavailable"), (OCRExecutionError("timeout"), "failed")]
)
def test_incomplete_run_has_no_fabricated_scores(experiment, monkeypatch, tmp_path, error, status):
    monkeypatch.setattr(experiment, "model_hashes", lambda _: {"eng": None, "fra": None, "vie": None})
    monkeypatch.setattr(experiment, "tesseract_info", lambda _: {})
    monkeypatch.setattr(experiment, "prepare_image", lambda source, *args: source)

    def recognize(*args, **kwargs):
        raise error

    monkeypatch.setattr(experiment, "read_tesseract", recognize)
    report = experiment.benchmark(tmp_path, tmp_path)
    assert all(row["status"] == status and "score" not in row for row in report["results"])
    for summary in report["summary"].values():
        assert summary[status] == 3
        assert summary["measured"] == summary["expected_fields_measured_pages"] == 0
        assert summary["expected_fields_all_pages"] == 16


def test_empty_ocr_is_measured_failure_not_unavailable(experiment, monkeypatch, tmp_path):
    monkeypatch.setattr(experiment, "model_hashes", lambda _: {})
    monkeypatch.setattr(experiment, "tesseract_info", lambda _: {})
    monkeypatch.setattr(experiment, "prepare_image", lambda source, *args: source)
    monkeypatch.setattr(experiment, "read_tesseract", lambda *args, **kwargs: OCRResult("", "tesseract"))
    report = experiment.benchmark(tmp_path, tmp_path)
    for summary in report["summary"].values():
        assert summary["measured"] == 3
        assert summary["false_negative"] == 16
        assert summary["true_positive"] == 0


def test_reject_unpinned_model(experiment, tmp_path):
    (tmp_path / "eng.traineddata").write_bytes(b"wrong model")
    with pytest.raises(ValueError, match="Unexpected SHA-256"):
        experiment.model_hashes(tmp_path)


def test_checked_in_ocr_evidence_matches_inputs_and_saved_text(experiment):
    report = json.loads(experiment.REPORT.read_text(encoding="utf-8"))
    experiment.check_report(report)
    for row in report["results"]:
        for field in row["predicted"]:
            assert row["ocr_text"][field["start"] : field["end"]] == field["raw_text"]


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "score",
        "summary",
        "missing_row",
        "duplicate_row",
        "unavailable",
        "protocol",
        "language",
        "image",
    ],
)
def test_report_checker_rejects_stale_or_inconsistent_evidence(experiment, change):
    report = copy.deepcopy(json.loads(experiment.REPORT.read_text(encoding="utf-8")))
    if change == "hash":
        report["input_and_source_sha256"]["data/ocr_cases.json"] = "changed"
    elif change == "score":
        report["results"][0]["score"]["true_positive"] += 1
    elif change == "summary":
        report["summary"]["clean"]["true_positive"] += 1
    elif change == "missing_row":
        report["results"].pop()
    elif change == "duplicate_row":
        report["results"][0] = report["results"][1]
    elif change == "protocol":
        report["settings"]["psm"] = 3
    elif change == "language":
        report["results"][0]["ocr_language"] = "fra"
    elif change == "image":
        report["results"][0]["image_sha256"] = "changed"
    else:
        report["results"][0]["status"] = "unavailable"
    with pytest.raises(ValueError):
        experiment.check_report(report)


def test_require_complete_returns_nonzero_for_missing_language_directory(tmp_path):
    output = tmp_path / "result.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/benchmark_ocr.py"),
            "--require-complete",
            "--tessdata-dir",
            str(tmp_path / "missing"),
            "--output",
            str(output),
            "--images-dir",
            str(tmp_path / "images"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1 and "Incomplete OCR run" in result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert all(row["status"] == "unavailable" for row in report["results"])
