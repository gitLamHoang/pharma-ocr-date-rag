import json
import sys

import pytest

from pharma_ocr_date_rag.cli import main


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
