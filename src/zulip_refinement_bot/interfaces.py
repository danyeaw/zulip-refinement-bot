"""Abstract interfaces for the Zulip Refinement Bot."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import BatchData, EstimationVote, IssueData, ParseResult


class GitHubAPIInterface(ABC):
    """Abstract interface for GitHub API operations."""

    @abstractmethod
    def fetch_issue_title(self, owner: str, repo: str, issue_number: str) -> str | None:
        """Fetch issue title from GitHub API.

        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue number

        Returns:
            Issue title if successful, None if failed
        """

    @abstractmethod
    async def fetch_issue_title_async(self, owner: str, repo: str, issue_number: str) -> str | None:
        """Async version of fetch_issue_title.

        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue number

        Returns:
            Issue title if successful, None if failed
        """


class DatabaseInterface(ABC):
    """Abstract interface for database operations."""

    @abstractmethod
    def get_active_batch(self) -> BatchData | None:
        """Get the currently active batch."""

    @abstractmethod
    def create_batch(self, date: str, deadline: str, facilitator: str) -> int:
        """Create a new batch and return its ID."""

    @abstractmethod
    def add_issues_to_batch(self, batch_id: int, issues: list[IssueData]) -> None:
        """Add issues to a batch."""

    @abstractmethod
    def cancel_batch(self, batch_id: int) -> None:
        """Cancel an active batch."""

    @abstractmethod
    def complete_batch(self, batch_id: int) -> None:
        """Mark a batch as completed."""

    @abstractmethod
    def upsert_vote(
        self, batch_id: int, voter: str, issue_number: str, points: int
    ) -> tuple[bool, bool]:
        """Store or update a vote."""

    @abstractmethod
    def get_batch_votes(self, batch_id: int) -> list[EstimationVote]:
        """Get all votes for a batch."""

    @abstractmethod
    def get_vote_count_by_voter(self, batch_id: int) -> int:
        """Get the number of unique voters for a batch."""

    @abstractmethod
    def update_batch_message_id(self, batch_id: int, message_id: int) -> None:
        """Update the message ID for a batch."""


class ParserInterface(ABC):
    """Abstract interface for input parsing operations."""

    @abstractmethod
    def parse_batch_input(self, content: str) -> ParseResult:
        """Parse batch input and return validation results."""

    @abstractmethod
    def parse_estimation_input(self, content: str) -> tuple[dict[str, int], list[str]]:
        """Parse story point estimation input."""


class ZulipClientInterface(ABC):
    """Abstract interface for Zulip client operations."""

    @abstractmethod
    def send_message(self, message_data: dict[str, Any]) -> dict[str, Any]:
        """Send a message via Zulip API."""

    @abstractmethod
    def update_message(self, message_data: dict[str, Any]) -> dict[str, Any]:
        """Update a message via Zulip API."""

    @abstractmethod
    def call_on_each_message(self, handler: Any) -> None:
        """Register message handler and start listening."""


class MessageHandlerInterface(ABC):
    """Abstract interface for message handling operations."""

    @abstractmethod
    def handle_start_batch(self, message: dict[str, Any], content: str) -> None:
        """Handle batch creation request."""

    @abstractmethod
    def handle_status(self, message: dict[str, Any]) -> None:
        """Handle status request."""

    @abstractmethod
    def handle_cancel(self, message: dict[str, Any]) -> None:
        """Handle batch cancellation request."""

    @abstractmethod
    def handle_complete(self, message: dict[str, Any]) -> None:
        """Handle batch completion request."""

    @abstractmethod
    def handle_vote_submission(self, message: dict[str, Any], content: str) -> None:
        """Handle vote submission from a user."""

    @abstractmethod
    def is_vote_format(self, content: str) -> bool:
        """Check if content looks like a vote submission."""

    @abstractmethod
    def _process_batch_completion(self, batch: Any, auto_completed: bool = False) -> None:
        """Process completion of a batch."""
