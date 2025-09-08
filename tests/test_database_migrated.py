"""Tests for the migrated database manager."""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.zulip_refinement_bot.database import DatabaseManager
from src.zulip_refinement_bot.models import IssueData


@pytest.fixture
def temp_db() -> Generator[Path, None, None]:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        yield db_path
    finally:
        if db_path.exists():
            db_path.unlink()


class TestDatabaseManager:
    """Test the migrated database manager."""


def test_database_migrated_initialization_with_auto_migrate(temp_db: Path):
    """Test database manager initialization with auto-migration."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Verify migrations were applied
    status = db_manager.get_migration_status()
    applied_migrations = [v for v, info in status.items() if info["status"] == "applied"]
    assert len(applied_migrations) > 0


def test_database_migrated_initialization_without_auto_migrate(temp_db: Path):
    """Test database manager initialization without auto-migration."""
    db_manager = DatabaseManager(temp_db, auto_migrate=False)

    # Verify no migrations were applied automatically
    status = db_manager.get_migration_status()
    applied_migrations = [v for v, info in status.items() if info["status"] == "applied"]
    assert len(applied_migrations) == 0


def test_database_migrated_migration_status_access(temp_db: Path):
    """Test accessing migration status through database manager."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    status = db_manager.get_migration_status()
    assert isinstance(status, dict)
    assert len(status) > 0

    # Check status structure
    for _version, info in status.items():
        assert "status" in info
        assert "description" in info
        assert "can_rollback" in info


def test_database_migrated_schema_validation(temp_db: Path):
    """Test schema validation through database manager."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    is_valid = db_manager.validate_schema()
    assert is_valid is True


def test_database_migrated_database_operations_after_migration(temp_db: Path):
    """Test that normal database operations work after migration."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Test creating a batch
    batch_id = db_manager.create_batch(
        date="2024-01-01", deadline="2024-01-02T10:00:00", facilitator="test_facilitator"
    )
    assert batch_id > 0

    # Test adding issues to batch
    issues = [
        IssueData(
            issue_number="123",
            title="Test Issue 1",
            url="https://github.com/test/repo/issues/123",
        ),
        IssueData(
            issue_number="124",
            title="Test Issue 2",
            url="https://github.com/test/repo/issues/124",
        ),
    ]
    db_manager.add_issues_to_batch(batch_id, issues)

    # Test retrieving batch
    batch = db_manager.get_active_batch()
    assert batch is not None
    assert batch.id == batch_id
    assert batch.facilitator == "test_facilitator"
    assert len(batch.issues) == 2


def test_database_migrated_voting_operations_after_migration(temp_db: Path):
    """Test voting operations work after migration."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Create batch and add issues
    batch_id = db_manager.create_batch(
        date="2024-01-01", deadline="2024-01-02T10:00:00", facilitator="test_facilitator"
    )
    issues = [IssueData(issue_number="123", title="Test Issue", url="")]
    db_manager.add_issues_to_batch(batch_id, issues)

    # Test storing votes
    success = db_manager.store_vote(batch_id, "voter1", "123", 5)
    assert success is True

    # Test upsert vote
    success, was_update = db_manager.upsert_vote(batch_id, "voter2", "123", 8)
    assert success is True
    assert was_update is False

    # Test updating existing vote
    success, was_update = db_manager.upsert_vote(batch_id, "voter1", "123", 3)
    assert success is True
    assert was_update is True

    # Test retrieving votes
    votes = db_manager.get_batch_votes(batch_id)
    assert len(votes) == 2

    # Test vote count
    vote_count = db_manager.get_vote_count_by_voter(batch_id)
    assert vote_count == 2


def test_database_migrated_batch_voters_operations_after_migration(temp_db: Path):
    """Test batch voters operations work after migration."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Create batch
    batch_id = db_manager.create_batch(
        date="2024-01-01", deadline="2024-01-02T10:00:00", facilitator="test_facilitator"
    )

    # Test adding voters
    voters = ["voter1@example.com", "voter2@example.com", "voter3@example.com"]
    db_manager.add_batch_voters(batch_id, voters)

    # Test retrieving voters
    retrieved_voters = db_manager.get_batch_voters(batch_id)
    assert set(retrieved_voters) == set(voters)

    # Test adding single voter
    added = db_manager.add_voter_to_batch(batch_id, "voter4@example.com")
    assert added is True

    # Test adding duplicate voter
    added = db_manager.add_voter_to_batch(batch_id, "voter1@example.com")
    assert added is False

    # Test removing voter
    removed = db_manager.remove_voter_from_batch(batch_id, "voter2@example.com")
    assert removed is True

    # Test removing non-existent voter
    removed = db_manager.remove_voter_from_batch(batch_id, "nonexistent@example.com")
    assert removed is False


def test_database_migrated_final_estimates_operations_after_migration(temp_db: Path):
    """Test final estimates operations work after migration."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Create batch and add issues
    batch_id = db_manager.create_batch(
        date="2024-01-01", deadline="2024-01-02T10:00:00", facilitator="test_facilitator"
    )
    issues = [
        IssueData(issue_number="123", title="Test Issue 1", url=""),
        IssueData(issue_number="124", title="Test Issue 2", url=""),
    ]
    db_manager.add_issues_to_batch(batch_id, issues)

    # Test storing final estimates
    db_manager.store_final_estimate(batch_id, "123", 5, "Agreed on 5 points after discussion")
    db_manager.store_final_estimate(batch_id, "124", 8, "Complex issue, needs 8 points")

    # Test retrieving final estimates
    estimates = db_manager.get_final_estimates(batch_id)
    assert len(estimates) == 2

    # Check estimate details
    estimate_123 = next(e for e in estimates if e.issue_number == "123")
    assert estimate_123.final_points == 5
    assert "discussion" in estimate_123.rationale.lower()
    assert isinstance(estimate_123.timestamp, datetime)


def test_database_migrated_batch_status_operations_after_migration(temp_db: Path):
    """Test batch status operations work after migration."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Create batch
    batch_id = db_manager.create_batch(
        date="2024-01-01", deadline="2024-01-02T10:00:00", facilitator="test_facilitator"
    )

    # Test setting batch to discussing
    db_manager.set_batch_discussing(batch_id)
    batch = db_manager.get_active_batch()
    assert batch is not None
    assert batch.status == "discussing"

    # Test completing batch
    db_manager.complete_batch(batch_id)
    batch = db_manager.get_active_batch()
    assert batch is None  # No active batch after completion

    # Test cancelling batch (create new one first)
    new_batch_id = db_manager.create_batch(
        date="2024-01-02", deadline="2024-01-03T10:00:00", facilitator="test_facilitator"
    )
    db_manager.cancel_batch(new_batch_id)
    batch = db_manager.get_active_batch()
    assert batch is None  # No active batch after cancellation


def test_database_migrated_message_id_operations_after_migration(temp_db: Path):
    """Test message ID operations work after migration."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Create batch
    batch_id = db_manager.create_batch(
        date="2024-01-01", deadline="2024-01-02T10:00:00", facilitator="test_facilitator"
    )

    # Test updating message ID
    message_id = 12345
    db_manager.update_batch_message_id(batch_id, message_id)

    # Verify message ID was stored
    batch = db_manager.get_active_batch()
    assert batch is not None
    assert batch.message_id == message_id


def test_database_migrated_migration_failure_handling(temp_db: Path):
    """Test handling of migration failures during initialization."""
    with patch("src.zulip_refinement_bot.database.MigrationRunner") as mock_runner_class:
        mock_runner = mock_runner_class.return_value
        mock_runner.run_migrations.side_effect = Exception("Migration failed")

        with pytest.raises(Exception, match="Migration failed"):
            DatabaseManager(temp_db, auto_migrate=True)


def test_database_migrated_database_path_creation(temp_db: Path):
    """Test that database path and parent directories are created."""
    # Use a path that doesn't exist
    nested_path = temp_db.parent / "nested" / "path" / "test.db"

    DatabaseManager(nested_path, auto_migrate=True)

    # Verify path was created
    assert nested_path.exists()
    assert nested_path.parent.exists()

    # Clean up
    nested_path.unlink()
    nested_path.parent.rmdir()
    nested_path.parent.parent.rmdir()


def test_database_migrated_multiple_database_instances(temp_db: Path):
    """Test that multiple database manager instances work correctly."""
    # Create first instance and apply migrations
    db1 = DatabaseManager(temp_db, auto_migrate=True)

    # Create second instance (should not re-run migrations)
    db2 = DatabaseManager(temp_db, auto_migrate=True)

    # Both should have the same migration status
    status1 = db1.get_migration_status()
    status2 = db2.get_migration_status()

    applied1 = [v for v, info in status1.items() if info["status"] == "applied"]
    applied2 = [v for v, info in status2.items() if info["status"] == "applied"]

    assert applied1 == applied2


def test_database_migrated_schema_validation_after_manual_changes(temp_db: Path):
    """Test schema validation after manual database changes."""
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Initially should be valid
    assert db_manager.validate_schema() is True

    # Make a manual change that breaks validation
    # (This is a simplified test - in practice you'd need a more sophisticated setup)
    import sqlite3

    with sqlite3.connect(temp_db) as conn:
        # Drop a table that should exist
        conn.execute("DROP TABLE IF EXISTS batches")
        conn.commit()

    # Validation should now fail
    assert db_manager.validate_schema() is False


class TestDatabaseManagerIntegration:
    """Integration tests for the migrated database manager."""


def test_database_migrated_complete_workflow_with_migrations(temp_db: Path):
    """Test complete workflow including migrations."""
    # Initialize database with migrations
    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # Verify all expected tables exist and work
    batch_id = db_manager.create_batch(
        date="2024-01-01", deadline="2024-01-02T10:00:00", facilitator="test_facilitator"
    )

    # Add issues
    issues = [
        IssueData(
            issue_number="123",
            title="Test Issue 1",
            url="https://github.com/test/repo/issues/123",
        ),
        IssueData(
            issue_number="124",
            title="Test Issue 2",
            url="https://github.com/test/repo/issues/124",
        ),
    ]
    db_manager.add_issues_to_batch(batch_id, issues)

    # Add voters
    voters = ["voter1@example.com", "voter2@example.com"]
    db_manager.add_batch_voters(batch_id, voters)

    # Store votes
    db_manager.upsert_vote(batch_id, "voter1@example.com", "123", 5)
    db_manager.upsert_vote(batch_id, "voter2@example.com", "123", 8)
    db_manager.upsert_vote(batch_id, "voter1@example.com", "124", 3)
    db_manager.upsert_vote(batch_id, "voter2@example.com", "124", 5)

    # Set to discussing
    db_manager.set_batch_discussing(batch_id)

    # Store final estimates
    db_manager.store_final_estimate(batch_id, "123", 5, "Consensus reached")
    db_manager.store_final_estimate(batch_id, "124", 3, "Simplified approach")

    # Complete batch
    db_manager.complete_batch(batch_id)

    # Verify final state
    estimates = db_manager.get_final_estimates(batch_id)
    assert len(estimates) == 2

    votes = db_manager.get_batch_votes(batch_id)
    assert len(votes) == 4

    batch_voters = db_manager.get_batch_voters(batch_id)
    assert len(batch_voters) == 2


def test_database_migrated_backward_compatibility(temp_db: Path):
    """Test that the migrated database manager maintains backward compatibility."""
    # This test ensures that existing code using the database manager
    # continues to work with the new migration system

    db_manager = DatabaseManager(temp_db, auto_migrate=True)

    # All the original database operations should still work
    # (This is essentially testing the same interface as the original DatabaseManager)

    # Test batch operations
    batch_id = db_manager.create_batch("2024-01-01", "2024-01-02T10:00:00", "facilitator")
    assert batch_id > 0

    # Test issue operations
    issues = [IssueData(issue_number="123", title="Test", url="")]
    db_manager.add_issues_to_batch(batch_id, issues)
    retrieved_issues = db_manager.get_batch_issues(batch_id)
    assert len(retrieved_issues) == 1

    # Test vote operations
    success = db_manager.store_vote(batch_id, "voter", "123", 5)
    assert success is True

    has_voted = db_manager.has_voter_voted(batch_id, "voter")
    assert has_voted is True

    # Test batch status operations
    db_manager.set_batch_discussing(batch_id)
    db_manager.complete_batch(batch_id)

    # All operations should work without any changes to the calling code
