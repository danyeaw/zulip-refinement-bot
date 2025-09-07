"""Tests for multi-voter add/remove functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zulip_refinement_bot.config import Config
from zulip_refinement_bot.database import DatabaseManager
from zulip_refinement_bot.handlers import MessageHandler
from zulip_refinement_bot.models import IssueData
from zulip_refinement_bot.services import BatchService, ResultsService, VotingService


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
def active_batch_with_voters(db_manager: DatabaseManager) -> int:
    """Create an active batch with some initial voters."""
    # Create batch
    batch_id: int = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

    # Add issues
    issues = [
        IssueData(issue_number="1234", title="Test Issue 1", url=""),
        IssueData(issue_number="1235", title="Test Issue 2", url=""),
    ]
    db_manager.add_issues_to_batch(batch_id, issues)

    # Add initial voters
    voters = ["Alice", "Bob"]
    db_manager.add_batch_voters(batch_id, voters)

    return batch_id


class TestVoterNameParsing:
    """Test voter name parsing functionality."""

    def test_parse_voter_names_single_name(self, message_handler: MessageHandler) -> None:
        """Test parsing a single voter name."""
        result = message_handler._parse_voter_names("John Doe")
        assert result == ["John Doe"]

    def test_parse_voter_names_comma_separated(self, message_handler: MessageHandler) -> None:
        """Test parsing comma-separated voter names."""
        result = message_handler._parse_voter_names("John Doe, Jane Smith, Bob Wilson")
        assert result == ["John Doe", "Jane Smith", "Bob Wilson"]

    def test_parse_voter_names_with_mentions(self, message_handler: MessageHandler) -> None:
        """Test parsing voter names with Zulip mentions."""
        result = message_handler._parse_voter_names("@**jdoe**, Jane Smith, @**bwilson**")
        assert result == ["jdoe", "Jane Smith", "bwilson"]

    def test_parse_voter_names_with_and(self, message_handler: MessageHandler) -> None:
        """Test parsing voter names connected with 'and'."""
        result = message_handler._parse_voter_names("John Doe and Jane Smith")
        assert result == ["John Doe", "Jane Smith"]

    def test_parse_voter_names_mixed_format(self, message_handler: MessageHandler) -> None:
        """Test parsing mixed format with commas, mentions, and 'and'."""
        result = message_handler._parse_voter_names("John Doe, @**jsmith** and Bob Wilson")
        assert result == ["John Doe", "jsmith", "Bob Wilson"]

    def test_parse_voter_names_with_duplicates(self, message_handler: MessageHandler) -> None:
        """Test parsing voter names with duplicates (should be removed)."""
        result = message_handler._parse_voter_names("John Doe, Jane Smith, John Doe")
        assert result == ["John Doe", "Jane Smith"]

    def test_parse_voter_names_empty_parts(self, message_handler: MessageHandler) -> None:
        """Test parsing voter names with empty parts."""
        result = message_handler._parse_voter_names("John Doe, , Jane Smith,")
        assert result == ["John Doe", "Jane Smith"]

    def test_parse_voter_names_case_insensitive_and(self, message_handler: MessageHandler) -> None:
        """Test parsing voter names with case-insensitive 'and'."""
        result = message_handler._parse_voter_names("John Doe AND Jane Smith")
        assert result == ["John Doe", "Jane Smith"]


class TestMultiVoterAdd:
    """Test multi-voter add functionality."""

    def test_add_single_voter_success(
        self,
        message_handler: MessageHandler,
        active_batch_with_voters: int,
        db_manager: DatabaseManager,
    ) -> None:
        """Test adding a single voter successfully."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply") as mock_reply,
            patch.object(message_handler, "_update_batch_message") as mock_update,
        ):
            message_handler.handle_add_voter(message, "add Charlie")

            # Verify voter was added
            voters = db_manager.get_batch_voters(active_batch_with_voters)
            assert "Charlie" in voters

            # Verify response
            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "✅ Added **Charlie**" in response
            assert f"batch {active_batch_with_voters}" in response

            # Verify batch message was updated
            mock_update.assert_called_once()

    def test_add_multiple_voters_success(
        self,
        message_handler: MessageHandler,
        active_batch_with_voters: int,
        db_manager: DatabaseManager,
    ) -> None:
        """Test adding multiple voters successfully."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply") as mock_reply,
            patch.object(message_handler, "_update_batch_message") as mock_update,
        ):
            message_handler.handle_add_voter(message, "add Charlie, David, Eve")

            # Verify voters were added
            voters = db_manager.get_batch_voters(active_batch_with_voters)
            assert "Charlie" in voters
            assert "David" in voters
            assert "Eve" in voters

            # Verify response
            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "✅ Added **Charlie**, **David**, **Eve**" in response

            # Verify batch message was updated
            mock_update.assert_called_once()

    def test_add_voters_with_mentions(
        self,
        message_handler: MessageHandler,
        active_batch_with_voters: int,
        db_manager: DatabaseManager,
    ) -> None:
        """Test adding voters with Zulip mention format."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply"),
            patch.object(message_handler, "_update_batch_message"),
        ):
            message_handler.handle_add_voter(message, "add @**charlie**, David and @**eve**")

            # Verify voters were added (mentions should be cleaned)
            voters = db_manager.get_batch_voters(active_batch_with_voters)
            assert "charlie" in voters
            assert "David" in voters
            assert "eve" in voters

    def test_add_voter_already_present(
        self, message_handler: MessageHandler, active_batch_with_voters: int
    ) -> None:
        """Test adding a voter who is already present."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply") as mock_reply,
            patch.object(message_handler, "_update_batch_message") as mock_update,
        ):
            message_handler.handle_add_voter(message, "add Alice")

            # Verify response
            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "ℹ️ **Alice** was already in batch" in response

            # Verify batch message was NOT updated (no changes)
            mock_update.assert_not_called()

    def test_add_voters_mixed_new_and_existing(
        self,
        message_handler: MessageHandler,
        active_batch_with_voters: int,
        db_manager: DatabaseManager,
    ) -> None:
        """Test adding a mix of new and existing voters."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply") as mock_reply,
            patch.object(message_handler, "_update_batch_message") as mock_update,
        ):
            message_handler.handle_add_voter(message, "add Alice, Charlie, Bob, David")

            # Verify new voters were added
            voters = db_manager.get_batch_voters(active_batch_with_voters)
            assert "Charlie" in voters
            assert "David" in voters

            # Verify response includes both added and already present
            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "✅ Added **Charlie**, **David**" in response
            assert "ℹ️ **Alice**, **Bob** were already in batch" in response

            # Verify batch message was updated (new voters added)
            mock_update.assert_called_once()

    def test_add_voter_no_active_batch(self, message_handler: MessageHandler) -> None:
        """Test adding voter when no active batch exists."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with patch.object(message_handler, "_send_reply") as mock_reply:
            message_handler.handle_add_voter(message, "add Charlie")

            mock_reply.assert_called_once_with(message, "❌ No active batch found.")

    def test_add_voter_no_names_provided(self, message_handler: MessageHandler) -> None:
        """Test adding voter with no names provided."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with patch.object(message_handler, "_send_reply") as mock_reply:
            message_handler.handle_add_voter(message, "add")

            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "❌ Please specify voter name(s)" in response
            assert "add John Doe" in response
            assert "add Alice and Bob" in response

    def test_add_voter_empty_names(self, message_handler: MessageHandler) -> None:
        """Test adding voter with empty names."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with patch.object(message_handler, "_send_reply") as mock_reply:
            message_handler.handle_add_voter(message, "add , ,")

            mock_reply.assert_called_once_with(message, "❌ No valid voter names found.")


class TestMultiVoterRemove:
    """Test multi-voter remove functionality."""

    def test_remove_single_voter_success(
        self,
        message_handler: MessageHandler,
        active_batch_with_voters: int,
        db_manager: DatabaseManager,
    ) -> None:
        """Test removing a single voter successfully."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply") as mock_reply,
            patch.object(message_handler, "_update_batch_message") as mock_update,
        ):
            message_handler.handle_remove_voter(message, "remove Alice")

            # Verify voter was removed
            voters = db_manager.get_batch_voters(active_batch_with_voters)
            assert "Alice" not in voters
            assert "Bob" in voters  # Should still be there

            # Verify response
            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "✅ Removed **Alice**" in response

            # Verify batch message was updated
            mock_update.assert_called_once()

    def test_remove_multiple_voters_success(
        self,
        message_handler: MessageHandler,
        active_batch_with_voters: int,
        db_manager: DatabaseManager,
    ) -> None:
        """Test removing multiple voters successfully."""
        # Add more voters first
        db_manager.add_voter_to_batch(active_batch_with_voters, "Charlie")
        db_manager.add_voter_to_batch(active_batch_with_voters, "David")

        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply") as mock_reply,
            patch.object(message_handler, "_update_batch_message") as mock_update,
        ):
            message_handler.handle_remove_voter(message, "remove Alice, Charlie, David")

            # Verify voters were removed
            voters = db_manager.get_batch_voters(active_batch_with_voters)
            assert "Alice" not in voters
            assert "Charlie" not in voters
            assert "David" not in voters
            assert "Bob" in voters  # Should still be there

            # Verify response
            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "✅ Removed **Alice**, **Charlie**, **David**" in response

            # Verify batch message was updated
            mock_update.assert_called_once()

    def test_remove_voter_not_present(
        self, message_handler: MessageHandler, active_batch_with_voters: int
    ) -> None:
        """Test removing a voter who is not present."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply") as mock_reply,
            patch.object(message_handler, "_update_batch_message") as mock_update,
        ):
            message_handler.handle_remove_voter(message, "remove Charlie")

            # Verify response
            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "ℹ️ **Charlie** was not in batch" in response

            # Verify batch message was NOT updated (no changes)
            mock_update.assert_not_called()

    def test_remove_voters_mixed_present_and_absent(
        self,
        message_handler: MessageHandler,
        active_batch_with_voters: int,
        db_manager: DatabaseManager,
    ) -> None:
        """Test removing a mix of present and absent voters."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with (
            patch.object(message_handler, "_send_reply") as mock_reply,
            patch.object(message_handler, "_update_batch_message") as mock_update,
        ):
            message_handler.handle_remove_voter(message, "remove Alice, Charlie, Bob, David")

            # Verify present voters were removed
            voters = db_manager.get_batch_voters(active_batch_with_voters)
            assert "Alice" not in voters
            assert "Bob" not in voters

            # Verify response includes both removed and not present
            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "✅ Removed **Alice**, **Bob**" in response
            assert "ℹ️ **Charlie**, **David** were not in batch" in response

            # Verify batch message was updated (voters removed)
            mock_update.assert_called_once()

    def test_remove_voter_no_active_batch(self, message_handler: MessageHandler) -> None:
        """Test removing voter when no active batch exists."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with patch.object(message_handler, "_send_reply") as mock_reply:
            message_handler.handle_remove_voter(message, "remove Alice")

            mock_reply.assert_called_once_with(message, "❌ No active batch found.")

    def test_remove_voter_no_names_provided(self, message_handler: MessageHandler) -> None:
        """Test removing voter with no names provided."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        with patch.object(message_handler, "_send_reply") as mock_reply:
            message_handler.handle_remove_voter(message, "remove")

            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "❌ Please specify voter name(s)" in response
            assert "remove John Doe" in response
            assert "remove Alice and Bob" in response


class TestMultiVoterIntegration:
    """Integration tests for multi-voter functionality."""

    def test_add_and_remove_voters_workflow(
        self,
        message_handler: MessageHandler,
        active_batch_with_voters: int,
        db_manager: DatabaseManager,
    ) -> None:
        """Test complete workflow of adding and removing multiple voters."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        # Initial state: Alice, Bob
        initial_voters = db_manager.get_batch_voters(active_batch_with_voters)
        assert set(initial_voters) == {"Alice", "Bob"}

        # Add multiple voters
        with (
            patch.object(message_handler, "_send_reply"),
            patch.object(message_handler, "_update_batch_message"),
        ):
            message_handler.handle_add_voter(message, "add Charlie, David and Eve")

        # Verify additions
        voters_after_add = db_manager.get_batch_voters(active_batch_with_voters)
        assert set(voters_after_add) == {"Alice", "Bob", "Charlie", "David", "Eve"}

        # Remove some voters
        with (
            patch.object(message_handler, "_send_reply"),
            patch.object(message_handler, "_update_batch_message"),
        ):
            message_handler.handle_remove_voter(message, "remove Alice, Charlie")

        # Verify removals
        final_voters = db_manager.get_batch_voters(active_batch_with_voters)
        assert set(final_voters) == {"Bob", "David", "Eve"}

    def test_error_handling_in_multi_voter_operations(
        self, message_handler: MessageHandler, active_batch_with_voters: int
    ) -> None:
        """Test error handling in multi-voter operations."""
        message = {"sender_full_name": "Test User", "sender_email": "test@example.com"}

        # Mock database error
        with (
            patch.object(
                message_handler.batch_service.database,
                "add_voter_to_batch",
                side_effect=Exception("DB Error"),
            ),
            patch.object(message_handler, "_send_reply") as mock_reply,
        ):
            message_handler.handle_add_voter(message, "add Charlie")

            mock_reply.assert_called_once()
            response = mock_reply.call_args[0][1]
            assert "❌ Error adding voter(s)" in response
