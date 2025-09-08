"""GitHub API integration for the Zulip Refinement Bot."""

from __future__ import annotations

import re

import httpx
import structlog

from .interfaces import GitHubAPIInterface

logger = structlog.get_logger(__name__)


class GitHubAPI(GitHubAPIInterface):
    """Handles GitHub API interactions to fetch issue information."""

    GITHUB_URL_PATTERN = re.compile(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)")

    def __init__(self, timeout: float = 10.0):
        """Initialize GitHub API client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    def parse_github_url(self, url: str) -> tuple[str, str, str] | None:
        """Parse GitHub issue URL to extract owner, repo, and issue number.

        Args:
            url: GitHub issue URL

        Returns:
            Tuple of (owner, repo, issue_number) or None if invalid
        """
        match = self.GITHUB_URL_PATTERN.match(url)
        if match:
            groups = match.groups()
            return (groups[0], groups[1], groups[2])
        return None

    def fetch_issue_title_by_url(self, url: str) -> str | None:
        """Fetch issue title from GitHub URL.

        Args:
            url: GitHub issue URL

        Returns:
            Issue title if successful, None if failed
        """
        parsed = self.parse_github_url(url)
        if not parsed:
            logger.error("Invalid GitHub URL format", url=url)
            return None

        owner, repo, issue_number = parsed
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"

        try:
            with httpx.Client() as client:
                response = client.get(api_url, timeout=self.timeout)

            if response.status_code == 200:
                issue_data = response.json()
                title = issue_data.get("title", "")
                if not isinstance(title, str):
                    logger.error("Invalid title type from GitHub API", title_type=type(title))
                    return None
                logger.info(
                    "Successfully fetched issue title",
                    owner=owner,
                    repo=repo,
                    issue_number=issue_number,
                    title=title[:50] + "..." if len(title) > 50 else title,
                )
                return title
            elif response.status_code == 404:
                logger.warning("Issue not found", owner=owner, repo=repo, issue_number=issue_number)
                return None
            else:
                logger.error(
                    "GitHub API error",
                    owner=owner,
                    repo=repo,
                    issue_number=issue_number,
                    status_code=response.status_code,
                )
                return None

        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.error(
                "Network error fetching issue",
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                error=str(e),
            )
            return None
        except (KeyError, ValueError) as e:
            logger.error(
                "Error parsing GitHub response",
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                error=str(e),
            )
            return None
