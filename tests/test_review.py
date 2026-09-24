import sqlite3

import pytest

from pharma_ocr_date_rag.review import database, history, index_folder, queue, review


@pytest.fixture
def source(tmp_path):
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "coa.txt").write_text("Expiry: 2027-06-30\nManufactured: 2026-01-01")
    return folder, tmp_path / "review.sqlite"


def test_idempotent_index_retains_review(source):
    folder, db = source
    assert index_folder(folder, db)["new_hits"] == 2
    hit = queue(db, label="expiry")[0]
    review(db, hit["id"], "accepted", "demo-reviewer", "Verified against synthetic source")
    assert index_folder(folder, db)["unchanged"] == 1
    assert len(queue(db)) == 1
    assert queue(db, decision="accepted")[0]["id"] == hit["id"]
    assert len(history(db, hit["id"])) == 1


def test_changed_version_and_reversion_preserve_evidence(source):
    folder, db = source
    index_folder(folder, db)
    old = queue(db)[0]
    review(db, old["id"], "rejected", "demo", "Incorrect in source")
    original = (folder / "coa.txt").read_text()
    (folder / "coa.txt").write_text("Expiry: 2028-06-30")
    assert index_folder(folder, db)["indexed"] == 1
    assert len(queue(db, decision="all")) == 1
    assert queue(db)[0]["content_sha256"] != old["content_sha256"]
    with pytest.raises(ValueError, match="inactive"):
        review(db, old["id"], "accepted", "demo", "stale")
    assert len(history(db, old["id"])) == 1
    (folder / "coa.txt").write_text(original)
    assert index_folder(folder, db)["reactivated"] == 1
    assert queue(db, decision="rejected")[0]["id"] == old["id"]


def test_append_only_history_and_parameterized_filters(source):
    folder, db = source
    index_folder(folder, db)
    hit = queue(db)[0]
    review(db, hit["id"], "needs_review", "demo", "Ambiguous source")
    review(db, hit["id"], "accepted", "demo", "Second inspection")
    assert [e["decision"] for e in history(db, hit["id"])] == ["needs_review", "accepted"]
    assert queue(db, label="expiry' OR 1=1 --") == []
    for decision, reviewer, reason in [
        ("made_up", "demo", "why"),
        ("accepted", "", "why"),
        ("accepted", "demo", " "),
    ]:
        with pytest.raises(ValueError):
            review(db, hit["id"], decision, reviewer, reason)
    with database(db) as conn:
        for query in ["DELETE FROM review_events", "UPDATE review_events SET decision='rejected'"]:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                conn.execute(query)


def test_extraction_failure_rolls_back_entire_batch(source, monkeypatch):
    from pharma_ocr_date_rag import review as module

    folder, db = source
    (folder / "z.txt").write_text("bad file")
    original = module.process_document

    def fail(path):
        if path.name == "z.txt":
            raise RuntimeError("OCR failed")
        return original(path)

    monkeypatch.setattr(module, "process_document", fail)
    with pytest.raises(RuntimeError):
        index_folder(folder, db)
    assert queue(db, decision="all") == []
    with database(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_pagination_and_collections_are_independent(source):
    folder, db = source
    index_folder(folder, db, "first")
    index_folder(folder, db, "second")
    assert len(queue(db)) == 4
    assert len(queue(db, collection="first")) == 2
    assert queue(db, limit=1, offset=1)[0]["id"] != queue(db, limit=1)[0]["id"]
    for kwargs in [{"limit": 0}, {"limit": 1001}, {"offset": -1}]:
        with pytest.raises(ValueError):
            queue(db, **kwargs)


def test_failed_update_restores_active_version_and_reviews(source, monkeypatch):
    from pharma_ocr_date_rag import review as module

    folder, db = source
    index_folder(folder, db)
    before = queue(db, decision="all")
    review(db, before[0]["id"], "accepted", "demo", "Verified old version")
    (folder / "coa.txt").write_text("Expiry: 2029-06-30")
    (folder / "z.txt").write_text("Expiry: 2030-06-30")
    original = module.process_document

    def fail(path):
        if path.name == "z.txt":
            raise RuntimeError("OCR failed after first file changed")
        return original(path)

    monkeypatch.setattr(module, "process_document", fail)
    with pytest.raises(RuntimeError):
        index_folder(folder, db)
    after = queue(db, decision="all")
    assert [row["id"] for row in after] == [row["id"] for row in before]
    assert after[0]["decision"] == "accepted"
    with database(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_changing_source_during_extraction_rolls_back(source, monkeypatch):
    from pharma_ocr_date_rag import review as module

    folder, db = source
    original = module.process_document

    def mutate(path):
        result = original(path)
        path.write_text("Expiry: 2040-01-01")
        return result

    monkeypatch.setattr(module, "process_document", mutate)
    with pytest.raises(ValueError, match="Source changed"):
        index_folder(folder, db)
    assert queue(db, decision="all") == []


def test_unsupported_database_schema_is_not_overwritten(tmp_path):
    db = tmp_path / "future.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA user_version = 99")
    with pytest.raises(ValueError, match="Unsupported database schema 99"):
        queue(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 99


def test_missing_files_keep_history_and_active_queue(source):
    folder, db = source
    index_folder(folder, db)
    before = queue(db, decision="all")
    (folder / "coa.txt").unlink()
    assert index_folder(folder, db)["indexed"] == 0
    assert queue(db, decision="all") == before
