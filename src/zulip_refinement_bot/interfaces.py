"""Abstract interfaces for the Zulip Refinement Bot."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import BatchData, EstimationVote, IssueData, ParseResult


class GitHubAPIInterface(ABC):
    """Interface for GitHub API operations."""

    @abstractmethod
    def fetch_issue_title(self, owner: str, repo: str, issue_number: str) -> str | None:
        """Fetch issue title from GitHub API."""

    @abstractmethod
    async def fetch_issue_title_async(self, owner: str, repo: str, issue_number: str) -> str | None:
        """Async version of fetch_issue_title."""


class DatabaseInterface(ABC):
    """Interface for database operations."""

    @abstractmethod
    def get_active_batch(self) -> BatchData | None: ...

    @abstractmethod
    def create_batch(self, date: str, deadline: str, facilitator: str) -> int: ...

    @abstractmethod
    def add_issues_to_batch(self, batch_id: int, issues: list[IssueData]) -> None: ...

    @abstractmethod
    def cancel_batch(self, batch_id: int) -> None: ...

    @abstractmethod
    def complete_batch(self, batch_id: int) -> None: ...

    @abstractmethod
    def upsert_vote(
        self, batch_id: int, voter: str, issue_number: str, points: int
    ) -> tuple[bool, bool]: ...

    @abstractmethod
    def get_batch_votes(self, batch_id: int) -> list[EstimationVote]: ...

    @abstractmethod
    def get_vote_count_by_voter(self, batch_id: int) -> int: ...

    @abstractmethod
    def update_batch_message_id(self, batch_id: int, message_id: int) -> None: ...


class ParserInterface(ABC):
    """Interface for input parsing operations."""

    @abstractmethod
    def parse_batch_input(self, content: str) -> ParseResult: ...

    @abstractmethod
    def parse_estimation_input(self, content: str) -> tuple[dict[str, int], list[str]]: ...


class ZulipClientInterface(ABC):
    """Interface for Zulip client operations."""

    @abstractmethod
    def send_message(self, message_data: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def update_message(self, message_data: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def call_on_each_message(self, handler: Any) -> None: ...


class MessageHandlerInterface(ABC):
    """Interface for message handling operations."""

    @abstractmethod
    def handle_start_batch(self, message: dict[str, Any], content: str) -> None: ...

    @abstractmethod
    def handle_status(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    def handle_cancel(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    def handle_complete(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    def handle_vote_submission(self, message: dict[str, Any], content: str) -> None: ...

    @abstractmethod
    def is_vote_format(self, content: str) -> bool: ...

    @abstractmethod
    def _process_batch_completion(self, batch: Any, auto_completed: bool = False) -> None: ...
