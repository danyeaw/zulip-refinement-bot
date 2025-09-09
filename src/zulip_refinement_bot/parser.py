"""Input parsing and validation for the Zulip Refinement Bot."""

from __future__ import annotations

import re

import structlog

from .config import Config
from .github_api import GitHubAPI
from .interfaces import ParserInterface
from .models import IssueData, ParseResult

logger = structlog.get_logger(__name__)


class InputParser(ParserInterface):
    """Handles parsing and validation of user input."""

    GITHUB_URL_PATTERN = re.compile(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)")

    def __init__(self, config: Config, github_api: GitHubAPI):
        """Initialize input parser.

        Args:
            config: Bot configuration
            github_api: GitHub API client
        """
        self.config = config
        self.github_api = github_api

    def parse_batch_input(self, content: str) -> ParseResult:
        """Parse batch input and return validation results.

        Only supports GitHub URL format:
        - https://github.com/owner/repo/issues/1234

        Args:
            content: Raw message content to parse

        Returns:
            ParseResult with success status, issues list, and error message
        """
        lines = [line.strip() for line in content.split("\n") if line.strip()]

        # Remove the command line
        if lines and lines[0].lower().startswith("start"):
            lines = lines[1:]

        if not lines:
            error_msg = (
                "❌ No GitHub issue URLs provided. "
                "Please provide GitHub issue URLs like: "
                "https://github.com/conda/conda/issues/15169"
            )
            logger.warning("Empty batch input")
            return ParseResult(success=False, issues=[], error=error_msg)

        issues: list[IssueData] = []
        seen_numbers: set[str] = set()

        for line in lines:
            github_match = self.GITHUB_URL_PATTERN.match(line)
            if github_match:
                owner, repo, issue_number = github_match.groups()

                if issue_number in seen_numbers:
                    error_msg = f"❌ Duplicate issue #{issue_number} found"
                    logger.warning("Duplicate issue number", issue_number=issue_number)
                    return ParseResult(success=False, issues=[], error=error_msg)

                seen_numbers.add(issue_number)
                issues.append(IssueData(issue_number=issue_number, url=line))
                continue

            error_msg = (
                f"❌ Invalid format: '{line}'. "
                "Please use GitHub issue URLs like: "
                "https://github.com/conda/conda/issues/15169"
            )
            logger.warning("Invalid URL format", line=line)
            return ParseResult(success=False, issues=[], error=error_msg)

        if len(issues) > self.config.max_issues_per_batch:
            error_msg = (
                f"❌ Maximum {self.config.max_issues_per_batch} issues per batch "
                f"(you provided {len(issues)})"
            )
            logger.warning(
                "Too many issues in batch",
                issue_count=len(issues),
                max_allowed=self.config.max_issues_per_batch,
            )
            return ParseResult(success=False, issues=[], error=error_msg)

        logger.info("Successfully parsed batch input", issue_count=len(issues))
        return ParseResult(success=True, issues=issues, error="")

    def parse_estimation_input(self, content: str) -> tuple[dict[str, int], list[str]]:
        """Parse story point estimation input.

        Expected format: "#1234: 5, #1235: 8, #1236: 3"

        Args:
            content: Raw estimation input

        Returns:
            Tuple of (valid estimates dict, list of validation errors)
        """
        estimates = {}
        validation_errors = []
        valid_fibonacci = [1, 2, 3, 5, 8, 13, 21]

        processed_content = content.strip()
        if (
            processed_content.startswith("`")
            and processed_content.endswith("`")
            and len(processed_content) > 1
        ):
            processed_content = processed_content[1:-1].strip()

        pattern = re.compile(r"#(\d+):\s*(\d+)")

        for match in pattern.finditer(processed_content):
            issue_number = match.group(1)
            points = int(match.group(2))

            if points not in valid_fibonacci:
                validation_errors.append(
                    f"#{issue_number}: {points} "
                    f"(must be one of: {', '.join(map(str, valid_fibonacci))})"
                )
                logger.warning(
                    "Invalid story points value - must use Fibonacci sequence",
                    issue_number=issue_number,
                    points=points,
                    valid_fibonacci=valid_fibonacci,
                )
                continue

            estimates[issue_number] = points

        logger.info(
            "Parsed estimation input", estimates=estimates, validation_errors=validation_errors
        )
        return estimates, validation_errors
