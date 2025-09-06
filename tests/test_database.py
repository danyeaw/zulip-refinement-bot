"""Tests for database management."""

from __future__ import annotations

from zulip_refinement_bot.database import DatabaseManager
from zulip_refinement_bot.models import IssueData


class TestDatabaseManager:
    """Test database operations."""

    def test_init_database(self, db_manager: DatabaseManager):
        """Test database initialization."""
        # Database should be initialized without errors
        assert db_manager.db_path.exists()

    def test_no_active_batch_initially(self, db_manager: DatabaseManager):
        """Test that no active batch exists initially."""
        active_batch = db_manager.get_active_batch()
        assert active_batch is None

    def test_create_and_get_batch(self, db_manager: DatabaseManager):
        """Test batch creation and retrieval."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")
        assert isinstance(batch_id, int)

        # Get active batch
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None
        assert active_batch.id == batch_id
        assert active_batch.date == "2024-03-25"
        assert active_batch.facilitator == "Test User"
        assert active_batch.status == "active"

    def test_add_and_get_issues(self, db_manager: DatabaseManager, sample_issues: list[IssueData]):
        """Test adding and retrieving issues."""
        # Create a batch first
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Add issues to batch
        db_manager.add_issues_to_batch(batch_id, sample_issues)

        # Retrieve issues
        retrieved_issues = db_manager.get_batch_issues(batch_id)
        assert len(retrieved_issues) == len(sample_issues)

        for original, retrieved in zip(sample_issues, retrieved_issues, strict=False):
            assert retrieved.issue_number == original.issue_number
            assert retrieved.title == original.title
            assert retrieved.url == original.url

    def test_get_active_batch_with_issues(
        self, db_manager: DatabaseManager, sample_issues: list[IssueData]
    ):
        """Test getting active batch with its issues."""
        # Create batch and add issues
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")
        db_manager.add_issues_to_batch(batch_id, sample_issues)

        # Get active batch
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None
        assert len(active_batch.issues) == len(sample_issues)

        for original, retrieved in zip(sample_issues, active_batch.issues, strict=False):
            assert retrieved.issue_number == original.issue_number
            assert retrieved.title == original.title
            assert retrieved.url == original.url

    def test_cancel_batch(self, db_manager: DatabaseManager):
        """Test batch cancellation."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Should be active initially
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None

        # Cancel the batch
        db_manager.cancel_batch(batch_id)

        # Should be no active batch now
        active_batch = db_manager.get_active_batch()
        assert active_batch is None

    def test_complete_batch(self, db_manager: DatabaseManager):
        """Test batch completion."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Should be active initially
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None

        # Complete the batch
        db_manager.complete_batch(batch_id)

        # Should be no active batch now
        active_batch = db_manager.get_active_batch()
        assert active_batch is None

    def test_multiple_batches_only_one_active(self, db_manager: DatabaseManager):
        """Test that only one batch can be active at a time."""
        # Create first batch
        batch_id1 = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "User 1")

        # Cancel first batch
        db_manager.cancel_batch(batch_id1)

        # Create second batch
        batch_id2 = db_manager.create_batch("2024-03-26", "2024-03-28T14:00:00+00:00", "User 2")

        # Only second batch should be active
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None
        assert active_batch.id == batch_id2
        assert active_batch.facilitator == "User 2"

    def test_store_and_retrieve_votes(self, db_manager: DatabaseManager):
        """Test storing and retrieving votes."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Store some votes
        assert db_manager.store_vote(batch_id, "Voter 1", "1234", 5) is True
        assert db_manager.store_vote(batch_id, "Voter 1", "1235", 8) is True
        assert db_manager.store_vote(batch_id, "Voter 2", "1234", 3) is True

        # Try to store duplicate vote (should fail)
        assert db_manager.store_vote(batch_id, "Voter 1", "1234", 8) is False

        # Get votes
        votes = db_manager.get_batch_votes(batch_id)
        assert len(votes) == 3

        # Check vote details
        vote_dict = {(v.voter, v.issue_number): v.points for v in votes}
        assert vote_dict[("Voter 1", "1234")] == 5
        assert vote_dict[("Voter 1", "1235")] == 8
        assert vote_dict[("Voter 2", "1234")] == 3

    def test_vote_count_by_voter(self, db_manager: DatabaseManager):
        """Test getting unique voter count."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Initially no votes
        assert db_manager.get_vote_count_by_voter(batch_id) == 0

        # Add votes from two voters
        db_manager.store_vote(batch_id, "Voter 1", "1234", 5)
        db_manager.store_vote(batch_id, "Voter 1", "1235", 8)  # Same voter, different issue
        assert db_manager.get_vote_count_by_voter(batch_id) == 1

        db_manager.store_vote(batch_id, "Voter 2", "1234", 3)
        assert db_manager.get_vote_count_by_voter(batch_id) == 2

    def test_has_voter_voted(self, db_manager: DatabaseManager):
        """Test checking if a voter has already voted."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Initially no votes
        assert db_manager.has_voter_voted(batch_id, "Voter 1") is False

        # Add a vote
        db_manager.store_vote(batch_id, "Voter 1", "1234", 5)
        assert db_manager.has_voter_voted(batch_id, "Voter 1") is True
        assert db_manager.has_voter_voted(batch_id, "Voter 2") is False

    def test_update_batch_message_id(self, db_manager: DatabaseManager):
        """Test updating batch message ID."""
        # Create a batch
        batch_id = db_manager.create_batch("2024-03-25", "2024-03-27T14:00:00+00:00", "Test User")

        # Update message ID
        message_id = 12345
        db_manager.update_batch_message_id(batch_id, message_id)

        # Verify it was stored
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None
        assert active_batch.message_id == message_id
