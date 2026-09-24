from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script,expected", [
    ("run_demo.py", "review: ambiguous_numeric_date"),
    ("evaluate.py", "matches:   18"),
    ("benchmark_multilingual.py", "all_languages: 42/42"),
])
def test_documented_scripts_run_outside_the_repository(script, expected, tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout
