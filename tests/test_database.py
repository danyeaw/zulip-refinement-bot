"""Tests for database management."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

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
        batch_id = db_manager.create_batch(
            "2024-03-25", "2024-03-27T14:00:00+00:00", "Test User"
        )
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
        batch_id = db_manager.create_batch(
            "2024-03-25", "2024-03-27T14:00:00+00:00", "Test User"
        )

        # Add issues to batch
        db_manager.add_issues_to_batch(batch_id, sample_issues)

        # Retrieve issues
        retrieved_issues = db_manager.get_batch_issues(batch_id)
        assert len(retrieved_issues) == len(sample_issues)
        
        for original, retrieved in zip(sample_issues, retrieved_issues):
            assert retrieved.issue_number == original.issue_number
            assert retrieved.title == original.title
            assert retrieved.url == original.url

    def test_get_active_batch_with_issues(
        self, db_manager: DatabaseManager, sample_issues: list[IssueData]
    ):
        """Test getting active batch with its issues."""
        # Create batch and add issues
        batch_id = db_manager.create_batch(
            "2024-03-25", "2024-03-27T14:00:00+00:00", "Test User"
        )
        db_manager.add_issues_to_batch(batch_id, sample_issues)

        # Get active batch
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None
        assert len(active_batch.issues) == len(sample_issues)
        
        for original, retrieved in zip(sample_issues, active_batch.issues):
            assert retrieved.issue_number == original.issue_number
            assert retrieved.title == original.title
            assert retrieved.url == original.url

    def test_cancel_batch(self, db_manager: DatabaseManager):
        """Test batch cancellation."""
        # Create a batch
        batch_id = db_manager.create_batch(
            "2024-03-25", "2024-03-27T14:00:00+00:00", "Test User"
        )

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
        batch_id = db_manager.create_batch(
            "2024-03-25", "2024-03-27T14:00:00+00:00", "Test User"
        )

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
        batch_id1 = db_manager.create_batch(
            "2024-03-25", "2024-03-27T14:00:00+00:00", "User 1"
        )

        # Cancel first batch
        db_manager.cancel_batch(batch_id1)

        # Create second batch
        batch_id2 = db_manager.create_batch(
            "2024-03-26", "2024-03-28T14:00:00+00:00", "User 2"
        )

        # Only second batch should be active
        active_batch = db_manager.get_active_batch()
        assert active_batch is not None
        assert active_batch.id == batch_id2
        assert active_batch.facilitator == "User 2"
