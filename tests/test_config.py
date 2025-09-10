"""Tests for configuration management."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from zulip_refinement_bot.config import Config


def test_config_with_env_vars(monkeypatch):
    """Test configuration loading from environment variables."""
    monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
    monkeypatch.setenv("ZULIP_API_KEY", "test_key")
    monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
    monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")
    monkeypatch.setenv("STREAM_NAME", "custom-stream")
    monkeypatch.setenv("DEFAULT_DEADLINE_HOURS", "72")

    config = Config()

    assert config.zulip_email == "test@example.com"
    assert config.zulip_api_key == "test_key"
    assert config.zulip_site == "https://test.zulipchat.com"
    assert config.zulip_token == "test_webhook_token"
    assert config.stream_name == "custom-stream"
    assert config.default_deadline_hours == 72


def test_config_defaults():
    """Test default configuration values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(
            zulip_email="test@example.com",
            zulip_api_key="test_key",
            zulip_site="https://test.zulipchat.com",
            zulip_token="test_token",
            database_path=Path(tmpdir) / "test.db",
        )

        assert config.stream_name == "conda-maintainers"
        assert config.default_deadline_hours == 48
        assert config.max_issues_per_batch == 6
        assert config.max_title_length == 50
        assert config.github_timeout == 10.0
        assert config.log_level == "INFO"
        assert config.log_format == "json"


def test_config_default_voters():
    """Test that default voters are available."""
    expected_voters = [
        "Dan Yeaw",
        "Daniel Holth",
        "Jannis Leidel",
        "Ken Odegard",
        "Mahe Iram Khan",
        "Ryan Keith",
        "Sophia Castellarin",
        "Travis Hathaway",
        "jaimergp",
    ]

    assert Config._default_voters == expected_voters


def test_config_database_path_creation():
    """Test that database directory is created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "subdir" / "test.db"

        config = Config(
            zulip_email="test@example.com",
            zulip_api_key="test_key",
            zulip_site="https://test.zulipchat.com",
            zulip_token="test_token",
            database_path=db_path,
        )

        assert config.database_path.parent.exists()


def test_config_from_env_file():
    """Test configuration loading from .env file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("ZULIP_EMAIL=env@example.com\n")
        f.write("ZULIP_API_KEY=env_key\n")
        f.write("ZULIP_SITE=https://env.zulipchat.com\n")
        f.write("ZULIP_TOKEN=env_token\n")
        f.write("STREAM_NAME=env-stream\n")
        env_file = f.name

    try:
        config = Config(_env_file=env_file)

        assert config.zulip_email == "env@example.com"
        assert config.zulip_api_key == "env_key"
        assert config.zulip_site == "https://env.zulipchat.com"
        assert config.zulip_token == "env_token"
        assert config.stream_name == "env-stream"
    finally:
        os.unlink(env_file)


def test_config_token_required():
    """Test that zulip_token is a required field."""
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # This should raise a validation error since zulip_token is required
            Config(
                zulip_email="test@example.com",
                zulip_api_key="test_key",
                zulip_site="https://test.zulipchat.com",
                database_path=Path(tmpdir) / "test.db",
            )
            # If we get here, the test should fail
            assert False, "Expected validation error for missing zulip_token"
        except Exception as e:
            # Should get a validation error for missing required field
            assert "zulip_token" in str(e).lower() or "field required" in str(e).lower()


def test_config_token_from_env():
    """Test that zulip_token can be loaded from environment variable."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("ZULIP_EMAIL=env@example.com\n")
        f.write("ZULIP_API_KEY=env_key\n")
        f.write("ZULIP_SITE=https://env.zulipchat.com\n")
        f.write("ZULIP_TOKEN=secret_webhook_token\n")
        env_file = f.name

    try:
        config = Config(_env_file=env_file)
        assert config.zulip_token == "secret_webhook_token"
    finally:
        os.unlink(env_file)
