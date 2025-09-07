"""Tests for discussion complete feature."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from zulip_refinement_bot.config import Config
from zulip_refinement_bot.database import DatabaseManager
from zulip_refinement_bot.exceptions import AuthorizationError, BatchError
from zulip_refinement_bot.handlers import MessageHandler
from zulip_refinement_bot.models import BatchData, EstimationVote, FinalEstimate, IssueData
from zulip_refinement_bot.services import BatchService, ResultsService, VotingService


# Global fixtures for all test classes
@pytest.fixture
def batch_service(test_config: Config, db_manager: DatabaseManager) -> BatchService:
    """Create a BatchService for testing."""
    mock_github_api = MagicMock()
    mock_parser = MagicMock()
    return BatchService(test_config, db_manager, mock_github_api, mock_parser)


@pytest.fixture
def voting_service(test_config: Config, db_manager: DatabaseManager) -> VotingService:
    """Create a VotingService for testing."""
    mock_parser = MagicMock()
    return VotingService(test_config, db_manager, mock_parser)


@pytest.fixture
def results_service(test_config: Config) -> ResultsService:
    """Create a ResultsService for testing."""
    return ResultsService(test_config)


@pytest.fixture
def message_handler(
    test_config: Config,
    batch_service: BatchService,
    voting_service: VotingService,
    results_service: ResultsService,
) -> MessageHandler:
    """Create a MessageHandler for testing."""
    mock_zulip_client = MagicMock()
    return MessageHandler(
        test_config, mock_zulip_client, batch_service, voting_service, results_service
    )


@pytest.fixture
def active_batch_discussing(db_manager: DatabaseManager) -> BatchData:
    """Create an active batch in discussing state."""
    # Create batch
    batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

    # Add issues
    issues = [
        IssueData(issue_number="1234", title="Test Issue 1", url=""),
        IssueData(issue_number="1235", title="Test Issue 2", url=""),
    ]
    db_manager.add_issues_to_batch(batch_id, issues)

    # Add voters
    voters = ["Alice", "Bob", "Charlie"]
    db_manager.add_batch_voters(batch_id, voters)

    # Set to discussing state
    db_manager.set_batch_discussing(batch_id)

    # Return the batch data
    batch = db_manager.get_active_batch()
    assert batch is not None
    return batch


class TestDiscussionCompleteFeature:
    """Test the discussion complete feature end-to-end."""


class TestBatchServiceDiscussion:
    """Test BatchService discussion phase methods."""

    def test_start_discussion_phase_success(self, test_config: Config) -> None:
        """Test successfully starting discussion phase."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_github_api = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks
        active_batch = BatchData(
            id=1,
            date="2024-01-01",
            deadline="2024-01-02T00:00:00",
            facilitator="facilitator",
            status="active",
        )
        mock_database.get_active_batch.return_value = active_batch

        # Create service
        service = BatchService(test_config, mock_database, mock_github_api, mock_parser)

        # Test starting discussion phase
        result_batch = service.start_discussion_phase(1, "facilitator")

        # Assertions
        assert result_batch.status == "discussing"
        mock_database.set_batch_discussing.assert_called_once_with(1)

    def test_start_discussion_phase_unauthorized(self, test_config: Config) -> None:
        """Test starting discussion phase fails for unauthorized user."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_github_api = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks
        active_batch = BatchData(
            id=1,
            date="2024-01-01",
            deadline="2024-01-02T00:00:00",
            facilitator="original_facilitator",
            status="active",
        )
        mock_database.get_active_batch.return_value = active_batch

        # Create service
        service = BatchService(test_config, mock_database, mock_github_api, mock_parser)

        # Test starting discussion phase fails for wrong user
        with pytest.raises(AuthorizationError, match="Only the facilitator"):
            service.start_discussion_phase(1, "different_user")

    def test_complete_discussion_phase_success(self, test_config: Config) -> None:
        """Test successfully completing discussion phase."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_github_api = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks
        active_batch = BatchData(
            id=1,
            date="2024-01-01",
            deadline="2024-01-02T00:00:00",
            facilitator="facilitator",
            status="discussing",
        )
        mock_database.get_active_batch.return_value = active_batch

        # Create service
        service = BatchService(test_config, mock_database, mock_github_api, mock_parser)

        # Test completing discussion phase
        final_estimates = {"1234": (5, "After discussion"), "1235": (8, "Agreed complexity")}
        result_batch = service.complete_discussion_phase(1, "facilitator", final_estimates)

        # Assertions
        assert result_batch.status == "completed"
        mock_database.store_final_estimate.assert_any_call(1, "1234", 5, "After discussion")
        mock_database.store_final_estimate.assert_any_call(1, "1235", 8, "Agreed complexity")
        mock_database.complete_batch.assert_called_once_with(1)

    def test_complete_discussion_phase_wrong_status(self, test_config: Config) -> None:
        """Test completing discussion phase fails when batch is not in discussing state."""
        # Mock dependencies
        mock_database = MagicMock()
        mock_github_api = MagicMock()
        mock_parser = MagicMock()

        # Setup mocks
        active_batch = BatchData(
            id=1,
            date="2024-01-01",
            deadline="2024-01-02T00:00:00",
            facilitator="facilitator",
            status="active",  # Wrong status
        )
        mock_database.get_active_batch.return_value = active_batch

        # Create service
        service = BatchService(test_config, mock_database, mock_github_api, mock_parser)

        # Test completing discussion phase fails
        with pytest.raises(BatchError, match="Batch is not in discussion phase"):
            service.complete_discussion_phase(1, "facilitator", {})


class TestMessageHandlerDiscussion:
    """Test MessageHandler discussion complete functionality."""

    def test_parse_discussion_complete_input_success(self, message_handler: MessageHandler) -> None:
        """Test parsing discussion complete input successfully."""
        content = (
            "discussion complete #1234: 5 After discussion we agreed, "
            "#1235: 8 More complex than expected"
        )

        result = message_handler._parse_discussion_complete_input(content)

        expected = {
            "1234": (5, "After discussion we agreed"),
            "1235": (8, "More complex than expected"),
        }
        assert result == expected

    def test_parse_discussion_complete_input_invalid_points(
        self, message_handler: MessageHandler
    ) -> None:
        """Test parsing discussion complete input with invalid story points."""
        content = "discussion complete #1234: 4 Invalid points, #1235: 8 Valid points"

        result = message_handler._parse_discussion_complete_input(content)

        # Should only include valid points
        expected = {"1235": (8, "Valid points")}
        assert result == expected

    def test_parse_discussion_complete_input_empty(self, message_handler: MessageHandler) -> None:
        """Test parsing empty discussion complete input."""
        content = "discussion complete"

        result = message_handler._parse_discussion_complete_input(content)

        assert result == {}

    def test_handle_discussion_complete_success(
        self, message_handler: MessageHandler, active_batch_discussing: BatchData
    ) -> None:
        """Test handling discussion complete command successfully."""
        # Mock message
        message = {
            "sender_full_name": "Test User",
            "sender_email": "test@example.com",
        }

        # Mock the parsing and completion
        with (
            patch.object(message_handler, "_parse_discussion_complete_input") as mock_parse,
            patch.object(message_handler, "_post_discussion_complete_results") as mock_post,
        ):
            mock_parse.return_value = {"1234": (5, "After discussion")}

            # Test handling
            message_handler.handle_discussion_complete(
                message, "discussion complete #1234: 5 After discussion"
            )

            # Verify methods were called
            mock_parse.assert_called_once()
            mock_post.assert_called_once()

    def test_handle_discussion_complete_no_active_batch(
        self, message_handler: MessageHandler
    ) -> None:
        """Test handling discussion complete when no active batch exists."""
        message = {
            "sender_full_name": "Test User",
            "sender_email": "test@example.com",
        }

        # Mock no active batch and _send_reply to capture the response
        with (
            patch.object(message_handler.batch_service, "get_active_batch", return_value=None),
            patch.object(message_handler, "_send_reply") as mock_reply,
        ):
            message_handler.handle_discussion_complete(message, "discussion complete #1234: 5")

            mock_reply.assert_called_once_with(message, "❌ No active batch found.")

    def test_handle_discussion_complete_wrong_status(
        self, message_handler: MessageHandler, db_manager: DatabaseManager
    ) -> None:
        """Test handling discussion complete when batch is not in discussing state."""
        # Create active batch (not in discussing state)
        db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")
        # Don't set to discussing state

        message = {
            "sender_full_name": "Test User",
            "sender_email": "test@example.com",
        }

        # Mock _send_reply to capture the response
        with patch.object(message_handler, "_send_reply") as mock_reply:
            message_handler.handle_discussion_complete(message, "discussion complete #1234: 5")

            # Should get error about wrong status
            mock_reply.assert_called_once()
            args = mock_reply.call_args[0]
            assert "not in discussion phase" in args[1]


class TestResultsServiceDiscussion:
    """Test ResultsService discussion complete functionality."""

    def test_generate_discussion_complete_results(self, results_service: ResultsService) -> None:
        """Test generating discussion complete results."""
        # Create test data
        batch = BatchData(
            id=1,
            date="2024-03-25",
            deadline="2024-03-27T14:00:00+00:00",
            facilitator="Test User",
            issues=[
                IssueData(issue_number="1234", title="Test Issue 1", url=""),
                IssueData(issue_number="1235", title="Test Issue 2", url=""),
            ],
        )

        consensus_estimates = {"1234": 5}  # Issue 1234 had consensus
        final_estimates = [
            FinalEstimate(
                issue_number="1235",
                final_points=8,
                rationale="After discussion we agreed it's more complex",
                timestamp=datetime.now(),
            )
        ]

        # Generate results
        results = results_service.generate_discussion_complete_results(
            batch, consensus_estimates, final_estimates
        )

        # Verify content
        assert "🎯 **ESTIMATION UPDATE - DISCUSSION COMPLETE**" in results
        assert "**✅ FINAL ESTIMATES**" in results
        assert "**Issue 1234** - Test Issue 1: **5 points**" in results
        assert "**Issue 1235** - Test Issue 2: **8 points**" in results
        assert "After discussion we agreed it's more complex" in results
        assert "**📝 ACTIONS**" in results
        assert "**🙏 THANKS**" in results

    def test_generate_results_content_with_discussion_needed(
        self, results_service: ResultsService
    ) -> None:
        """Test that results content includes discussion instructions when needed."""
        # Create test data with wide spread votes (will need discussion)
        batch = BatchData(
            id=1,
            date="2024-03-25",
            deadline="2024-03-27T14:00:00+00:00",
            facilitator="Test User",
            issues=[
                IssueData(issue_number="1234", title="Test Issue 1", url=""),
            ],
        )

        # Create votes with wide spread
        votes = [
            EstimationVote(voter="Alice", issue_number="1234", points=1),
            EstimationVote(voter="Bob", issue_number="1234", points=13),
            EstimationVote(voter="Charlie", issue_number="1234", points=21),
        ]

        batch_voters = ["Alice", "Bob", "Charlie"]

        # Generate results
        results = results_service.generate_results_content(batch, votes, 3, 3, batch_voters)

        # Verify discussion instructions are included
        assert "⚠️ **DISCUSSION NEEDED**" in results
        assert "**🗣️ NEXT STEPS**" in results
        assert "discussion complete" in results
        assert "Example:" in results


class TestDatabaseDiscussion:
    """Test database methods for discussion complete feature."""

    def test_set_batch_discussing(self, db_manager: DatabaseManager) -> None:
        """Test setting batch to discussing status."""
        # Create batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Set to discussing
        db_manager.set_batch_discussing(batch_id)

        # Verify status
        batch = db_manager.get_active_batch()
        assert batch is not None
        assert batch.status == "discussing"

    def test_store_and_get_final_estimates(self, db_manager: DatabaseManager) -> None:
        """Test storing and retrieving final estimates."""
        # Create batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Store final estimates
        db_manager.store_final_estimate(batch_id, "1234", 5, "After discussion")
        db_manager.store_final_estimate(batch_id, "1235", 8, "More complex than expected")

        # Retrieve final estimates
        estimates = db_manager.get_final_estimates(batch_id)

        assert len(estimates) == 2
        estimates_dict = {est.issue_number: est for est in estimates}

        assert estimates_dict["1234"].final_points == 5
        assert estimates_dict["1234"].rationale == "After discussion"
        assert estimates_dict["1235"].final_points == 8
        assert estimates_dict["1235"].rationale == "More complex than expected"

    def test_store_final_estimate_update(self, db_manager: DatabaseManager) -> None:
        """Test updating a final estimate."""
        # Create batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Store initial estimate
        db_manager.store_final_estimate(batch_id, "1234", 5, "Initial decision")

        # Update estimate
        db_manager.store_final_estimate(batch_id, "1234", 8, "Changed after more discussion")

        # Retrieve estimates
        estimates = db_manager.get_final_estimates(batch_id)

        assert len(estimates) == 1
        assert estimates[0].issue_number == "1234"
        assert estimates[0].final_points == 8
        assert estimates[0].rationale == "Changed after more discussion"


class TestDiscussionCompleteIntegration:
    """Integration tests for the complete discussion workflow."""

    def test_batch_completion_triggers_discussion_phase(
        self,
        message_handler: MessageHandler,
        db_manager: DatabaseManager,
    ) -> None:
        """Test that batch completion automatically triggers discussion phase when needed."""
        # Create batch with issues
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")
        issues = [IssueData(issue_number="1234", title="Test Issue", url="")]
        db_manager.add_issues_to_batch(batch_id, issues)
        db_manager.add_batch_voters(batch_id, ["Alice", "Bob", "Charlie"])

        # Add votes with wide spread (will trigger discussion)
        db_manager.upsert_vote(batch_id, "Alice", "1234", 1)
        db_manager.upsert_vote(batch_id, "Bob", "1234", 13)
        db_manager.upsert_vote(batch_id, "Charlie", "1234", 21)

        batch = db_manager.get_active_batch()
        assert batch is not None

        # Mock the results service to return discussion needed content
        with patch.object(
            message_handler.results_service, "generate_results_content"
        ) as mock_generate:
            mock_generate.return_value = "⚠️ **DISCUSSION NEEDED** Some content here"

            # Process batch completion
            message_handler._process_batch_completion(batch, auto_completed=True)

            # Verify batch is now in discussing state
            updated_batch = db_manager.get_active_batch()
            assert updated_batch is not None
            assert updated_batch.status == "discussing"

    def test_full_discussion_workflow(
        self,
        message_handler: MessageHandler,
        active_batch_discussing: BatchData,
    ) -> None:
        """Test the complete discussion workflow from start to finish."""
        message = {
            "sender_full_name": "Test User",
            "sender_email": "test@example.com",
        }

        # Mock the necessary methods
        with (
            patch.object(message_handler, "_post_discussion_complete_results") as mock_post,
            patch.object(message_handler, "_send_reply") as mock_reply,
        ):
            # Handle discussion complete
            message_handler.handle_discussion_complete(
                message, "discussion complete #1234: 5 After discussion, #1235: 8 More complex"
            )

            # Verify completion was processed
            mock_post.assert_called_once()
            mock_reply.assert_called_once_with(
                message,
                "✅ Discussion phase completed successfully. Final results posted to the stream.",
            )

            # Verify batch is now completed
            batch = message_handler.batch_service.get_active_batch()
            # Should be None since batch is completed
            assert batch is None or batch.status == "completed"
