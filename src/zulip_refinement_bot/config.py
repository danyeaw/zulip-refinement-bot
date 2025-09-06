"""Configuration management for the Zulip Refinement Bot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Configuration settings for the Zulip Refinement Bot."""

    # Zulip connection settings
    zulip_email: str = Field(..., env="ZULIP_EMAIL")
    zulip_api_key: str = Field(..., env="ZULIP_API_KEY")
    zulip_site: str = Field(..., env="ZULIP_SITE")

    # Bot configuration
    stream_name: str = Field(default="conda-maintainers", env="STREAM_NAME")
    default_deadline_hours: int = Field(default=48, env="DEFAULT_DEADLINE_HOURS")
    max_issues_per_batch: int = Field(default=6, env="MAX_ISSUES_PER_BATCH")
    max_title_length: int = Field(default=50, env="MAX_TITLE_LENGTH")

    # Voter list
    voter_list: list[str] = Field(
        default=[
            "jaimergp",
            "Jannis Leidel",
            "Sophia Castellarin",
            "Daniel Holth",
            "Ryan Keith",
            "Mahe Iyer",
            "Dan Yeaw",
        ],
        env="VOTER_LIST",
    )

    # Database settings
    database_path: Path = Field(
        default_factory=lambda: Path.cwd() / "data" / "refinement.db",
        env="DATABASE_PATH",
    )

    # GitHub API settings
    github_timeout: float = Field(default=10.0, env="GITHUB_TIMEOUT")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    def __init__(self, **kwargs: Any) -> None:
        """Initialize configuration and ensure database directory exists."""
        super().__init__(**kwargs)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
