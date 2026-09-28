import sqlite3
from pathlib import Path

import pytest

from pharma_ocr_date_rag.review import (
    database,
    document_action,
    document_history,
    document_versions,
    history,
    index_folder,
    queue,
    review,
)


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


def test_ambiguous_queue_and_configuration_changes_keep_separate_reviews(source):
    folder, db = source
    (folder / "coa.txt").write_text("Date de péremption: 09/10/2026", encoding="utf-8")
    assert index_folder(folder, db)["new_hits"] == 1
    ambiguous = queue(db)[0]
    assert ambiguous["normalized"] is None
    assert ambiguous["candidates"] == ["2026-09-10", "2026-10-09"]
    assert ambiguous["review_reasons"] == ["ambiguous_numeric_date"]
    assert ambiguous["source_start"] == 20
    with pytest.raises(ValueError, match="ambiguous"):
        review(db, ambiguous["id"], "accepted", "demo", "unresolved")
    review(db, ambiguous["id"], "needs_review", "demo", "Confirm convention")
    assert index_folder(folder, db, date_order="dmy")["new_hits"] == 1
    resolved = queue(db)[0]
    assert resolved["normalized"] == "2026-10-09"
    assert resolved["id"] != ambiguous["id"]
    assert resolved["decision"] == "pending"
    assert len(history(db, ambiguous["id"])) == 1
    assert index_folder(folder, db)["reactivated"] == 1
    assert queue(db, decision="needs_review")[0]["id"] == ambiguous["id"]


def test_v1_migration_preserves_review_ids_history_and_foreign_keys(tmp_path):
    db = tmp_path / "old.sqlite"
    schema = (Path(__file__).parent / "fixtures" / "review_schema_v1.sql").read_text()
    with sqlite3.connect(db) as conn:
        conn.executescript(schema)
        conn.execute(
            "INSERT INTO documents VALUES(7,'demo','old.txt','abc','dates-v1','plain-text',1,'past')"
        )
        conn.execute("INSERT INTO date_hits VALUES(11,7,'2029-07','expiry','07/2029','EXP: 07/2029',0.9)")
        conn.execute("INSERT INTO review_events VALUES(5,11,'accepted','demo','Checked original','past')")
    assert queue(db, decision="accepted")[0]["id"] == 11
    assert queue(db, decision="accepted")[0]["precision"] == "month"
    assert queue(db, decision="accepted")[0]["candidates"] == ["2029-07"]
    assert history(db, 11)[0]["id"] == 5
    with database(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM review_events")
    review(db, 11, "needs_review", "demo", "Review after migration")
    assert len(history(db, 11)) == 2


def test_reopen_appends_decisions_to_every_field_without_changing_other_documents(source):
    folder, db = source
    (folder / "other.txt").write_text("Expiry: 09/10/2026")
    index_folder(folder, db)
    before = queue(db, decision="all")
    doc_id = before[0]["document_id"]
    review(db, before[0]["id"], "accepted", "demo", "First inspection")
    review(db, before[1]["id"], "rejected", "demo", "Wrong field")
    result = document_action(db, doc_id, "reopen", " second reviewer ", " Check the source again ")
    assert result["hits_reopened"] == 2
    assert result["event"]["reviewer"] == "second reviewer"
    assert result["event"]["reason"] == "Check the source again"
    assert len(queue(db, decision="needs_review")) == 2
    assert len(queue(db)) == 1
    assert [row["id"] for row in queue(db, decision="all")] == [row["id"] for row in before]
    assert [event["decision"] for event in history(db, before[0]["id"])] == ["accepted", "needs_review"]
    assert document_history(db, doc_id) == [result["event"]]
    assert index_folder(folder, db)["unchanged"] == 2
    assert len(history(db, before[0]["id"])) == 2
    assert document_action(db, doc_id, "reopen", "demo", "Another explicit cycle")["hits_reopened"] == 2
    assert len(document_history(db, doc_id)) == 2


def test_retirement_blocks_all_source_versions_and_settings_until_explicit_restore(source):
    folder, db = source
    index_folder(folder, db, "demo")
    old = queue(db)[0]
    review(db, old["id"], "accepted", "demo", "Checked")
    retired = document_action(db, old["document_id"], "retire", "demo", "Source withdrawn")
    assert retired["hits_reopened"] == 0
    assert queue(db, decision="all") == []
    assert history(db, old["id"])[0]["decision"] == "accepted"
    assert document_versions(db, state="retired")[0]["id"] == old["document_id"]
    assert index_folder(folder, db, "demo")["retired_skipped"] == 1
    (folder / "coa.txt").write_text("Expiry: 2030-01-01")
    assert index_folder(folder, db, "demo", date_order="dmy")["retired_skipped"] == 1
    assert len(document_versions(db, state="all")) == 1
    with pytest.raises(ValueError, match="inactive"):
        review(db, old["id"], "accepted", "demo", "No bypass")
    restored = document_action(db, old["document_id"], "restore", "demo", "Return for checking")
    assert restored["hits_reopened"] == 2
    assert document_versions(db)[0]["state"] == "active"
    assert [event["decision"] for event in history(db, old["id"])] == ["accepted", "needs_review"]
    assert len(queue(db, decision="needs_review")) == 2
    assert index_folder(folder, db, "demo")["indexed"] == 1
    assert queue(db)[0]["normalized"] == "2030-01-01"
    assert document_versions(db, state="superseded")[0]["id"] == old["document_id"]
    assert [event["action"] for event in document_history(db, old["document_id"])] == ["retire", "restore"]


def test_only_active_version_can_retire_and_only_last_retired_version_can_restore(source):
    folder, db = source
    index_folder(folder, db)
    first = document_versions(db)[0]["id"]
    (folder / "coa.txt").write_text("Expiry: 2030-01-01")
    index_folder(folder, db)
    second = document_versions(db)[0]["id"]
    for action in ["reopen", "retire", "restore"]:
        with pytest.raises(ValueError):
            document_action(db, first, action, "demo", "Stale version")
    with pytest.raises(ValueError, match="last explicitly retired"):
        document_action(db, second, "restore", "demo", "Not retired")
    document_action(db, second, "retire", "demo", "Withdraw source")
    assert len(document_versions(db, state="retired")) == 2
    for doc_id, action in [(first, "restore"), (second, "retire"), (second, "reopen")]:
        with pytest.raises(ValueError):
            document_action(db, doc_id, action, "demo", "No stale action")
    assert len(document_history(db, second)) == 1
    document_action(db, second, "restore", "demo", "Check again")
    with pytest.raises(ValueError):
        document_action(db, second, "restore", "demo", "No duplicate restore")


def test_retirement_is_collection_scoped_and_can_target_missing_files_without_hits(source):
    folder, db = source
    (folder / "coa.txt").write_text("No dates here")
    index_folder(folder, db, "first")
    index_folder(folder, db, "second")
    doc = document_versions(db, collection="first")[0]
    assert doc["hit_count"] == 0
    (folder / "coa.txt").unlink()
    assert document_action(db, doc["id"], "retire", "demo", "No longer a source")["hits_reopened"] == 0
    assert document_versions(db, collection="first") == []
    assert document_versions(db, collection="second")[0]["state"] == "active"
    assert document_action(db, doc["id"], "restore", "demo", "Restore stored evidence")["hits_reopened"] == 0
    assert len(document_history(db, doc["id"])) == 2


@pytest.mark.parametrize("action", ["reopen", "restore"])
def test_document_action_failure_rolls_back_all_events_and_active_state(source, action):
    folder, db = source
    index_folder(folder, db)
    doc_id = document_versions(db)[0]["id"]
    hits = queue(db)
    if action == "restore":
        document_action(db, doc_id, "retire", "demo", "Withdrawn")
    before = document_history(db, doc_id)
    with database(db) as conn, conn:
        conn.execute(
            f"CREATE TRIGGER fail_second_hit BEFORE INSERT ON review_events WHEN NEW.hit_id={hits[1]['id']} "
            "BEGIN SELECT RAISE(ABORT, 'Simulated write failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="Simulated"):
        document_action(db, doc_id, action, "demo", "All or nothing")
    assert document_history(db, doc_id) == before
    assert all(history(db, row["id"]) == [] for row in hits)
    assert document_versions(db, state="all")[0]["active"] == (action == "reopen")


def test_document_events_are_append_only_and_inputs_are_validated(source):
    folder, db = source
    index_folder(folder, db)
    doc_id = document_versions(db)[0]["id"]
    for action, reviewer, reason in [("delete", "demo", "why"), ("reopen", " ", "why"), ("retire", "a", " ")]:
        with pytest.raises(ValueError):
            document_action(db, doc_id, action, reviewer, reason)
    with pytest.raises(ValueError, match="does not exist"):
        document_action(db, 999, "reopen", "demo", "Unknown ID")
    document_action(db, doc_id, "reopen", "demo", "Check again")
    with database(db) as conn:
        for statement in ["DELETE FROM document_events", "UPDATE document_events SET action='retire'"]:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                conn.execute(statement)
    assert document_versions(db, collection="documents' OR 1=1 --") == []
    for kwargs in [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"state": "unknown"}]:
        with pytest.raises(ValueError):
            document_versions(db, **kwargs)
    assert document_versions(db, offset=1) == []


@pytest.mark.parametrize("interrupt", [False, True])
def test_v2_upgrade_is_additive_and_transactional(source, monkeypatch, interrupt):
    from pharma_ocr_date_rag import review as module

    _, db = source
    schema = (Path(__file__).parent / "fixtures" / "review_schema_v2.sql").read_text()
    with sqlite3.connect(db) as conn:
        conn.executescript(schema)
        conn.execute(
            "INSERT INTO documents VALUES(7,'demo','old.txt','abc','dates-v2','plain-text',1,'past')"
        )
        conn.execute(
            "INSERT INTO date_hits(id,document_id,normalized,label,extracted_text,context,heuristic_confidence) "
            "VALUES(11,7,'2029-07','expiry','07/2029','EXP: 07/2029',0.9)"
        )
        conn.execute("INSERT INTO review_events VALUES(5,11,'accepted','demo','Checked original','past')")
    if interrupt:
        execute = module._execute_script

        def fail_after_upgrade(connection, script):
            execute(connection, script)
            raise RuntimeError("Simulated interruption")

        monkeypatch.setattr(module, "_execute_script", fail_after_upgrade)
        with pytest.raises(RuntimeError):
            document_versions(db)
    else:
        assert queue(db, decision="accepted")[0]["id"] == 11
        assert document_versions(db)[0]["id"] == 7
        assert document_history(db, 7) == []
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == (2 if interrupt else 3)
        assert conn.execute("SELECT decision FROM review_events WHERE id=5").fetchone()[0] == "accepted"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        has_events = conn.execute("SELECT name FROM sqlite_master WHERE name='document_events'").fetchone()
        assert bool(has_events) == (not interrupt)


def test_failed_migration_rolls_back_schema_and_data(tmp_path, monkeypatch):
    from pharma_ocr_date_rag import review as module

    db = tmp_path / "rollback.sqlite"
    schema = (Path(__file__).parent / "fixtures" / "review_schema_v1.sql").read_text()
    with sqlite3.connect(db) as conn:
        conn.executescript(schema)
        conn.execute(
            "INSERT INTO documents VALUES(7,'demo','old.txt','abc','dates-v1','plain-text',1,'past')"
        )
        conn.execute("INSERT INTO date_hits VALUES(11,7,'2029-07','expiry','07/2029','EXP: 07/2029',0.9)")
        conn.execute("INSERT INTO review_events VALUES(5,11,'accepted','demo','Checked original','past')")
    execute = module._execute_script

    def fail_after_migration(connection, script):
        execute(connection, script)
        raise RuntimeError("Simulated interruption after schema changes")

    monkeypatch.setattr(module, "_execute_script", fail_after_migration)
    with pytest.raises(RuntimeError, match="Simulated interruption"):
        queue(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert len(conn.execute("PRAGMA table_info(date_hits)").fetchall()) == 7
        assert conn.execute("SELECT normalized FROM date_hits WHERE id=11").fetchone()[0] == "2029-07"
        assert conn.execute("SELECT decision FROM review_events WHERE id=5").fetchone()[0] == "accepted"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
