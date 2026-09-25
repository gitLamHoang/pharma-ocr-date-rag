import json
import sys
from pathlib import Path

import pytest

from pharma_ocr_date_rag.cli import main

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "mixed_conventions"


def test_review_cli_round_trip(tmp_path, capsys, monkeypatch):
    folder = tmp_path / "source"
    folder.mkdir()
    (folder / "coa.txt").write_text("Expiry: 2027-06-30")
    db = str(tmp_path / "review.sqlite")

    def command(*args):
        monkeypatch.setattr(sys, "argv", ["pharma-date-rag", *args, "--db", db])
        main()
        return json.loads(capsys.readouterr().out)

    assert command("index", str(folder), "--collection", "demo")["indexed"] == 1
    hit = command("queue", "--label", "expiry")[0]
    event = command(
        "review", str(hit["id"]), "--decision", "accepted", "--reviewer", "demo", "--reason", "Checked source"
    )
    assert event["decision"] == "accepted"
    assert command("queue") == []
    assert command("history", str(hit["id"])) == [event]
    assert command("index", str(folder), "--collection", "demo")["unchanged"] == 1


def test_cli_database_failure_has_actionable_error(tmp_path, capsys, monkeypatch):
    db = tmp_path / "corrupt.sqlite"
    db.write_text("This is not a SQLite database")
    monkeypatch.setattr(sys, "argv", ["pharma-date-rag", "queue", "--db", str(db)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "not a database" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["extract", "ask", "index"])
def test_document_policies_are_shared_by_all_folder_commands(command, tmp_path, capsys, monkeypatch):
    args = [command, str(FIXTURES), "--date-order-map", str(FIXTURES / "date_orders.json")]
    if command == "extract":
        args += ["--format", "json", "--date-order", "mdy"]
    elif command == "ask":
        args += ["--question", "expiry"]
    else:
        args += ["--db", str(tmp_path / "reviews.sqlite")]
    monkeypatch.setattr(sys, "argv", ["pharma-date-rag", *args])
    main()
    output = capsys.readouterr().out
    if command == "extract":
        rows = json.loads(output)["dates"]
        assert len(rows) == 8
        assert next(row for row in rows if row["document"] == "eu_receipt.txt")["normalized"] == "2026-10-09"
        assert next(row for row in rows if row["document"] == "unconfirmed_receipt.txt")["normalized"] is None
    elif command == "ask":
        assert "2026-10-09 (expiry)" in output
        assert "2026-09-10 (expiry)" in output
        assert "ambiguous: 2026-09-10 or 2026-10-09" in output
    else:
        assert json.loads(output)["new_hits"] == 8


@pytest.mark.parametrize("content", ['{"typo.txt":"mdy"}', '{"eu_receipt.txt":"DMY"}', "not json"])
def test_cli_invalid_policy_is_an_actionable_usage_error(content, tmp_path, capsys, monkeypatch):
    path = tmp_path / "orders.json"
    path.write_text(content)
    monkeypatch.setattr(
        sys, "argv", ["pharma-date-rag", "extract", str(FIXTURES), "--date-order-map", str(path)]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "Traceback" not in captured.err
    assert not captured.out
