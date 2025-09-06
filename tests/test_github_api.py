"""Tests for GitHub API integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from zulip_refinement_bot.github_api import GitHubAPI


class TestGitHubAPI:
    """Test GitHub API integration."""

    def test_init(self):
        """Test GitHub API initialization."""
        api = GitHubAPI(timeout=5.0)
        assert api.timeout == 5.0

    @patch("zulip_refinement_bot.github_api.httpx.Client")
    def test_fetch_issue_title_success(self, mock_client_class: MagicMock):
        """Test successful issue title fetching."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"title": "Fix memory leak in solver"}
        mock_client.get.return_value = mock_response

        # Test
        api = GitHubAPI()
        title = api.fetch_issue_title("conda", "conda", "15169")

        # Verify
        assert title == "Fix memory leak in solver"
        mock_client.get.assert_called_once_with(
            "https://api.github.com/repos/conda/conda/issues/15169", timeout=10.0
        )

    @patch("zulip_refinement_bot.github_api.httpx.Client")
    def test_fetch_issue_title_not_found(self, mock_client_class: MagicMock):
        """Test issue not found (404)."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response

        # Test
        api = GitHubAPI()
        title = api.fetch_issue_title("conda", "conda", "99999")

        # Verify
        assert title is None

    @patch("zulip_refinement_bot.github_api.httpx.Client")
    def test_fetch_issue_title_api_error(self, mock_client_class: MagicMock):
        """Test API error (non-200, non-404 status)."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.get.return_value = mock_response

        # Test
        api = GitHubAPI()
        title = api.fetch_issue_title("conda", "conda", "15169")

        # Verify
        assert title is None

    @patch("zulip_refinement_bot.github_api.httpx.Client")
    def test_fetch_issue_title_network_error(self, mock_client_class: MagicMock):
        """Test network error handling."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("Network error")

        # Test
        api = GitHubAPI()
        title = api.fetch_issue_title("conda", "conda", "15169")

        # Verify
        assert title is None

    @patch("zulip_refinement_bot.github_api.httpx.Client")
    def test_fetch_issue_title_timeout(self, mock_client_class: MagicMock):
        """Test timeout handling."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        # Test
        api = GitHubAPI()
        title = api.fetch_issue_title("conda", "conda", "15169")

        # Verify
        assert title is None

    @patch("zulip_refinement_bot.github_api.httpx.Client")
    def test_fetch_issue_title_json_error(self, mock_client_class: MagicMock):
        """Test JSON parsing error."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.get.return_value = mock_response

        # Test
        api = GitHubAPI()
        title = api.fetch_issue_title("conda", "conda", "15169")

        # Verify
        assert title is None

    @patch("zulip_refinement_bot.github_api.httpx.Client")
    def test_fetch_issue_title_custom_timeout(self, mock_client_class: MagicMock):
        """Test custom timeout setting."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"title": "Test Issue"}
        mock_client.get.return_value = mock_response

        # Test
        api = GitHubAPI(timeout=5.0)
        title = api.fetch_issue_title("conda", "conda", "15169")

        # Verify
        assert title == "Test Issue"
        mock_client.get.assert_called_once_with(
            "https://api.github.com/repos/conda/conda/issues/15169", timeout=5.0
        )
