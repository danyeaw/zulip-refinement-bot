"""Tests for finish feature."""

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
def batch_service(
    test_config: Config, db_manager: DatabaseManager, mock_github_api: MagicMock
) -> BatchService:
    """Create a BatchService for testing."""
    mock_parser = MagicMock()
    return BatchService(test_config, db_manager, mock_github_api, mock_parser)


@pytest.fixture
def voting_service(test_config: Config, db_manager: DatabaseManager) -> VotingService:
    """Create a VotingService for testing."""
    mock_parser = MagicMock()
    return VotingService(test_config, db_manager, mock_parser)


@pytest.fixture
def results_service(
    test_config: Config, mock_github_api: MagicMock, batch_service: BatchService
) -> ResultsService:
    """Create a ResultsService for testing."""
    return ResultsService(test_config, mock_github_api, batch_service)


@pytest.fixture
def message_handler(
    test_config: Config,
    batch_service: BatchService,
    voting_service: VotingService,
    results_service: ResultsService,
    mock_github_api: MagicMock,
) -> MessageHandler:
    """Create a MessageHandler for testing."""
    mock_zulip_client = MagicMock()
    return MessageHandler(
        test_config,
        mock_zulip_client,
        batch_service,
        voting_service,
        results_service,
        mock_github_api,
    )


@pytest.fixture
def active_batch_discussing(db_manager: DatabaseManager) -> BatchData:
    """Create an active batch in discussing state."""
    # Create batch
    batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

    # Add issues
    issues = [
        IssueData(issue_number="1234", url="https://github.com/test/repo/issues/1234"),
        IssueData(issue_number="1235", url="https://github.com/test/repo/issues/1235"),
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


def test_batch_service_start_discussion_phase_success(test_config: Config) -> None:
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


def test_batch_service_start_discussion_phase_unauthorized(test_config: Config) -> None:
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


def test_batch_service_complete_discussion_phase_success(test_config: Config) -> None:
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


def test_batch_service_complete_discussion_phase_wrong_status(test_config: Config) -> None:
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


def test_message_handler_parse_finish_input_success(
    message_handler: MessageHandler,
) -> None:
    """Test parsing finish input successfully."""
    content = "finish #1234: 5 After discussion we agreed, #1235: 8 More complex than expected"

    result = message_handler._parse_finish_input(content)

    expected = {
        "1234": (5, "After discussion we agreed"),
        "1235": (8, "More complex than expected"),
    }
    assert result == expected


def test_message_handler_parse_finish_input_invalid_points(
    message_handler: MessageHandler,
) -> None:
    """Test parsing finish input with invalid story points."""
    content = "finish #1234: 4 Invalid points, #1235: 8 Valid points"

    result = message_handler._parse_finish_input(content)

    # Should only include valid points
    expected = {"1235": (8, "Valid points")}
    assert result == expected


def test_message_handler_parse_finish_input_empty(
    message_handler: MessageHandler,
) -> None:
    """Test parsing empty finish input."""
    content = "finish"

    result = message_handler._parse_finish_input(content)

    assert result == {}


def test_message_handler_handle_discussion_complete_success(
    message_handler: MessageHandler, active_batch_discussing: BatchData
) -> None:
    """Test handling finish command successfully."""
    # Mock message
    message = {
        "sender_full_name": "Test User",
        "sender_email": "test@example.com",
    }

    # Mock the parsing and completion (only finishing 1 of 2 issues)
    with (
        patch.object(message_handler, "_parse_finish_input") as mock_parse,
        patch.object(message_handler, "_post_updated_estimation_results") as mock_post_updated,
        patch.object(message_handler, "_send_reply") as mock_reply,
    ):
        mock_parse.return_value = {"1234": (5, "After discussion")}

        # Test handling
        message_handler.handle_finish(message, "finish #1234: 5 After discussion")

        # Verify methods were called
        mock_parse.assert_called_once()
        mock_post_updated.assert_called_once()  # Should post updated results, not complete
        mock_reply.assert_called_once()  # Should reply saying item completed


def test_message_handler_handle_discussion_complete_no_active_batch(
    message_handler: MessageHandler,
) -> None:
    """Test handling finish when no active batch exists."""
    message = {
        "sender_full_name": "Test User",
        "sender_email": "test@example.com",
    }

    # Mock no active batch and _send_reply to capture the response
    with (
        patch.object(message_handler.batch_service, "get_active_batch", return_value=None),
        patch.object(message_handler, "_send_reply") as mock_reply,
    ):
        message_handler.handle_finish(message, "finish #1234: 5")

        mock_reply.assert_called_once_with(message, "❌ No active batch found.")


def test_message_handler_handle_discussion_complete_wrong_status(
    message_handler: MessageHandler, db_manager: DatabaseManager
) -> None:
    """Test handling finish when batch is not in discussing state."""
    # Create active batch (not in discussing state)
    db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")
    # Don't set to discussing state

    message = {
        "sender_full_name": "Test User",
        "sender_email": "test@example.com",
    }

    # Mock _send_reply to capture the response
    with patch.object(message_handler, "_send_reply") as mock_reply:
        message_handler.handle_finish(message, "finish #1234: 5")

        # Should get error about wrong status
        mock_reply.assert_called_once()
        args = mock_reply.call_args[0]
        assert "not in discussion phase" in args[1]


def test_results_service_generate_discussion_complete_results(
    results_service: ResultsService,
    mock_github_api: MagicMock,
) -> None:
    """Test generating finish results."""

    # Configure mock to return expected titles
    def mock_fetch_title(url: str) -> str:
        if "1234" in url:
            return "Test Issue 1"
        elif "1235" in url:
            return "Test Issue 2"
        return "Unknown Issue"

    mock_github_api.fetch_issue_title_by_url.side_effect = mock_fetch_title

    # Create test data
    batch = BatchData(
        id=1,
        date="2024-03-25",
        deadline="2024-03-27T14:00:00+00:00",
        facilitator="Test User",
        issues=[
            IssueData(issue_number="1234", url="https://github.com/test/repo/issues/1234"),
            IssueData(issue_number="1235", url="https://github.com/test/repo/issues/1235"),
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
    results = results_service.generate_finish_results(batch, consensus_estimates, final_estimates)

    # Verify content
    assert "🎯 **ESTIMATION UPDATE - DISCUSSION COMPLETE**" in results
    assert "**✅ FINAL ESTIMATES**" in results
    assert "**Issue 1234** - Test Issue 1: **5 points**" in results
    assert "**Issue 1235** - Test Issue 2: **8 points**" in results
    assert "After discussion we agreed it's more complex" in results
    assert "**📝 ACTIONS**" in results
    assert "**🙏 THANKS**" in results


def test_results_service_generate_results_content_with_discussion_needed(
    results_service: ResultsService,
    mock_github_api: MagicMock,
) -> None:
    """Test that results content includes discussion instructions when needed."""
    # Configure mock to return expected title
    mock_github_api.fetch_issue_title_by_url.return_value = "Test Issue 1"

    # Create test data with wide spread votes (will need discussion)
    batch = BatchData(
        id=1,
        date="2024-03-25",
        deadline="2024-03-27T14:00:00+00:00",
        facilitator="Test User",
        issues=[
            IssueData(issue_number="1234", url="https://github.com/test/repo/issues/1234"),
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
    assert "finish" in results
    assert "Example:" in results


def test_database_set_batch_discussing(db_manager: DatabaseManager) -> None:
    """Test setting batch to discussing status."""
    # Create batch
    batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

    # Set to discussing
    db_manager.set_batch_discussing(batch_id)

    # Verify status
    batch = db_manager.get_active_batch()
    assert batch is not None
    assert batch.status == "discussing"


def test_database_store_and_get_final_estimates(db_manager: DatabaseManager) -> None:
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


def test_database_store_final_estimate_update(db_manager: DatabaseManager) -> None:
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


def test_discussion_complete_integration_batch_completion_triggers_discussion_phase(
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
    with patch.object(message_handler.results_service, "generate_results_content") as mock_generate:
        mock_generate.return_value = "⚠️ **DISCUSSION NEEDED** Some content here"

        # Process batch completion
        message_handler._process_batch_completion(batch, auto_completed=True)

        # Verify batch is now in discussing state
        updated_batch = db_manager.get_active_batch()
        assert updated_batch is not None
        assert updated_batch.status == "discussing"


def test_discussion_complete_integration_full_discussion_workflow(
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
        patch.object(message_handler, "_post_finish_results") as mock_post,
        patch.object(message_handler, "_send_reply") as mock_reply,
    ):
        # Handle finish
        message_handler.handle_finish(
            message, "finish #1234: 5 After discussion, #1235: 8 More complex"
        )

        # Verify completion was processed
        mock_post.assert_called_once()
        mock_reply.assert_called_once_with(
            message,
            "✅ All discussion items completed! Final results posted to the stream.",
        )

        # Verify batch is now completed
        batch = message_handler.batch_service.get_active_batch()
        # Should be None since batch is completed
        assert batch is None or batch.status == "completed"


def test_auto_finish_when_consensus_reached(
    message_handler: MessageHandler,
    db_manager: DatabaseManager,
) -> None:
    """Test that finish is automatically triggered when consensus is reached during estimation."""
    batch = BatchData(
        id=1,
        date="2024-03-25",
        deadline="2024-03-27T14:00:00+00:00",
        facilitator="Test User",
        issues=[
            IssueData(issue_number="1234", title="Test Issue 1", url=""),
            IssueData(issue_number="1235", title="Test Issue 2", url=""),
        ],
        status="voting",
        message_id=123,
    )

    batch_id = db_manager.create_batch(batch.date, batch.deadline, batch.facilitator)
    batch.id = batch_id

    db_manager.add_issues_to_batch(batch_id, batch.issues)
    db_manager.add_batch_voters(batch_id, ["voter1", "voter2", "voter3"])

    db_manager.upsert_vote(batch_id, "voter1", "1234", 5)
    db_manager.upsert_vote(batch_id, "voter1", "1235", 8)
    db_manager.upsert_vote(batch_id, "voter2", "1234", 5)
    db_manager.upsert_vote(batch_id, "voter2", "1235", 8)
    db_manager.upsert_vote(batch_id, "voter3", "1234", 5)
    db_manager.upsert_vote(batch_id, "voter3", "1235", 8)

    with (
        patch.object(message_handler, "_update_batch_completion_status") as mock_update,
        patch.object(message_handler, "_post_finish_results") as mock_post_finish,
        patch.object(message_handler, "_post_estimation_results") as mock_post_estimation,
    ):
        message_handler._process_batch_completion(batch, auto_completed=True)

        mock_post_finish.assert_called_once()
        mock_post_estimation.assert_not_called()
        mock_update.assert_called_once()

        updated_batch = message_handler.batch_service.get_active_batch()
        assert updated_batch is None or updated_batch.status == "completed"

        final_estimates = db_manager.get_final_estimates(batch_id)
        assert len(final_estimates) == 2

        estimates_dict = {est.issue_number: est.final_points for est in final_estimates}
        assert estimates_dict["1234"] == 5
        assert estimates_dict["1235"] == 8

        for est in final_estimates:
            assert "Consensus reached during initial voting" in est.rationale


def test_no_auto_finish_when_discussion_needed(
    message_handler: MessageHandler,
    db_manager: DatabaseManager,
) -> None:
    """Test that finish is NOT automatically triggered when discussion is needed."""
    batch = BatchData(
        id=1,
        date="2024-03-25",
        deadline="2024-03-27T14:00:00+00:00",
        facilitator="Test User",
        issues=[
            IssueData(issue_number="1234", title="Test Issue 1", url=""),
            IssueData(issue_number="1235", title="Test Issue 2", url=""),
        ],
        status="voting",
        message_id=123,
    )

    batch_id = db_manager.create_batch(batch.date, batch.deadline, batch.facilitator)
    batch.id = batch_id

    db_manager.add_issues_to_batch(batch_id, batch.issues)
    db_manager.add_batch_voters(batch_id, ["voter1", "voter2", "voter3"])

    db_manager.upsert_vote(batch_id, "voter1", "1234", 3)
    db_manager.upsert_vote(batch_id, "voter1", "1235", 8)
    db_manager.upsert_vote(batch_id, "voter2", "1234", 5)
    db_manager.upsert_vote(batch_id, "voter2", "1235", 8)
    db_manager.upsert_vote(batch_id, "voter3", "1234", 8)
    db_manager.upsert_vote(batch_id, "voter3", "1235", 8)

    with (
        patch.object(message_handler, "_update_batch_discussion_status") as mock_discussion_update,
        patch.object(message_handler, "_post_finish_results") as mock_post_finish,
        patch.object(message_handler, "_post_estimation_results") as mock_post_estimation,
    ):
        message_handler._process_batch_completion(batch, auto_completed=True)

        mock_post_estimation.assert_called_once()
        mock_post_finish.assert_not_called()
        mock_discussion_update.assert_called_once()

        updated_batch = message_handler.batch_service.get_active_batch()
        assert updated_batch is not None
        assert updated_batch.status == "discussing"

        final_estimates = db_manager.get_final_estimates(batch_id)
        assert len(final_estimates) == 0
