"""Pytest configuration and fixtures."""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zulip_refinement_bot.config import Config
from zulip_refinement_bot.database import DatabaseManager
from zulip_refinement_bot.github_api import GitHubAPI


@pytest.fixture
def temp_db() -> Generator[Path, None, None]:
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def test_config(temp_db: Path) -> Config:
    """Create a test configuration."""
    return Config(
        zulip_email="test@example.com",
        zulip_api_key="test_api_key",
        zulip_site="https://test.zulipchat.com",
        database_path=temp_db,
        stream_name="test-stream",
        voter_list_str="voter1, voter2, voter3",
    )


@pytest.fixture
def db_manager(temp_db: Path) -> DatabaseManager:
    """Create a database manager with temporary database."""
    return DatabaseManager(temp_db)


@pytest.fixture
def github_api() -> GitHubAPI:
    """Create a GitHub API client."""
    return GitHubAPI(timeout=5.0)


@pytest.fixture
def mock_zulip_client() -> MagicMock:
    """Create a mock Zulip client."""
    mock_client = MagicMock()
    mock_client.send_message.return_value = {"result": "success"}
    return mock_client


@pytest.fixture
def sample_message() -> dict:
    """Create a sample Zulip message for testing."""
    return {
        "type": "private",
        "sender_email": "test@example.com",
        "sender_full_name": "Test User",
        "sender_id": "123",
        "content": "test message",
    }


@pytest.fixture
def sample_issues() -> list:
    """Create sample issue data for testing."""
    from zulip_refinement_bot.models import IssueData

    return [
        IssueData(
            issue_number="1234",
            title="Fix memory leak in solver",
            url="https://github.com/conda/conda/issues/1234",
        ),
        IssueData(
            issue_number="1235",
            title="Improve dependency resolution",
            url="https://github.com/conda/conda/issues/1235",
        ),
    ]
