"""Test a trusted local wheel in a fresh, dependency-free environment outside the checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import tempfile
import venv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr[-2000:]}")
    return result.stdout


def exercise(python: Path, entrypoint: Path, cwd: Path) -> list[str]:
    """Run the installed entry point with isolated imports, not pytest's source path."""
    checks = []

    def cli(*args: str) -> object:
        return json.loads(run([str(python), "-I", str(entrypoint), *args], cwd))

    source = cwd / "sources"
    shutil.copytree(ROOT / "data/mixed_conventions", source)
    policy = str(source / "date_orders.json")
    rows = cli("extract", str(source), "--format", "json", "--date-order-map", policy)["dates"]
    require(len(rows) == 8, "Expected eight mixed-convention fields")
    require(sum(row["normalized"] is None for row in rows) == 1, "Unconfirmed date was resolved")
    expected = {"eu_receipt.txt": "2026-10-09", "us_receipt.txt": "2026-09-10"}
    for filename, value in expected.items():
        hit = next(row for row in rows if row["document"] == filename and row["label"] == "expiry")
        require(hit["normalized"] == value, f"Wrong date convention for {filename}")
    for row in rows:
        text = (source / row["document"]).read_text(encoding="utf-8")
        require(text[row["start"] : row["end"]] == row["raw_text"], "Source offsets changed")
    checks.append("mixed_conventions_and_source_spans")

    db = str(cwd / "reviews.sqlite")

    def review_cli(*args: str) -> object:
        return cli(*args, "--db", db)

    indexed = review_cli("index", str(source), "--date-order-map", policy, "--collection", "release")
    require(indexed["indexed"] == 3 and indexed["new_hits"] == 8, "Installed indexing failed")
    hits = review_cli("queue", "--decision", "all")
    hit = next(row for row in hits if row["path"] == "eu_receipt.txt" and row["label"] == "expiry")
    hit_id, document_id = str(hit["id"]), str(hit["document_id"])
    reviewer = ["--reviewer", "release-check", "--reason", "Synthetic release verification"]
    review_cli("review", hit_id, "--decision", "accepted", *reviewer)
    same = review_cli("index", str(source), "--date-order-map", policy, "--collection", "release")
    require(same["unchanged"] == 3, "Identical indexing changed document versions")
    require(len(review_cli("history", hit_id)) == 1, "Identical indexing changed review history")
    checks.append("idempotent_index_and_review")

    review_cli("document", "reopen", document_id, *reviewer)
    review_cli("document", "retire", document_id, *reviewer)
    retired = review_cli("index", str(source), "--date-order-map", policy, "--collection", "release")
    require(retired["retired_skipped"] == 1, "Indexing reactivated a retired source")
    require(len(review_cli("queue", "--decision", "all")) == 5, "Retired fields stayed active")
    restored = review_cli("document", "restore", document_id, *reviewer)
    require(restored["hits_reopened"] == 3, "Restoration did not require fresh review")
    history = review_cli("history", hit_id)
    require(
        [event["decision"] for event in history] == ["accepted", "needs_review", "needs_review"],
        "Review history was lost or rewritten",
    )
    events = review_cli("document-history", document_id)
    require(
        [event["action"] for event in events] == ["reopen", "retire", "restore"],
        "Document lifecycle history changed",
    )
    checks.append("reopen_retire_restore_history")

    for version in (1, 2):
        db = str(cwd / f"legacy-v{version}.sqlite")
        schema = ROOT / f"tests/fixtures/review_schema_v{version}.sql"
        with sqlite3.connect(db) as connection:
            connection.executescript(schema.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO documents VALUES(7,'legacy','old.txt','abc','old-parser','plain-text',1,'past')"
            )
            connection.execute(
                "INSERT INTO date_hits(id,document_id,normalized,label,extracted_text,context,heuristic_confidence) "
                "VALUES(11,7,'2029-07','expiry','07/2029','EXP: 07/2029',0.9)"
            )
            connection.execute(
                "INSERT INTO review_events VALUES(5,11,'accepted','demo','Original check','past')"
            )
        migrated = review_cli("queue", "--decision", "accepted")
        require(len(migrated) == 1 and migrated[0]["id"] == 11, "Migration changed the field ID")
        require(review_cli("history", "11")[0]["id"] == 5, "Migration changed review IDs")
        review_cli("document", "reopen", "7", *reviewer)
        with sqlite3.connect(db) as connection:
            require(connection.execute("PRAGMA user_version").fetchone()[0] == 3, "Schema did not reach v3")
            require(not connection.execute("PRAGMA foreign_key_check").fetchall(), "Foreign keys are invalid")
        require(len(review_cli("history", "11")) == 2, "Migrated review workflow failed")
        checks.append(f"schema_v{version}_upgrade_preserves_history")
    return checks


def verify(wheel: Path) -> dict:
    require(wheel.is_file() and wheel.suffix == ".whl", "Provide an existing trusted .whl file")
    report = {
        "schema_version": 1,
        "scope": "Installed dependency-free wheel smoke check; not model or OCR accuracy.",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "wheel": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__).resolve(),
                *sorted((ROOT / "data/mixed_conventions").glob("*")),
                *sorted((ROOT / "tests/fixtures").glob("review_schema_v*.sql")),
            ]
            if path.is_file()
        },
        "passed": False,
        "checks": [],
    }
    try:
        require(os.name != "nt", "This release verifier currently supports POSIX hosts only")
        with tempfile.TemporaryDirectory(prefix="pharma-wheel-") as temporary:
            cwd = Path(temporary)
            environment = cwd / "environment"
            venv.EnvBuilder(with_pip=True).create(environment)
            bin_dir = environment / "bin"
            python = bin_dir / "python"
            run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "--disable-pip-version-check",
                    "install",
                    "--no-index",
                    "--no-deps",
                    str(wheel.resolve()),
                ],
                cwd,
            )
            module_path = run(
                [str(python), "-I", "-c", "import pharma_ocr_date_rag; print(pharma_ocr_date_rag.__file__)"],
                cwd,
            ).strip()
            require(
                Path(module_path).resolve().is_relative_to(environment.resolve()),
                "Imported the checkout rather than the installed wheel",
            )
            entrypoint = bin_dir / "pharma-date-rag"
            require(entrypoint.is_file(), "Installed CLI entry point is missing")
            report["checks"] = ["isolated_install_and_entrypoint", *exercise(python, entrypoint, cwd)]
            report["passed"] = True
    except Exception as error:
        # Any failed step invalidates the release check, including malformed CLI JSON.
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/wheel-verification.json"))
    args = parser.parse_args()
    try:
        report = verify(args.wheel)
    except (ValueError, OSError) as error:
        report = {"schema_version": 1, "passed": False, "checks": [], "error": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
