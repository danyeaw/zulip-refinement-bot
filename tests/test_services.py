"""Tests for service layer components."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zulip_refinement_bot.config import Config
from zulip_refinement_bot.exceptions import AuthorizationError, BatchError, ValidationError
from zulip_refinement_bot.models import BatchData, IssueData
from zulip_refinement_bot.services import BatchService, VotingService


class TestBatchService:
    """Tests for BatchService."""

    def test_create_batch_success(self, test_config: Config) -> None:
        """Test successful batch creation."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_github_api = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks
        mock_database.get_active_batch.return_value = None
        mock_parser.parse_batch_input.return_value = MagicMock(
            success=True,
            issues=[
                IssueData(
                    issue_number="1234",
                    title="Test Issue",
                    url="https://github.com/test/test/issues/1234",
                )
            ],
            error="",
        )
        mock_database.create_batch.return_value = 1
        mock_database.add_issues_to_batch.return_value = None

        # Create service
        service = BatchService(test_config, mock_database, mock_github_api, mock_parser)

        # Test batch creation
        batch_id, issues, deadline = service.create_batch(
            "start batch\nhttps://github.com/test/test/issues/1234", "facilitator"
        )

        # Assertions
        assert batch_id == 1
        assert len(issues) == 1
        assert issues[0].issue_number == "1234"
        mock_database.create_batch.assert_called_once()
        mock_database.add_issues_to_batch.assert_called_once()

    def test_create_batch_with_active_batch_fails(self, test_config: Config) -> None:
        """Test batch creation fails when there's already an active batch."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_github_api = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks
        mock_database.get_active_batch.return_value = BatchData(
            id=1, date="2024-01-01", deadline="2024-01-02T00:00:00", facilitator="someone"
        )

        # Create service
        service = BatchService(test_config, mock_database, mock_github_api, mock_parser)

        # Test batch creation fails
        with pytest.raises(BatchError, match="Active batch already running"):
            service.create_batch(
                "start batch\nhttps://github.com/test/test/issues/1234", "facilitator"
            )

    def test_cancel_batch_unauthorized(self, test_config: Config) -> None:
        """Test batch cancellation fails for unauthorized user."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_github_api = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks
        mock_database.get_active_batch.return_value = BatchData(
            id=1,
            date="2024-01-01",
            deadline="2024-01-02T00:00:00",
            facilitator="original_facilitator",
        )

        # Create service
        service = BatchService(test_config, mock_database, mock_github_api, mock_parser)

        # Test cancellation fails for wrong user
        with pytest.raises(AuthorizationError, match="Only the facilitator"):
            service.cancel_batch(1, "different_user")


class TestVotingService:
    """Tests for VotingService."""

    def test_submit_votes_unauthorized(self, test_config: Config) -> None:
        """Test vote submission fails for unauthorized voter."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_parser = MagicMock()

        # Create service
        service = VotingService(test_config, mock_database, mock_parser)

        # Create batch
        batch = BatchData(
            id=1, date="2024-01-01", deadline="2024-01-02T00:00:00", facilitator="facilitator"
        )

        # Test vote submission fails for unauthorized voter
        with pytest.raises(AuthorizationError, match="not authorized to vote"):
            service.submit_votes("#1234: 5", "unauthorized_voter", batch)

    def test_submit_votes_success(self, test_config: Config) -> None:
        """Test successful vote submission."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks
        mock_parser.parse_estimation_input.return_value = ({"1234": 5}, [])
        mock_database.upsert_vote.return_value = (True, False)
        mock_database.get_vote_count_by_voter.return_value = 1

        # Create service
        service = VotingService(test_config, mock_database, mock_parser)

        # Create batch with matching issue
        batch = BatchData(
            id=1,
            date="2024-01-01",
            deadline="2024-01-02T00:00:00",
            facilitator="facilitator",
            issues=[IssueData(issue_number="1234", title="Test Issue", url="")],
        )

        # Test vote submission
        estimates, has_updates, all_complete = service.submit_votes("#1234: 5", "voter1", batch)

        # Assertions
        assert estimates == {"1234": 5}
        assert not has_updates  # No updates since it was a new vote
        assert not all_complete  # Only 1 out of 3 voters
        mock_database.upsert_vote.assert_called_once_with(1, "voter1", "1234", 5)

    def test_submit_votes_validation_error(self, test_config: Config) -> None:
        """Test vote submission with validation errors."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks - return validation errors
        mock_parser.parse_estimation_input.return_value = (
            {},
            ["#1234: 4 (must be one of: 1, 2, 3, 5, 8, 13, 21)"],
        )

        # Create service
        service = VotingService(test_config, mock_database, mock_parser)

        # Create batch
        batch = BatchData(
            id=1, date="2024-01-01", deadline="2024-01-02T00:00:00", facilitator="facilitator"
        )

        # Test vote submission fails with validation error
        with pytest.raises(ValidationError, match="Invalid story point values"):
            service.submit_votes("#1234: 4", "voter1", batch)
