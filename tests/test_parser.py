"""Tests for input parsing and validation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zulip_refinement_bot.config import Config
from zulip_refinement_bot.github_api import GitHubAPI
from zulip_refinement_bot.parser import InputParser


@pytest.fixture
def mock_github_api() -> MagicMock:
    """Create a mock GitHub API."""
    mock_api = MagicMock(spec=GitHubAPI)
    return mock_api


@pytest.fixture
def parser(test_config: Config, mock_github_api: MagicMock) -> InputParser:
    """Create an input parser with mocked dependencies."""
    return InputParser(test_config, mock_github_api)


def test_input_parser_valid_single_issue(parser: InputParser, mock_github_api: MagicMock):
    """Test single GitHub URL parsing."""
    content = """start batch
https://github.com/conda/conda/issues/15169"""

    # No title fetching during parsing - titles fetched on-demand (BSSN)

    result = parser.parse_batch_input(content)

    assert result.success is True
    assert len(result.issues) == 1
    assert result.issues[0].issue_number == "15169"
    assert result.issues[0].url == "https://github.com/conda/conda/issues/15169"
    assert result.error == ""


def test_input_parser_valid_multiple_issues(parser: InputParser, mock_github_api: MagicMock):
    """Test multiple GitHub URLs parsing."""
    content = """start batch
https://github.com/conda/conda/issues/15169
https://github.com/conda/conda/issues/15168
https://github.com/conda/conda/issues/15167"""

    def mock_fetch_title(owner, repo, issue_number):
        titles = {
            "15169": "Fix memory leak in solver",
            "15168": "Improve dependency resolution",
            "15167": "Update documentation",
        }
        return titles.get(issue_number)

    # No title fetching during parsing - titles fetched on-demand (BSSN)

    result = parser.parse_batch_input(content)

    assert result.success is True
    assert len(result.issues) == 3
    assert result.issues[0].issue_number == "15169"
    assert result.issues[1].issue_number == "15168"
    assert result.issues[2].issue_number == "15167"


def test_input_parser_invalid_format(parser: InputParser):
    """Test invalid format (not a GitHub URL)."""
    content = "start batch\n#1234: Fix memory leak"  # Old manual format

    result = parser.parse_batch_input(content)

    assert result.success is False
    assert len(result.issues) == 0
    assert "Invalid format" in result.error
    assert "GitHub issue URLs" in result.error


def test_input_parser_duplicate_issue_numbers(parser: InputParser, mock_github_api: MagicMock):
    """Test duplicate issue numbers in GitHub URLs."""
    content = """start batch
https://github.com/conda/conda/issues/15169
https://github.com/conda/conda/issues/15169"""

    # No title fetching during parsing - titles fetched on-demand (BSSN)

    result = parser.parse_batch_input(content)

    assert result.success is False
    assert "Duplicate issue #15169" in result.error


def test_input_parser_too_many_issues(parser: InputParser, mock_github_api: MagicMock):
    """Test too many GitHub URLs."""
    # Create more issues than the limit (6 in test config)
    issues_list = [f"https://github.com/conda/conda/issues/{1000 + i}" for i in range(7)]
    content = "start batch\n" + "\n".join(issues_list)

    # No title fetching during parsing - titles fetched on-demand (BSSN)

    result = parser.parse_batch_input(content)

    assert result.success is False
    assert "Maximum 6 issues" in result.error


def test_input_parser_title_truncation(parser: InputParser, mock_github_api: MagicMock):
    """Test that titles are no longer truncated (BSSN: titles fetched on-demand)."""
    content = "start batch\nhttps://github.com/conda/conda/issues/15169"

    # No title fetching during parsing - titles fetched on-demand (BSSN)

    result = parser.parse_batch_input(content)

    assert result.success is True
    # BSSN: No title stored during parsing, titles fetched on-demand
    assert result.issues[0].issue_number == "15169"
    assert result.issues[0].url == "https://github.com/conda/conda/issues/15169"


def test_input_parser_empty_input(parser: InputParser):
    """Test empty input."""
    content = "start batch"

    result = parser.parse_batch_input(content)

    assert result.success is False
    assert "No GitHub issue URLs provided" in result.error


def test_input_parser_github_api_failure(parser: InputParser, mock_github_api: MagicMock):
    """Test GitHub URL parsing when API fails (BSSN: still succeeds, validation deferred)."""
    content = """start batch
https://github.com/conda/conda/issues/99999"""

    # No title fetching during parsing - titles fetched on-demand (BSSN)

    result = parser.parse_batch_input(content)

    # BSSN: Parser succeeds, title fetching happens on-demand
    assert result.success is True
    assert len(result.issues) == 1
    assert result.issues[0].issue_number == "99999"


def test_input_parser_parse_estimation_input_valid(parser: InputParser):
    """Test valid estimation input parsing."""
    content = "#1234: 5, #1235: 8, #1236: 3"

    estimates, validation_errors = parser.parse_estimation_input(content)

    assert estimates == {"1234": 5, "1235": 8, "1236": 3}
    assert validation_errors == []


def test_input_parser_parse_estimation_input_invalid_points(parser: InputParser):
    """Test estimation input with invalid story points."""
    content = "#1234: 4, #1235: 8, #1236: 15"  # 4 and 15 are not valid

    estimates, validation_errors = parser.parse_estimation_input(content)

    # Should only include valid points (8)
    assert estimates == {"1235": 8}
    # Should have validation errors for invalid points
    assert len(validation_errors) == 2
    assert "#1234: 4" in validation_errors[0]
    assert "#1236: 15" in validation_errors[1]


def test_input_parser_parse_estimation_input_mixed_format(parser: InputParser):
    """Test estimation input with mixed valid/invalid format."""
    content = "#1234: 5, invalid format, #1235: 8"

    estimates, validation_errors = parser.parse_estimation_input(content)

    assert estimates == {"1234": 5, "1235": 8}
    assert validation_errors == []  # Invalid format is ignored, not a validation error


def test_input_parser_parse_estimation_input_empty(parser: InputParser):
    """Test empty estimation input."""
    content = ""

    estimates, validation_errors = parser.parse_estimation_input(content)

    assert estimates == {}
    assert validation_errors == []


def test_input_parser_github_url_pattern_matching(parser: InputParser):
    """Test GitHub URL pattern matching."""
    # Valid URLs
    valid_urls = [
        "https://github.com/conda/conda/issues/15169",
        "https://github.com/user/repo/issues/1",
        "https://github.com/org-name/repo-name/issues/999999",
    ]

    for url in valid_urls:
        match = parser.GITHUB_URL_PATTERN.match(url)
        assert match is not None

    # Invalid URLs
    invalid_urls = [
        "http://github.com/conda/conda/issues/15169",  # http instead of https
        "https://github.com/conda/conda/pull/15169",  # pull request, not issue
        "https://gitlab.com/conda/conda/issues/15169",  # different domain
        "https://github.com/conda/conda/issues/",  # no issue number
        "github.com/conda/conda/issues/15169",  # no protocol
    ]

    for url in invalid_urls:
        match = parser.GITHUB_URL_PATTERN.match(url)
        assert match is None
