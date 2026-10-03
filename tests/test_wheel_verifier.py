import importlib
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("verify_wheel")


def test_preconditions_do_not_depend_on_python_assertions(verifier):
    verifier.require(True, "not an error")
    with pytest.raises(ValueError, match="failure"):
        verifier.require(False, "failure")


def test_subprocesses_have_a_bound_and_fail_with_diagnostics(verifier, monkeypatch, tmp_path):
    calls = []

    def fail(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=2, stderr="missing schema.sql", stdout="")

    monkeypatch.setattr(verifier.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="missing schema.sql"):
        verifier.run(["python", "--version"], tmp_path)
    assert calls[0][1]["timeout"] == 120
    assert calls[0][1]["cwd"] == tmp_path


@pytest.mark.parametrize(
    "error", [RuntimeError("failed install"), KeyError("dates"), subprocess.TimeoutExpired("pip", 120)]
)
def test_failed_setup_never_becomes_a_passing_report(verifier, monkeypatch, tmp_path, error):
    wheel = tmp_path / "trusted-test.whl"
    wheel.write_bytes(b"test artifact, installer mocked")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(verifier.venv.EnvBuilder, "create", fail)
    report = verifier.verify(wheel)
    assert report["passed"] is False
    assert report["checks"] == []
    assert type(error).__name__ in report["error"]
    assert len(report["wheel_sha256"]) == 64


def test_source_checkout_import_is_rejected(verifier, monkeypatch, tmp_path):
    wheel = tmp_path / "trusted-test.whl"
    wheel.write_bytes(b"test artifact, installer mocked")
    calls = []
    monkeypatch.setattr(verifier.venv.EnvBuilder, "create", lambda *args: None)

    def fake_run(command, cwd):
        calls.append(command)
        return str(ROOT / "src/pharma_ocr_date_rag/__init__.py") if "-c" in command else ""

    monkeypatch.setattr(verifier, "run", fake_run)
    report = verifier.verify(wheel)
    assert not report["passed"]
    assert "checkout rather than" in report["error"]
    assert "--no-index" in calls[0] and "--no-deps" in calls[0] and "--isolated" in calls[0]
    assert all("-I" in command for command in calls)


def test_invalid_artifact_overwrites_stale_success_report(verifier, monkeypatch, tmp_path, capsys):
    output = tmp_path / "result.json"
    output.write_text('{"passed": true}')
    monkeypatch.setattr(
        sys, "argv", ["verify_wheel.py", str(tmp_path / "missing.whl"), "--output", str(output)]
    )
    with pytest.raises(SystemExit) as error:
        verifier.main()
    assert error.value.code == 1
    report = json.loads(output.read_text())
    assert report["passed"] is False
    assert report["checks"] == []
    assert "existing trusted" in report["error"]
    assert json.loads(capsys.readouterr().out) == report


def test_cleanup_failure_invalidates_an_otherwise_successful_run(verifier, monkeypatch, tmp_path):
    wheel = tmp_path / "trusted-test.whl"
    wheel.write_bytes(b"test artifact, installer mocked")
    environment = tmp_path / "environment"
    (environment / "bin").mkdir(parents=True)
    (environment / "bin/pharma-date-rag").write_text("mock entry point")

    @contextmanager
    def fail_cleanup(**kwargs):
        yield str(tmp_path)
        raise OSError("Cleanup failed")

    monkeypatch.setattr(verifier.tempfile, "TemporaryDirectory", fail_cleanup)
    monkeypatch.setattr(verifier.venv.EnvBuilder, "create", lambda *args: None)
    monkeypatch.setattr(verifier, "run", lambda *args: str(environment / "package/__init__.py"))
    monkeypatch.setattr(verifier, "exercise", lambda *args: ["completed_mock_checks"])
    report = verifier.verify(wheel)
    assert report["passed"] is False
    assert "Cleanup failed" in report["error"]
