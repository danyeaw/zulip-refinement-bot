"""Tests for the reminder system functionality."""

import pytest

from zulip_refinement_bot.config import Config
from zulip_refinement_bot.database import DatabaseManager


@pytest.fixture
def database_manager(tmp_path):
    """Create a database manager with a temporary database."""
    db_path = tmp_path / "test.db"
    db = DatabaseManager(db_path)
    return db


def test_reminder_tracking(database_manager):
    """Test that reminders can be tracked and prevent duplicates."""
    # Create a test batch
    batch_id = database_manager.create_batch("2025-01-01", "2025-01-03T12:00:00", "Test User")

    # Initially no reminders should be sent
    assert not database_manager.has_reminder_been_sent(batch_id, "halfway")
    assert not database_manager.has_reminder_been_sent(batch_id, "1_hour")

    # Record a reminder
    database_manager.record_reminder_sent(batch_id, "halfway")

    # Now the halfway reminder should be marked as sent
    assert database_manager.has_reminder_been_sent(batch_id, "halfway")
    assert not database_manager.has_reminder_been_sent(batch_id, "1_hour")

    # Record the 1-hour reminder
    database_manager.record_reminder_sent(batch_id, "1_hour")

    # Both should now be marked as sent
    assert database_manager.has_reminder_been_sent(batch_id, "halfway")
    assert database_manager.has_reminder_been_sent(batch_id, "1_hour")


def test_get_voters_without_votes(database_manager):
    """Test getting voters who haven't submitted votes yet."""
    # Create a test batch
    batch_id = database_manager.create_batch("2025-01-01", "2025-01-03T12:00:00", "Test User")

    # Add some voters
    voters = ["Alice", "Bob", "Charlie"]
    database_manager.add_batch_voters(batch_id, voters)

    # Initially all voters should be without votes
    voters_without_votes = database_manager.get_voters_without_votes(batch_id)
    assert set(voters_without_votes) == set(voters)

    # Add a vote for Alice
    database_manager.upsert_vote(batch_id, "Alice", "123", 5)

    # Now Alice should not be in the list
    voters_without_votes = database_manager.get_voters_without_votes(batch_id)
    assert set(voters_without_votes) == {"Bob", "Charlie"}

    # Add an abstention for Bob
    database_manager.upsert_abstention(batch_id, "Bob", "123")

    # Now only Charlie should be without votes
    voters_without_votes = database_manager.get_voters_without_votes(batch_id)
    assert voters_without_votes == ["Charlie"]


def test_reminder_duplicate_prevention(database_manager):
    """Test that duplicate reminders are prevented."""
    batch_id = database_manager.create_batch("2025-01-01", "2025-01-03T12:00:00", "Test User")

    # Record the same reminder multiple times
    database_manager.record_reminder_sent(batch_id, "halfway")
    database_manager.record_reminder_sent(batch_id, "halfway")  # Should not cause error
    database_manager.record_reminder_sent(batch_id, "halfway")  # Should not cause error

    # Should still only be marked as sent once
    assert database_manager.has_reminder_been_sent(batch_id, "halfway")


def test_reminder_threshold_calculations():
    """Test the reminder threshold calculations."""
    config = Config(
        zulip_email="test@example.com",
        zulip_api_key="test_key",
        zulip_site="test.zulipchat.com",
        zulip_token="test_token",
        default_deadline_hours=48,  # 48 hour deadline
    )

    # Test reminder threshold calculations
    half_deadline_hours = config.default_deadline_hours // 2
    assert half_deadline_hours == 24  # For 48-hour deadline, halfway is 24 hours

    # Test with different deadline
    config_72h = Config(
        zulip_email="test@example.com",
        zulip_api_key="test_key",
        zulip_site="test.zulipchat.com",
        zulip_token="test_token",
        default_deadline_hours=72,  # 72 hour deadline
    )

    half_deadline_hours_72 = config_72h.default_deadline_hours // 2
    assert half_deadline_hours_72 == 36  # For 72-hour deadline, halfway is 36 hours
