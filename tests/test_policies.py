import csv
import io
import json
from pathlib import Path

import pytest

from pharma_ocr_date_rag.pipeline import format_date_report, process_folder
from pharma_ocr_date_rag.policies import load_date_order_map, resolve_date_orders
from pharma_ocr_date_rag.rag import retrieve
from pharma_ocr_date_rag.reporting import date_rows, export_csv
from pharma_ocr_date_rag.review import history, index_folder, queue, review

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "mixed_conventions"


def test_explicit_document_orders_keep_same_token_distinct_and_unknown_unresolved():
    policies = load_date_order_map(FIXTURES / "date_orders.json")
    docs = process_folder(FIXTURES, date_order="mdy", date_order_map=policies)
    by_name = {doc.path.name: doc for doc in docs}
    assert by_name["us_receipt.txt"].dates[0].normalized == "2026-09-10"
    assert by_name["eu_receipt.txt"].dates[0].normalized == "2026-10-09"
    for name in ("us_receipt.txt", "eu_receipt.txt"):
        assert [(hit.normalized, hit.label) for hit in by_name[name].dates[1:]] == [
            ("2025-01-12", "manufacture"),
            ("2024-02-29", "qa_check"),
        ]
    unknown = by_name["unconfirmed_receipt.txt"]
    assert unknown.date_order == "auto"
    assert unknown.dates[0].normalized is None
    assert unknown.dates[0].candidates == ("2026-09-10", "2026-10-09")
    assert len(unknown.dates) == 2  # Invalid 31/02 must not leak a valid month/year suffix.
    assert unknown.dates[1].normalized == "2028-12"
    assert unknown.dates[1].precision == "month"
    assert sum(len(doc.dates) for doc in docs) == 8
    for doc in docs:
        assert f"date_order={policies[doc.path.name]}" in format_date_report(doc)
        for hit in doc.dates:
            assert doc.ocr.text[hit.start : hit.end] == hit.raw_text
        assert all(chunk.date_order == doc.date_order for chunk in doc.chunks)
        found = retrieve(doc.chunks, "expiry")
        assert found[0].dates[0].normalized == doc.dates[0].normalized
    rows = date_rows(docs)
    assert all(row["date_order"] == policies[row["document"]] for row in rows)
    csv_rows = list(csv.DictReader(io.StringIO(export_csv(rows))))
    assert all(row["date_order"] == policies[row["document"]] for row in csv_rows)


def test_sparse_map_inherits_default_and_explicit_auto_can_undo_global_order():
    paths = [Path("eu.txt"), Path("us.txt"), Path("unknown.txt")]
    overrides = {"eu.txt": "dmy", "unknown.txt": "auto"}
    assert resolve_date_orders(paths, "mdy", overrides) == {
        "eu.txt": "dmy",
        "us.txt": "mdy",
        "unknown.txt": "auto",
    }
    assert overrides == {"eu.txt": "dmy", "unknown.txt": "auto"}
    assert resolve_date_orders([], "auto", {}) == {}


def test_mixed_batch_stays_ambiguous_without_confirmed_per_document_orders():
    before = date_rows(process_folder(FIXTURES))
    policies = load_date_order_map(FIXTURES / "date_orders.json")
    after = date_rows(process_folder(FIXTURES, date_order_map=policies))
    assert len(before) == len(after) == 8
    assert sum(row["normalized"] is None for row in before) == 5
    assert sum(row["normalized"] is None for row in after) == 1
    assert {row["source_sha256"] for row in before} == {row["source_sha256"] for row in after}


@pytest.mark.parametrize(
    "bad",
    [
        [],
        None,
        "mdy",
        {"a.txt": "DMY"},
        {"a.txt": None},
        {"a.txt": ["dmy"]},
        {"../a.txt": "dmy"},
        {"nested/a.txt": "dmy"},
        {"C:\\a.txt": "mdy"},
        {"": "auto"},
    ],
)
def test_invalid_json_map_is_rejected(tmp_path, bad):
    path = tmp_path / "orders.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_date_order_map(path)


def test_duplicate_keys_and_malformed_json_are_rejected(tmp_path):
    path = tmp_path / "orders.json"
    path.write_text('{"a.txt":"mdy","a.txt":"dmy"}')
    with pytest.raises(ValueError, match="Duplicate document name"):
        load_date_order_map(path)
    path.write_text('{"a.txt":')
    with pytest.raises(ValueError):
        load_date_order_map(path)


def test_bom_and_exact_unicode_filenames_are_supported(tmp_path):
    path = tmp_path / "orders.json"
    path.write_text('{"phiếu.txt": "dmy"}', encoding="utf-8-sig")
    policy = load_date_order_map(path)
    assert resolve_date_orders([Path("phiếu.txt")], overrides=policy) == {"phiếu.txt": "dmy"}


@pytest.mark.parametrize("name", ["typo.txt", "*.txt", "date_orders.json"])
def test_bad_filename_fails_before_reading_documents_or_creating_database(tmp_path, name, monkeypatch):
    from pharma_ocr_date_rag import pipeline

    def unexpected(*args, **kwargs):
        pytest.fail("No source should be read for an invalid policy map")

    monkeypatch.setattr(pipeline, "process_document", unexpected)
    with pytest.raises(ValueError, match="missing or unsupported"):
        process_folder(FIXTURES, date_order_map={name: "dmy"})
    db = tmp_path / "reviews.sqlite"
    with pytest.raises(ValueError, match="missing or unsupported"):
        index_folder(FIXTURES, db, date_order_map={name: "dmy"})
    assert not db.exists()


def test_invalid_batch_default_is_rejected_even_if_every_file_has_override():
    with pytest.raises(ValueError, match="Unsupported date order"):
        resolve_date_orders([Path("eu.txt")], "guess", {"eu.txt": "dmy"})


def test_policy_change_versions_only_affected_document_and_preserves_history(tmp_path):
    db = tmp_path / "reviews.sqlite"
    policies = load_date_order_map(FIXTURES / "date_orders.json")
    assert index_folder(FIXTURES, db, date_order_map=policies)["new_hits"] == 8
    initial = queue(db, decision="all")
    eu = next(row for row in initial if row["path"] == "eu_receipt.txt" and row["label"] == "expiry")
    review(db, eu["id"], "accepted", "demo", "Synthetic source explicitly declares day/month/year")
    assert index_folder(FIXTURES, db, date_order_map=dict(reversed(list(policies.items()))))["unchanged"] == 3
    changed = {**policies, "eu_receipt.txt": "auto"}
    result = index_folder(FIXTURES, db, date_order_map=changed)
    assert result["indexed"] == 1
    assert result["unchanged"] == 2
    after = queue(db, decision="all")
    old_other_ids = [r["id"] for r in initial if r["path"] != "eu_receipt.txt"]
    assert [r["id"] for r in after if r["path"] != "eu_receipt.txt"] == old_other_ids
    unresolved = next(row for row in after if row["path"] == "eu_receipt.txt" and row["label"] == "expiry")
    assert unresolved["normalized"] is None
    assert unresolved["decision"] == "pending"
    assert unresolved["id"] != eu["id"]
    with pytest.raises(ValueError, match="inactive"):
        review(db, eu["id"], "accepted", "demo", "stale convention")
    assert len(history(db, eu["id"])) == 1
    assert index_folder(FIXTURES, db, date_order_map=policies)["reactivated"] == 1
    assert queue(db, decision="accepted")[0]["id"] == eu["id"]


def test_invalid_map_does_not_change_existing_queue(tmp_path):
    db = tmp_path / "reviews.sqlite"
    index_folder(FIXTURES, db)
    before = queue(db, decision="all")
    with pytest.raises(ValueError):
        index_folder(FIXTURES, db, date_order_map={"typo.txt": "dmy"})
    assert queue(db, decision="all") == before


def test_same_effective_order_reuses_version_regardless_of_configuration_source(tmp_path):
    db = tmp_path / "reviews.sqlite"
    index_folder(FIXTURES, db, date_order="dmy")
    before = queue(db, decision="all")
    result = index_folder(FIXTURES, db, date_order="dmy", date_order_map={"eu_receipt.txt": "dmy"})
    assert result["unchanged"] == 3
    assert queue(db, decision="all") == before


def test_policy_batch_extraction_failure_restores_prior_versions(tmp_path, monkeypatch):
    from pharma_ocr_date_rag import review as module

    db = tmp_path / "reviews.sqlite"
    index_folder(FIXTURES, db)
    before = queue(db, decision="all")
    original = module.process_document

    def fail_last(path, **kwargs):
        if path.name == "us_receipt.txt":
            raise RuntimeError("Simulated last-document failure")
        return original(path, **kwargs)

    monkeypatch.setattr(module, "process_document", fail_last)
    with pytest.raises(RuntimeError, match="last-document failure"):
        index_folder(FIXTURES, db, date_order_map=load_date_order_map(FIXTURES / "date_orders.json"))
    assert queue(db, decision="all") == before
