"""Settings from environment variables and the git-ignored `.env` at the repo root."""

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    ai_enabled: bool = True
    claude_provider: Literal["anthropic", "bedrock", "vertex"] = "anthropic"
    claude_model: str = "claude-opus-5-5"
    data_dir: Path = Path("data")
    max_upload_mb: int = 50
    max_pages: int = 100
    render_dpi: int = 200
    ai_concurrency: int = 4
    tesseract_langs: str = "eng+fra+deu+spa+vie+ara+rus+chi_sim+jpn"


@cache
def get_settings() -> Settings:
    return Settings()
