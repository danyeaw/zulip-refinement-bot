"""Tests for per-batch voter storage functionality."""

from __future__ import annotations

from zulip_refinement_bot.database import DatabaseManager
from zulip_refinement_bot.models import IssueData


class TestBatchVoters:
    """Test per-batch voter storage functionality."""

    def test_add_batch_voters(self, db_manager: DatabaseManager):
        """Test adding voters to a batch."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add voters to the batch
        voters = ["Alice", "Bob", "Charlie"]
        db_manager.add_batch_voters(batch_id, voters)

        # Retrieve voters
        retrieved_voters = db_manager.get_batch_voters(batch_id)
        assert set(retrieved_voters) == set(voters)
        assert len(retrieved_voters) == 3

    def test_get_batch_voters_empty(self, db_manager: DatabaseManager):
        """Test getting voters from a batch with no voters."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Should return empty list initially (before migration runs)
        voters = db_manager.get_batch_voters(batch_id)
        assert isinstance(voters, list)

    def test_add_single_voter_to_batch(self, db_manager: DatabaseManager):
        """Test adding a single voter to an existing batch."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add initial voters
        initial_voters = ["Alice", "Bob"]
        db_manager.add_batch_voters(batch_id, initial_voters)

        # Add a new voter
        was_added = db_manager.add_voter_to_batch(batch_id, "Charlie")
        assert was_added is True

        # Verify the voter was added
        voters = db_manager.get_batch_voters(batch_id)
        assert "Charlie" in voters
        assert len(voters) == 3

    def test_add_duplicate_voter_to_batch(self, db_manager: DatabaseManager):
        """Test adding a duplicate voter to a batch."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add initial voters
        initial_voters = ["Alice", "Bob"]
        db_manager.add_batch_voters(batch_id, initial_voters)

        # Try to add duplicate voter
        was_added = db_manager.add_voter_to_batch(batch_id, "Alice")
        assert was_added is False

        # Verify no duplicate was created
        voters = db_manager.get_batch_voters(batch_id)
        assert voters.count("Alice") == 1
        assert len(voters) == 2

    def test_voters_isolated_between_batches(self, db_manager: DatabaseManager):
        """Test that voters are isolated between different batches."""
        # Create first batch
        batch_id1 = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "User 1")
        voters1 = ["Alice", "Bob"]
        db_manager.add_batch_voters(batch_id1, voters1)

        # Cancel first batch and create second batch
        db_manager.cancel_batch(batch_id1)
        batch_id2 = db_manager.create_batch("2024-03-26", "2024-03-28T14:00:00+00:00", "User 2")
        voters2 = ["Charlie", "David", "Eve"]
        db_manager.add_batch_voters(batch_id2, voters2)

        # Verify voters are isolated
        retrieved_voters1 = db_manager.get_batch_voters(batch_id1)
        retrieved_voters2 = db_manager.get_batch_voters(batch_id2)

        assert set(retrieved_voters1) == set(voters1)
        assert set(retrieved_voters2) == set(voters2)
        assert len(retrieved_voters1) == 2
        assert len(retrieved_voters2) == 3

    def test_voters_sorted_alphabetically(self, db_manager: DatabaseManager):
        """Test that voters are returned in alphabetical order."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add voters in random order
        voters = ["Zoe", "Alice", "Bob", "Charlie"]
        db_manager.add_batch_voters(batch_id, voters)

        # Retrieve voters
        retrieved_voters = db_manager.get_batch_voters(batch_id)

        # Should be sorted alphabetically
        expected_sorted = ["Alice", "Bob", "Charlie", "Zoe"]
        assert retrieved_voters == expected_sorted


class TestBatchVotersPool:
    """Test per-batch voter storage functionality with DatabasePool."""

    def test_add_batch_voters_pool(self, db_pool: DatabaseManager):
        """Test adding voters to a batch using DatabasePool."""
        # Create a batch
        batch_id = db_pool.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add voters to the batch
        voters = ["Alice", "Bob", "Charlie"]
        db_pool.add_batch_voters(batch_id, voters)

        # Retrieve voters
        retrieved_voters = db_pool.get_batch_voters(batch_id)
        assert set(retrieved_voters) == set(voters)
        assert len(retrieved_voters) == 3

    def test_add_single_voter_pool(self, db_pool: DatabaseManager):
        """Test adding a single voter using DatabasePool."""
        # Create a batch
        batch_id = db_pool.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add initial voters
        initial_voters = ["Alice", "Bob"]
        db_pool.add_batch_voters(batch_id, initial_voters)

        # Add a new voter
        was_added = db_pool.add_voter_to_batch(batch_id, "Charlie")
        assert was_added is True

        # Verify the voter was added
        voters = db_pool.get_batch_voters(batch_id)
        assert "Charlie" in voters
        assert len(voters) == 3

    def test_pool_cleanup(self, db_pool: DatabaseManager):
        """Test that database manager works without connection pooling."""
        # Create some data
        batch_id = db_pool.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")
        db_pool.add_batch_voters(batch_id, ["Alice", "Bob"])

        # Verify data was created (no pool cleanup needed)
        voters = db_pool.get_batch_voters(batch_id)
        assert len(voters) == 2


class TestBatchVotersIntegration:
    """Integration tests for batch voters with other functionality."""

    def test_batch_creation_with_voters(self, db_manager: DatabaseManager):
        """Test that batch creation can be followed by voter addition."""
        # Create a batch
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

        # Get active batch with all data
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None
        assert active_batch.id == batch_id
        assert len(active_batch.issues) == 2

        # Get voters separately
        batch_voters = db_manager.get_batch_voters(batch_id)
        assert set(batch_voters) == set(voters)

    def test_votes_with_batch_voters(self, db_manager: DatabaseManager):
        """Test that voting works with batch-specific voters."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add voters
        voters = ["Alice", "Bob"]
        db_manager.add_batch_voters(batch_id, voters)

        # Add votes from batch voters
        success1, was_update1 = db_manager.upsert_vote(batch_id, "Alice", "1234", 5)
        success2, was_update2 = db_manager.upsert_vote(batch_id, "Bob", "1234", 8)

        assert success1 is True
        assert was_update1 is False  # New vote
        assert success2 is True
        assert was_update2 is False  # New vote

        # Verify vote count
        vote_count = db_manager.get_vote_count_by_voter(batch_id)
        assert vote_count == 2

        # Add vote from new voter (simulating dynamic addition)
        db_manager.add_voter_to_batch(batch_id, "Charlie")
        success3, was_update3 = db_manager.upsert_vote(batch_id, "Charlie", "1234", 3)

        assert success3 is True
        assert was_update3 is False  # New vote

        # Vote count should now be 3
        vote_count = db_manager.get_vote_count_by_voter(batch_id)
        assert vote_count == 3

        # Verify all voters are in the batch
        batch_voters = db_manager.get_batch_voters(batch_id)
        assert set(batch_voters) == {"Alice", "Bob", "Charlie"}

    def test_batch_completion_with_voters(self, db_manager: DatabaseManager):
        """Test batch completion logic with batch-specific voters."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add voters
        voters = ["Alice", "Bob"]
        db_manager.add_batch_voters(batch_id, voters)

        # Add votes from all voters
        db_manager.upsert_vote(batch_id, "Alice", "1234", 5)
        db_manager.upsert_vote(batch_id, "Bob", "1234", 8)

        # Vote count should equal number of batch voters
        vote_count = db_manager.get_vote_count_by_voter(batch_id)
        batch_voters = db_manager.get_batch_voters(batch_id)

        assert vote_count == len(batch_voters)
        assert vote_count == 2

        # Complete the batch
        db_manager.complete_batch(batch_id)

        # Should no longer be active
        active_batch = db_manager.get_active_batch()
        assert active_batch is None


class TestZulipMentionParsing:
    """Test parsing of Zulip mention format in voter names."""

    def test_parse_voter_name_with_mention_format(self):
        """Test parsing Zulip @**username** format."""
        from unittest.mock import MagicMock

        from zulip_refinement_bot.handlers import MessageHandler

        # Create a minimal handler instance for testing
        handler = MessageHandler(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())

        # Test Zulip mention format
        result = handler._parse_voter_name("@**jaimergp**")
        assert result == "jaimergp"

        # Test plain text format
        result = handler._parse_voter_name("Jane Doe")
        assert result == "Jane Doe"

        # Test with extra whitespace
        result = handler._parse_voter_name("  @**username**  ")
        assert result == "username"

        # Test plain text with whitespace
        result = handler._parse_voter_name("  John Smith  ")
        assert result == "John Smith"


class TestBatchMessageUpdates:
    """Test that batch messages are updated when voters change."""

    def test_add_voter_updates_batch_message(self):
        """Test that adding a voter updates the batch refinement message."""
        from unittest.mock import MagicMock, patch

        from zulip_refinement_bot.handlers import MessageHandler

        # Create mocks
        mock_config = MagicMock()
        mock_zulip_client = MagicMock()
        mock_batch_service = MagicMock()
        mock_voting_service = MagicMock()
        mock_results_service = MagicMock()

        # Set up active batch
        mock_active_batch = MagicMock()
        mock_active_batch.id = 1
        mock_batch_service.get_active_batch.return_value = mock_active_batch
        mock_batch_service.database.add_voter_to_batch.return_value = True

        handler = MessageHandler(
            mock_config,
            mock_zulip_client,
            mock_batch_service,
            mock_voting_service,
            mock_results_service,
        )

        # Test message
        message = {"sender_full_name": "Test User"}
        content = "add @**newuser**"

        # Mock the methods using patch
        with (
            patch.object(handler, "_update_batch_message") as mock_update,
            patch.object(handler, "_send_reply") as mock_send_reply,
        ):
            # Call the handler
            handler.handle_add_voter(message, content)

            # Verify voter was added
            mock_batch_service.database.add_voter_to_batch.assert_called_once_with(1, "newuser")

            # Verify batch message was updated
            mock_update.assert_called_once_with(1, mock_active_batch)

            # Verify success message was sent
            mock_send_reply.assert_called_once_with(message, "✅ Added **newuser** to batch 1")

    def test_remove_voter_updates_batch_message(self):
        """Test that removing a voter updates the batch refinement message."""
        from unittest.mock import MagicMock, patch

        from zulip_refinement_bot.handlers import MessageHandler

        # Create mocks
        mock_config = MagicMock()
        mock_zulip_client = MagicMock()
        mock_batch_service = MagicMock()
        mock_voting_service = MagicMock()
        mock_results_service = MagicMock()

        # Set up active batch
        mock_active_batch = MagicMock()
        mock_active_batch.id = 1
        mock_batch_service.get_active_batch.return_value = mock_active_batch
        mock_batch_service.database.remove_voter_from_batch.return_value = True

        handler = MessageHandler(
            mock_config,
            mock_zulip_client,
            mock_batch_service,
            mock_voting_service,
            mock_results_service,
        )

        # Test message
        message = {"sender_full_name": "Test User"}
        content = "remove @**olduser**"

        # Mock the methods using patch
        with (
            patch.object(handler, "_update_batch_message") as mock_update,
            patch.object(handler, "_send_reply") as mock_send_reply,
        ):
            # Call the handler
            handler.handle_remove_voter(message, content)

            # Verify voter was removed
            mock_batch_service.database.remove_voter_from_batch.assert_called_once_with(
                1, "olduser"
            )

            # Verify batch message was updated
            mock_update.assert_called_once_with(1, mock_active_batch)

            # Verify success message was sent
            mock_send_reply.assert_called_once_with(message, "✅ Removed **olduser** from batch 1")

    def test_no_update_when_voter_already_exists(self):
        """Test that batch message is not updated when voter already exists."""
        from unittest.mock import MagicMock, patch

        from zulip_refinement_bot.handlers import MessageHandler

        # Create mocks
        mock_config = MagicMock()
        mock_zulip_client = MagicMock()
        mock_batch_service = MagicMock()
        mock_voting_service = MagicMock()
        mock_results_service = MagicMock()

        # Set up active batch
        mock_active_batch = MagicMock()
        mock_active_batch.id = 1
        mock_batch_service.get_active_batch.return_value = mock_active_batch
        mock_batch_service.database.add_voter_to_batch.return_value = False  # Already exists

        handler = MessageHandler(
            mock_config,
            mock_zulip_client,
            mock_batch_service,
            mock_voting_service,
            mock_results_service,
        )

        # Test message
        message = {"sender_full_name": "Test User"}
        content = "add existing_user"

        # Mock the methods using patch
        with (
            patch.object(handler, "_update_batch_message") as mock_update,
            patch.object(handler, "_send_reply") as mock_send_reply,
        ):
            # Call the handler
            handler.handle_add_voter(message, content)

            # Verify voter addition was attempted
            mock_batch_service.database.add_voter_to_batch.assert_called_once_with(
                1, "existing_user"
            )

            # Verify batch message was NOT updated (since no change occurred)
            mock_update.assert_not_called()

            # Verify info message was sent
            mock_send_reply.assert_called_once_with(
                message, "ℹ️ **existing_user** was already in batch 1"
            )
