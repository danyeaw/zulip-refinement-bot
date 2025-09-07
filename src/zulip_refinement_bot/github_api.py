"""GitHub API integration for the Zulip Refinement Bot."""

from __future__ import annotations

import httpx
import structlog

from .interfaces import GitHubAPIInterface

logger = structlog.get_logger(__name__)


class GitHubAPI(GitHubAPIInterface):
    """Handles GitHub API interactions to fetch issue information."""

    def __init__(self, timeout: float = 10.0):
        """Initialize GitHub API client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    def fetch_issue_title(self, owner: str, repo: str, issue_number: str) -> str | None:
        """Fetch issue title from GitHub API.

        Args:
            owner: Repository owner (e.g., 'conda')
            repo: Repository name (e.g., 'conda')
            issue_number: Issue number as string

        Returns:
            Issue title if successful, None if failed
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"

        try:
            with httpx.Client() as client:
                response = client.get(url, timeout=self.timeout)

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
        except ValueError as e:
            logger.error(
                "JSON parsing error",
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                error=str(e),
            )
            return None

    async def fetch_issue_title_async(self, owner: str, repo: str, issue_number: str) -> str | None:
        """Async version of fetch_issue_title.

        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue number as string

        Returns:
            Issue title if successful, None if failed
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=self.timeout)

            if response.status_code == 200:
                issue_data = response.json()
                title = issue_data.get("title", "")
                if not isinstance(title, str):
                    logger.error(
                        "Invalid title type from GitHub API (async)", title_type=type(title)
                    )
                    return None
                logger.info(
                    "Successfully fetched issue title (async)",
                    owner=owner,
                    repo=repo,
                    issue_number=issue_number,
                    title=title[:50] + "..." if len(title) > 50 else title,
                )
                return title
            elif response.status_code == 404:
                logger.warning(
                    "Issue not found (async)", owner=owner, repo=repo, issue_number=issue_number
                )
                return None
            else:
                logger.error(
                    "GitHub API error (async)",
                    owner=owner,
                    repo=repo,
                    issue_number=issue_number,
                    status_code=response.status_code,
                )
                return None

        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.error(
                "Network error fetching issue (async)",
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                error=str(e),
            )
            return None
        except ValueError as e:
            logger.error(
                "JSON parsing error (async)",
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                error=str(e),
            )
            return None
