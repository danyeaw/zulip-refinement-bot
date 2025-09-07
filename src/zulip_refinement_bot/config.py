"""Configuration management for the Zulip Refinement Bot."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field, computed_field
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

    # Holiday configuration
    holiday_country: str = "US"
    custom_holidays: str = ""

    _default_voters: ClassVar[list[str]] = [
        "jaimergp",
        "Jannis Leidel",
        "Sophia Castellarin",
        "Daniel Holth",
        "Ryan Keith",
        "Mahe Iyer",
        "Dan Yeaw",
    ]

    voter_list_str: str = Field(default_factory=lambda: ",".join(Config._default_voters))

    # Database settings
    database_path: Path = Field(default_factory=lambda: Path.cwd() / "data" / "refinement.db")

    # GitHub API settings
    github_timeout: float = 10.0

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @computed_field  # type: ignore[misc]
    def voter_list(self) -> list[str]:
        """Parse comma-separated voter list from environment variable."""
        return [voter.strip() for voter in self.voter_list_str.split(",") if voter.strip()]

    @computed_field  # type: ignore[misc]
    def custom_holiday_dates(self) -> list[str]:
        """Parse comma-separated custom holiday dates."""
        if not self.custom_holidays.strip():
            return []
        return [date.strip() for date in self.custom_holidays.split(",") if date.strip()]

    def __init__(self, **kwargs: Any) -> None:
        """Initialize configuration and ensure database directory exists."""
        super().__init__(**kwargs)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
