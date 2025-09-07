"""Tests for VotingService with per-batch voter functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zulip_refinement_bot.config import Config
from zulip_refinement_bot.database import DatabaseManager
from zulip_refinement_bot.exceptions import ValidationError, VotingError
from zulip_refinement_bot.models import BatchData, IssueData
from zulip_refinement_bot.services import VotingService


class TestVotingServiceBatchVoters:
    """Test VotingService with per-batch voter functionality."""

    @pytest.fixture
    def voting_service(self, test_config: Config, db_manager: DatabaseManager) -> VotingService:
        """Create a VotingService for testing."""
        # Create mock parser
        mock_parser = MagicMock()
        mock_parser.parse_estimation_input.return_value = ({"1234": 5, "1235": 8}, [])

        return VotingService(config=test_config, database=db_manager, parser=mock_parser)

    @pytest.fixture
    def active_batch_with_voters(self, db_manager: DatabaseManager) -> BatchData:
        """Create an active batch with voters and issues."""
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

        # Return the batch data
        batch = db_manager.get_active_batch()
        assert batch is not None  # Should always exist since we just created it
        return batch

    def test_submit_votes_existing_voter(
        self, voting_service: VotingService, active_batch_with_voters: BatchData
    ):
        """Test submitting votes from an existing batch voter."""
        # Submit votes from existing voter
        estimates, has_updates, all_complete = voting_service.submit_votes(
            "1234: 5, 1235: 8", "Alice", active_batch_with_voters
        )

        assert estimates == {"1234": 5, "1235": 8}
        assert has_updates is True
        assert all_complete is False  # Only 1 of 3 voters has voted

    def test_submit_votes_new_voter_auto_add(
        self,
        voting_service: VotingService,
        active_batch_with_voters: BatchData,
        db_manager: DatabaseManager,
    ):
        """Test submitting votes from a new voter (should be auto-added)."""
        # Verify initial voter count
        assert active_batch_with_voters.id is not None
        initial_voters = db_manager.get_batch_voters(active_batch_with_voters.id)
        assert "David" not in initial_voters
        assert len(initial_voters) == 3

        # Submit votes from new voter
        estimates, has_updates, all_complete = voting_service.submit_votes(
            "1234: 5, 1235: 8",
            "David",  # New voter not in original list
            active_batch_with_voters,
        )

        assert estimates == {"1234": 5, "1235": 8}
        assert has_updates is True
        assert all_complete is False  # Only 1 of 4 voters has voted

        # Verify voter was added to batch
        updated_voters = db_manager.get_batch_voters(active_batch_with_voters.id)
        assert "David" in updated_voters
        assert len(updated_voters) == 4

    def test_check_completion_status_batch_voters(
        self,
        voting_service: VotingService,
        active_batch_with_voters: BatchData,
        db_manager: DatabaseManager,
    ):
        """Test completion status checking with batch-specific voters."""
        batch_id = active_batch_with_voters.id
        assert batch_id is not None

        # Initially no votes
        vote_count, total_voters, is_complete = voting_service.check_completion_status(batch_id)
        assert vote_count == 0
        assert total_voters == 3  # Alice, Bob, Charlie
        assert is_complete is False

        # Add votes from 2 voters
        db_manager.upsert_vote(batch_id, "Alice", "1234", 5)
        db_manager.upsert_vote(batch_id, "Bob", "1234", 8)

        vote_count, total_voters, is_complete = voting_service.check_completion_status(batch_id)
        assert vote_count == 2
        assert total_voters == 3
        assert is_complete is False

        # Add vote from third voter
        db_manager.upsert_vote(batch_id, "Charlie", "1234", 3)

        vote_count, total_voters, is_complete = voting_service.check_completion_status(batch_id)
        assert vote_count == 3
        assert total_voters == 3
        assert is_complete is True

    def test_check_completion_status_with_dynamic_voter(
        self,
        voting_service: VotingService,
        active_batch_with_voters: BatchData,
        db_manager: DatabaseManager,
    ):
        """Test completion status when a new voter is dynamically added."""
        batch_id = active_batch_with_voters.id
        assert batch_id is not None

        # Add votes from original 3 voters
        db_manager.upsert_vote(batch_id, "Alice", "1234", 5)
        db_manager.upsert_vote(batch_id, "Bob", "1234", 8)
        db_manager.upsert_vote(batch_id, "Charlie", "1234", 3)

        # Should be complete with 3 voters
        vote_count, total_voters, is_complete = voting_service.check_completion_status(batch_id)
        assert vote_count == 3
        assert total_voters == 3
        assert is_complete is True

        # Add a new voter dynamically
        db_manager.add_voter_to_batch(batch_id, "David")

        # Now should not be complete (3 votes, 4 voters)
        vote_count, total_voters, is_complete = voting_service.check_completion_status(batch_id)
        assert vote_count == 3
        assert total_voters == 4
        assert is_complete is False

        # Add vote from new voter
        db_manager.upsert_vote(batch_id, "David", "1234", 2)

        # Now should be complete again
        vote_count, total_voters, is_complete = voting_service.check_completion_status(batch_id)
        assert vote_count == 4
        assert total_voters == 4
        assert is_complete is True

    def test_submit_votes_no_active_batch(self, voting_service: VotingService):
        """Test submitting votes when no batch is active."""
        # Create a batch data with no ID (simulating no active batch)
        batch = BatchData(
            id=None,
            date="2024-03-25",
            deadline="2024-03-27T14:00:00+00:00",
            facilitator="Test User",
        )

        with pytest.raises(VotingError, match="No active batch found"):
            voting_service.submit_votes("1234: 5", "Alice", batch)

    def test_submit_votes_validation_error(
        self, voting_service: VotingService, active_batch_with_voters: BatchData
    ):
        """Test submitting votes with validation errors."""
        # Mock parser to return validation errors
        with patch.object(
            voting_service.parser, "parse_estimation_input", return_value=({}, ["Invalid format"])
        ):
            with pytest.raises(ValidationError, match="Invalid story point values found"):
                voting_service.submit_votes("invalid format", "Alice", active_batch_with_voters)

    def test_get_batch_votes(
        self,
        voting_service: VotingService,
        active_batch_with_voters: BatchData,
        db_manager: DatabaseManager,
    ):
        """Test retrieving all votes for a batch."""
        batch_id = active_batch_with_voters.id
        assert batch_id is not None

        # Add some votes
        db_manager.upsert_vote(batch_id, "Alice", "1234", 5)
        db_manager.upsert_vote(batch_id, "Alice", "1235", 8)
        db_manager.upsert_vote(batch_id, "Bob", "1234", 3)

        # Get votes through service
        votes = voting_service.get_batch_votes(batch_id)

        assert len(votes) == 3
        vote_dict = {(v.voter, v.issue_number): v.points for v in votes}
        assert vote_dict[("Alice", "1234")] == 5
        assert vote_dict[("Alice", "1235")] == 8
        assert vote_dict[("Bob", "1234")] == 3

    def test_multiple_vote_submissions_same_voter(
        self,
        voting_service: VotingService,
        active_batch_with_voters: BatchData,
        db_manager: DatabaseManager,
    ):
        """Test multiple vote submissions from the same voter (updates)."""
        # First submission
        estimates1, has_updates1, _ = voting_service.submit_votes(
            "1234: 5, 1235: 8", "Alice", active_batch_with_voters
        )

        assert estimates1 == {"1234": 5, "1235": 8}
        assert has_updates1 is True  # New votes

        # Second submission (updates)
        with patch.object(
            voting_service.parser,
            "parse_estimation_input",
            return_value=({"1234": 3, "1235": 13}, []),
        ):
            estimates2, has_updates2, _ = voting_service.submit_votes(
                "1234: 3, 1235: 13", "Alice", active_batch_with_voters
            )

        assert estimates2 == {"1234": 3, "1235": 13}
        assert has_updates2 is True  # Updated votes

        # Verify final vote values
        assert active_batch_with_voters.id is not None
        votes = db_manager.get_batch_votes(active_batch_with_voters.id)
        alice_votes = {v.issue_number: v.points for v in votes if v.voter == "Alice"}
        assert alice_votes == {"1234": 3, "1235": 13}

    def test_race_condition_voter_addition(
        self,
        voting_service: VotingService,
        active_batch_with_voters: BatchData,
        db_manager: DatabaseManager,
    ):
        """Test race condition when adding the same voter simultaneously."""
        batch_id = active_batch_with_voters.id
        assert batch_id is not None

        # Manually add voter first (simulating race condition)
        db_manager.add_voter_to_batch(batch_id, "David")

        # Now submit vote from same voter (should handle gracefully)
        estimates, has_updates, _ = voting_service.submit_votes(
            "1234: 5, 1235: 8", "David", active_batch_with_voters
        )

        assert estimates == {"1234": 5, "1235": 8}
        assert has_updates is True

        # Verify voter appears only once
        voters = db_manager.get_batch_voters(batch_id)
        assert voters.count("David") == 1
