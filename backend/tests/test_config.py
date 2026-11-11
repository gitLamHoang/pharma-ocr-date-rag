from pathlib import Path

import pytest
from pydantic import ValidationError

from pharma_dates.config import Settings, get_settings

ENV_VARS = (
    "AI_ENABLED",
    "CLAUDE_PROVIDER",
    "CLAUDE_MODEL",
    "DATA_DIR",
    "MAX_UPLOAD_MB",
    "MAX_PAGES",
    "RENDER_DPI",
    "AI_CONCURRENCY",
    "TESSERACT_LANGS",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "AWS_REGION",
    "VERTEX_PROJECT_ID",
    "VERTEX_REGION",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_match_the_spec():
    settings = Settings(_env_file=None)
    assert settings.ai_enabled is True
    assert settings.claude_provider == "anthropic"
    assert settings.claude_model == "claude-opus-5-5"
    assert settings.data_dir == Path("data")
    assert settings.max_upload_mb == 50
    assert settings.max_pages == 100
    assert settings.render_dpi == 200
    assert settings.ai_concurrency == 4
    assert settings.tesseract_langs == "eng"


def test_environment_overrides_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("CLAUDE_PROVIDER", "bedrock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_PAGES", "7")
    settings = Settings(_env_file=None)
    assert settings.ai_enabled is False
    assert settings.claude_provider == "bedrock"
    assert settings.data_dir == tmp_path
    assert settings.max_pages == 7


def test_env_file_is_read_and_unknown_keys_are_ignored(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(["CLAUDE_PROVIDER=vertex", "VERTEX_REGION=us-east5", ""]))
    assert Settings(_env_file=env_file).claude_provider == "vertex"


def test_provider_credentials_from_environment_are_hidden(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")  # pragma: allowlist secret
    monkeypatch.setenv("VERTEX_PROJECT_ID", "demo-project")
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key.get_secret_value() == "test-not-a-key"  # pragma: allowlist secret
    assert "test-not-a-key" not in repr(settings)
    assert settings.anthropic_auth_token is None
    assert settings.vertex_project_id == "demo-project"
    assert settings.vertex_region == "global"
    assert settings.aws_region is None


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("CLAUDE_PROVIDER", "openai")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_empty_values_from_a_copied_env_example_keep_the_defaults(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text((Path(__file__).resolve().parents[2] / ".env.example").read_text())
    settings = Settings(_env_file=env_file)
    assert settings.vertex_region == "global"
    assert settings.aws_region is None
    assert settings.vertex_project_id is None
    assert settings.anthropic_api_key is None
