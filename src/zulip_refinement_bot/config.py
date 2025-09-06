"""Configuration management for the Zulip Refinement Bot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Configuration settings for the Zulip Refinement Bot."""

    # Zulip connection settings
    zulip_email: str
    zulip_api_key: str
    zulip_site: str

    # Bot configuration
    stream_name: str = "conda-maintainers"
    default_deadline_hours: int = 48
    max_issues_per_batch: int = 6
    max_title_length: int = 50

    default_list = [
        "jaimergp",
        "Jannis Leidel",
        "Sophia Castellarin",
        "Daniel Holth",
        "Ryan Keith",
        "Mahe Iyer",
        "Dan Yeaw",
    ]
    voter_list_str: str = ", ".join(default_list)

    # Database settings
    database_path: Path = Path.cwd() / "data" / "refinement.db"

    # GitHub API settings
    github_timeout: float = 10.0

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="",
    )

    @property
    def voter_list(self) -> list[str]:
        """Parse comma-separated voter list from environment variable."""
        return [voter.strip() for voter in self.voter_list_str.split(",") if voter.strip()]

    def __init__(self, **kwargs: Any) -> None:
        """Initialize configuration and ensure database directory exists."""
        super().__init__(**kwargs)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
