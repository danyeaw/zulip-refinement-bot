"""Tests for specific migration versions."""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from src.zulip_refinement_bot.migrations.runner import MigrationRunner
from src.zulip_refinement_bot.migrations.versions import (
    ALL_MIGRATIONS,
    AddMessageIdMigration,
    BatchVotersMigration,
    FinalEstimatesMigration,
    InitialSchemaMigration,
)


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


@pytest.fixture
def migration_runner(temp_db: Path) -> MigrationRunner:
    """Create a migration runner with temporary database."""
    runner = MigrationRunner(temp_db)
    runner.register_migrations(ALL_MIGRATIONS)
    return runner


def test_migration_versions_initial_schema_migration_properties():
    """Test migration basic properties."""
    migration = InitialSchemaMigration()
    assert migration.version == "001"
    assert "initial schema" in migration.description.lower()
    assert migration.dependencies == []


def test_migration_versions_initial_schema_up_migration(temp_db: Path):
    """Test applying the initial schema migration."""
    migration = InitialSchemaMigration()

    with sqlite3.connect(temp_db) as conn:
        migration.up(conn)

        # Check that all required tables were created
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}
        expected_tables = {"batches", "issues", "votes"}
        assert expected_tables.issubset(tables)

        # Check batches table structure
        cursor = conn.execute("PRAGMA table_info(batches)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {"id", "date", "deadline", "facilitator", "status", "created_at"}
        assert expected_columns.issubset(columns)

        # Check issues table structure
        cursor = conn.execute("PRAGMA table_info(issues)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {"id", "batch_id", "issue_number", "title", "url"}
        assert expected_columns.issubset(columns)

        # Check votes table structure
        cursor = conn.execute("PRAGMA table_info(votes)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {"id", "batch_id", "issue_number", "voter", "points", "created_at"}
        assert expected_columns.issubset(columns)


def test_migration_versions_initial_schema_down_migration(temp_db: Path):
    """Test rolling back the initial schema migration."""
    migration = InitialSchemaMigration()

    with sqlite3.connect(temp_db) as conn:
        # Apply migration
        migration.up(conn)

        # Verify tables exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('batches', 'issues', 'votes')"
        )
        assert len(cursor.fetchall()) == 3

        # Rollback migration
        migration.down(conn)

        # Verify tables were dropped
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('batches', 'issues', 'votes')"
        )
        assert len(cursor.fetchall()) == 0


def test_migration_versions_initial_schema_validation(temp_db: Path):
    """Test migration validation."""
    migration = InitialSchemaMigration()

    with sqlite3.connect(temp_db) as conn:
        # Should fail validation before migration
        assert not migration.validate(conn)

        # Apply migration
        migration.up(conn)

        # Should pass validation after migration
        assert migration.validate(conn)


def test_migration_versions_indexes_created(temp_db: Path):
    """Test that performance indexes are created."""
    migration = InitialSchemaMigration()

    with sqlite3.connect(temp_db) as conn:
        migration.up(conn)

        # Check that indexes were created
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        expected_indexes = {
            "idx_batches_status",
            "idx_issues_batch_id",
            "idx_votes_batch_id",
            "idx_votes_voter",
        }
        assert expected_indexes.issubset(indexes)

    """Test the add message_id migration (002)."""


def test_migration_versions_add_message_id_migration_properties():
    """Test migration basic properties."""
    migration = AddMessageIdMigration()
    assert migration.version == "002"
    assert "message_id" in migration.description.lower()
    assert migration.dependencies == ["001"]


def test_migration_versions_add_message_id_up_migration(temp_db: Path):
    """Test applying the add message_id migration."""
    # First apply initial schema
    initial_migration = InitialSchemaMigration()
    with sqlite3.connect(temp_db) as conn:
        initial_migration.up(conn)

    # Apply message_id migration
    migration = AddMessageIdMigration()
    with sqlite3.connect(temp_db) as conn:
        migration.up(conn)

        # Check that message_id column was added
        cursor = conn.execute("PRAGMA table_info(batches)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "message_id" in columns


def test_migration_versions_add_message_id_up_migration_idempotent(temp_db: Path):
    """Test that migration is idempotent (can be run multiple times)."""
    # Apply initial schema and message_id migration
    initial_migration = InitialSchemaMigration()
    migration = AddMessageIdMigration()

    with sqlite3.connect(temp_db) as conn:
        initial_migration.up(conn)
        migration.up(conn)

        # Apply again - should not fail
        migration.up(conn)

        # Column should still exist
        cursor = conn.execute("PRAGMA table_info(batches)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "message_id" in columns


def test_migration_versions_add_message_id_down_migration(temp_db: Path):
    """Test rolling back the add message_id migration."""
    # Apply initial schema and message_id migration
    initial_migration = InitialSchemaMigration()
    migration = AddMessageIdMigration()

    with sqlite3.connect(temp_db) as conn:
        initial_migration.up(conn)
        migration.up(conn)

        # Verify column exists
        cursor = conn.execute("PRAGMA table_info(batches)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "message_id" in columns

        # Rollback migration
        migration.down(conn)

        # Verify column was removed
        cursor = conn.execute("PRAGMA table_info(batches)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "message_id" not in columns


def test_migration_versions_add_message_id_validation(temp_db: Path):
    """Test migration validation."""
    initial_migration = InitialSchemaMigration()
    migration = AddMessageIdMigration()

    with sqlite3.connect(temp_db) as conn:
        initial_migration.up(conn)

        # Should fail validation before migration
        assert not migration.validate(conn)

        # Apply migration
        migration.up(conn)

        # Should pass validation after migration
        assert migration.validate(conn)

    """Test the batch voters migration (003)."""


def test_migration_versions_batch_voters_migration_properties():
    """Test migration basic properties."""
    migration = BatchVotersMigration()
    assert migration.version == "003"
    assert "batch_voters" in migration.description.lower()
    assert migration.dependencies == ["002"]


def test_migration_versions_batch_voters_up_migration(temp_db: Path):
    """Test applying the batch voters migration."""
    # Apply prerequisite migrations
    runner = MigrationRunner(temp_db)
    runner.register_migrations([InitialSchemaMigration, AddMessageIdMigration])
    runner.run_migrations()

    # Apply batch voters migration
    migration = BatchVotersMigration()
    with sqlite3.connect(temp_db) as conn:
        migration.up(conn)

        # Check that batch_voters table was created
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_voters'"
        )
        assert cursor.fetchone() is not None

        # Check table structure
        cursor = conn.execute("PRAGMA table_info(batch_voters)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {"id", "batch_id", "voter_name"}
        assert expected_columns.issubset(columns)


def test_migration_versions_batch_voters_down_migration(temp_db: Path):
    """Test rolling back the batch voters migration."""
    # Apply prerequisite migrations and batch voters migration
    runner = MigrationRunner(temp_db)
    runner.register_migrations(
        [InitialSchemaMigration, AddMessageIdMigration, BatchVotersMigration]
    )
    runner.run_migrations()

    migration = BatchVotersMigration()
    with sqlite3.connect(temp_db) as conn:
        # Verify table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_voters'"
        )
        assert cursor.fetchone() is not None

        # Rollback migration
        migration.down(conn)

        # Verify table was dropped
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_voters'"
        )
        assert cursor.fetchone() is None


def test_migration_versions_data_migration(temp_db: Path):
    """Test that existing batches get default voters."""
    # Apply prerequisite migrations
    runner = MigrationRunner(temp_db)
    runner.register_migrations([InitialSchemaMigration, AddMessageIdMigration])
    runner.run_migrations()

    # Create some test batches
    with sqlite3.connect(temp_db) as conn:
        conn.execute("""
            INSERT INTO batches (date, deadline, facilitator)
            VALUES ('2024-01-01', '2024-01-02T10:00:00', 'test_facilitator')
        """)
        conn.execute("""
            INSERT INTO batches (date, deadline, facilitator)
            VALUES ('2024-01-02', '2024-01-03T10:00:00', 'another_facilitator')
        """)
        conn.commit()

    # Apply batch voters migration
    migration = BatchVotersMigration()
    with sqlite3.connect(temp_db) as conn:
        migration.up(conn)

        # Check that default voters were added to existing batches
        cursor = conn.execute("SELECT COUNT(*) FROM batch_voters")
        voter_count = cursor.fetchone()[0]
        assert voter_count > 0  # Should have some default voters


def test_migration_versions_batch_voters_validation(temp_db: Path):
    """Test migration validation."""
    # Apply prerequisite migrations
    runner = MigrationRunner(temp_db)
    runner.register_migrations([InitialSchemaMigration, AddMessageIdMigration])
    runner.run_migrations()

    migration = BatchVotersMigration()
    with sqlite3.connect(temp_db) as conn:
        # Should fail validation before migration
        assert not migration.validate(conn)

        # Apply migration
        migration.up(conn)

        # Should pass validation after migration
        assert migration.validate(conn)

    """Test the final estimates migration (004)."""


def test_migration_versions_final_estimates_migration_properties():
    """Test migration basic properties."""
    migration = FinalEstimatesMigration()
    assert migration.version == "004"
    assert "final_estimates" in migration.description.lower()
    assert migration.dependencies == ["003"]


def test_migration_versions_final_estimates_up_migration(temp_db: Path):
    """Test applying the final estimates migration."""
    # Apply all prerequisite migrations
    runner = MigrationRunner(temp_db)
    runner.register_migrations(
        [InitialSchemaMigration, AddMessageIdMigration, BatchVotersMigration]
    )
    runner.run_migrations()

    # Apply final estimates migration
    migration = FinalEstimatesMigration()
    with sqlite3.connect(temp_db) as conn:
        migration.up(conn)

        # Check that final_estimates table was created
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='final_estimates'"
        )
        assert cursor.fetchone() is not None

        # Check table structure
        cursor = conn.execute("PRAGMA table_info(final_estimates)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {
            "id",
            "batch_id",
            "issue_number",
            "final_points",
            "rationale",
            "timestamp",
        }
        assert expected_columns.issubset(columns)


def test_migration_versions_final_estimates_down_migration(temp_db: Path):
    """Test rolling back the final estimates migration."""
    # Apply all migrations
    runner = MigrationRunner(temp_db)
    runner.register_migrations(ALL_MIGRATIONS)
    runner.run_migrations()

    migration = FinalEstimatesMigration()
    with sqlite3.connect(temp_db) as conn:
        # Verify table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='final_estimates'"
        )
        assert cursor.fetchone() is not None

        # Rollback migration
        migration.down(conn)

        # Verify table was dropped
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='final_estimates'"
        )
        assert cursor.fetchone() is None


def test_migration_versions_final_estimates_validation(temp_db: Path):
    """Test migration validation."""
    # Apply prerequisite migrations
    runner = MigrationRunner(temp_db)
    runner.register_migrations(
        [InitialSchemaMigration, AddMessageIdMigration, BatchVotersMigration]
    )
    runner.run_migrations()

    migration = FinalEstimatesMigration()
    with sqlite3.connect(temp_db) as conn:
        # Should fail validation before migration
        assert not migration.validate(conn)

        # Apply migration
        migration.up(conn)

        # Should pass validation after migration
        assert migration.validate(conn)


def test_migration_versions_final_estimates_indexes_created(temp_db: Path):
    """Test that performance indexes are created."""
    # Apply prerequisite migrations
    runner = MigrationRunner(temp_db)
    runner.register_migrations(
        [InitialSchemaMigration, AddMessageIdMigration, BatchVotersMigration]
    )
    runner.run_migrations()

    migration = FinalEstimatesMigration()
    with sqlite3.connect(temp_db) as conn:
        migration.up(conn)

        # Check that indexes were created
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_final_estimates_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        expected_indexes = {"idx_final_estimates_batch_id", "idx_final_estimates_issue"}
        assert expected_indexes.issubset(indexes)

    """Integration tests for all migrations together."""


def test_migration_versions_all_migrations_run_successfully(migration_runner: MigrationRunner):
    """Test that all migrations can be applied successfully."""
    applied = migration_runner.run_migrations()
    expected_versions = ["001", "002", "003", "004", "005", "006", "007", "008"]
    assert applied == expected_versions


def test_migration_versions_all_migrations_validate(migration_runner: MigrationRunner):
    """Test that all applied migrations validate successfully."""
    migration_runner.run_migrations()
    assert migration_runner.validate_migrations() is True


def test_migration_versions_migration_order_dependency(migration_runner: MigrationRunner):
    """Test that migrations are applied in correct dependency order."""
    # Get pending migrations
    pending = migration_runner.get_pending_migrations()

    # Verify they are in correct order
    versions = [m.version for m in pending]
    assert versions == ["001", "002", "003", "004", "005", "006", "007", "008"]


def test_migration_versions_complete_schema_after_all_migrations(temp_db: Path):
    """Test that the complete schema is correct after all migrations."""
    runner = MigrationRunner(temp_db)
    runner.register_migrations(ALL_MIGRATIONS)
    runner.run_migrations()

    with sqlite3.connect(temp_db) as conn:
        # Check all expected tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}
        expected_tables = {
            "batches",
            "issues",
            "votes",
            "batch_voters",
            "final_estimates",
            "schema_migrations",
        }
        assert expected_tables.issubset(tables)

        # Check batches table has all expected columns
        cursor = conn.execute("PRAGMA table_info(batches)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {
            "id",
            "date",
            "deadline",
            "facilitator",
            "status",
            "created_at",
            "message_id",
        }
        assert expected_columns.issubset(columns)


def test_migration_versions_rollback_all_migrations(migration_runner: MigrationRunner):
    """Test rolling back all migrations in reverse order."""
    # Apply all migrations
    migration_runner.run_migrations()

    # Rollback in reverse order
    versions_to_rollback = ["008", "007", "006", "005", "004", "003", "002", "001"]
    for version in versions_to_rollback:
        migration_runner.rollback_migration(version)

    # Verify no migrations are applied
    applied = migration_runner.get_applied_migrations()
    assert len(applied) == 0

    # Verify only schema_migrations table remains (and sqlite_sequence which is auto-created)
    with sqlite3.connect(migration_runner.db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT IN ('schema_migrations', 'sqlite_sequence')"
        )
        remaining_tables = cursor.fetchall()
        assert len(remaining_tables) == 0


def test_migration_versions_partial_rollback_and_reapply(migration_runner: MigrationRunner):
    """Test partial rollback and reapplying migrations."""
    # Apply all migrations
    migration_runner.run_migrations()

    # Rollback last two migrations
    migration_runner.rollback_migration("004")
    migration_runner.rollback_migration("003")

    # Verify state
    applied = migration_runner.get_applied_migrations()
    assert applied == {"001", "002", "005", "006", "007", "008"}

    # Reapply migrations
    reapplied = migration_runner.run_migrations()
    assert reapplied == ["003", "004"]

    # Verify final state
    final_applied = migration_runner.get_applied_migrations()
    assert final_applied == {"001", "002", "003", "004", "005", "006", "007", "008"}
