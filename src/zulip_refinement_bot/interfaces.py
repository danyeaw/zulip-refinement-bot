"""Abstract interfaces for the Zulip Refinement Bot."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import BatchData, EstimationVote, FinalEstimate, IssueData, ParseResult


class GitHubAPIInterface(ABC):
    """Interface for GitHub API operations."""

    @abstractmethod
    def parse_github_url(self, url: str) -> tuple[str, str, str] | None: ...

    @abstractmethod
    def fetch_issue_title_by_url(self, url: str) -> str | None: ...


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
    def get_completed_voters_count(self, batch_id: int) -> int: ...

    @abstractmethod
    def has_voter_voted(self, batch_id: int, voter: str) -> bool: ...

    @abstractmethod
    def update_batch_message_id(self, batch_id: int, message_id: int) -> None: ...

    @abstractmethod
    def update_batch_results_message_id(self, batch_id: int, results_message_id: int) -> None: ...

    @abstractmethod
    def add_batch_voters(self, batch_id: int, voters: list[str]) -> None: ...

    @abstractmethod
    def get_batch_voters(self, batch_id: int) -> list[str]: ...

    @abstractmethod
    def add_voter_to_batch(self, batch_id: int, voter: str) -> bool: ...

    @abstractmethod
    def remove_voter_from_batch(self, batch_id: int, voter: str) -> bool: ...

    @abstractmethod
    def set_batch_discussing(self, batch_id: int) -> None: ...

    @abstractmethod
    def store_final_estimate(
        self, batch_id: int, issue_number: str, final_points: int, rationale: str
    ) -> None: ...

    @abstractmethod
    def get_final_estimates(self, batch_id: int) -> list[FinalEstimate]: ...

    @abstractmethod
    def upsert_abstention(
        self, batch_id: int, voter: str, issue_number: str
    ) -> tuple[bool, bool]: ...

    @abstractmethod
    def get_voter_abstentions(self, batch_id: int, voter: str) -> list[str]: ...

    @abstractmethod
    def has_reminder_been_sent(self, batch_id: int, reminder_type: str) -> bool: ...

    @abstractmethod
    def record_reminder_sent(self, batch_id: int, reminder_type: str) -> None: ...

    @abstractmethod
    def get_voters_without_votes(self, batch_id: int) -> list[str]: ...

    @abstractmethod
    def has_voter_abstained(self, batch_id: int, voter: str, issue_number: str) -> bool: ...

    @abstractmethod
    def remove_vote_if_exists(self, batch_id: int, voter: str, issue_number: str) -> bool: ...

    @abstractmethod
    def remove_abstention_if_exists(self, batch_id: int, voter: str, issue_number: str) -> bool: ...


class ParserInterface(ABC):
    """Interface for input parsing operations."""

    @abstractmethod
    def parse_batch_input(self, content: str) -> ParseResult: ...

    @abstractmethod
    def parse_estimation_input(
        self, content: str
    ) -> tuple[dict[str, int], list[str], list[str]]: ...


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

    @abstractmethod
    def handle_list_voters(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    def handle_add_voter(self, message: dict[str, Any], content: str) -> None: ...

    @abstractmethod
    def handle_remove_voter(self, message: dict[str, Any], content: str) -> None: ...

    @abstractmethod
    def handle_finish(self, message: dict[str, Any], content: str) -> None: ...

    @abstractmethod
    def is_proxy_vote_format(self, content: str) -> bool: ...

    @abstractmethod
    def handle_proxy_vote(self, message: dict[str, Any], content: str) -> None: ...
