"""Tests for the database migration system."""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from src.zulip_refinement_bot.migrations.base import (
    Migration,
    MigrationError,
    SchemaValidationMixin,
)
from src.zulip_refinement_bot.migrations.runner import MigrationRunner


class MockMigration(Migration, SchemaValidationMixin):
    """Mock migration for unit testing."""

    def __init__(self, version: str, description: str, should_fail: bool = False):
        super().__init__()
        self._version = version
        self._description = description
        self._should_fail = should_fail
        self._up_called = False
        self._down_called = False
        self._validate_called = False

    @property
    def version(self) -> str:
        return self._version

    @property
    def description(self) -> str:
        return self._description

    def up(self, conn: sqlite3.Connection) -> None:
        """Test migration up method."""
        self._up_called = True
        if self._should_fail:
            raise MigrationError("Test migration failure")

        # Create a simple test table
        self.execute_sql(
            conn,
            f"""
            CREATE TABLE IF NOT EXISTS test_table_{self.version} (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """,
        )

    def down(self, conn: sqlite3.Connection) -> None:
        """Test migration down method."""
        self._down_called = True
        self.execute_sql(conn, f"DROP TABLE IF EXISTS test_table_{self.version}")

    def validate(self, conn: sqlite3.Connection) -> bool:
        """Test migration validation."""
        self._validate_called = True
        return self.table_exists(conn, f"test_table_{self.version}")


class MockMigrationWithoutRollback(Migration):
    """Mock migration without rollback support."""

    def __init__(self, version: str):
        super().__init__()
        self._version = version

    @property
    def version(self) -> str:
        return self._version

    @property
    def description(self) -> str:
        return "Test migration without rollback"

    def up(self, conn: sqlite3.Connection) -> None:
        """Simple up migration."""
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS no_rollback_{self.version} (
                id INTEGER PRIMARY KEY
            )
        """)


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
    return MigrationRunner(temp_db)


def test_migrations_migration_properties():
    """Test migration basic properties."""
    migration = MockMigration("001", "Test migration")
    assert migration.version == "001"
    assert migration.description == "Test migration"
    assert migration.dependencies == []


def test_migrations_migration_dependencies_default():
    """Test default dependency calculation."""
    migration = MockMigration("005", "Test migration")
    assert migration.dependencies == ["004"]


def test_migrations_migration_string_representation():
    """Test string representations."""
    migration = MockMigration("001", "Test migration")
    assert str(migration) == "Migration 001: Test migration"
    assert "Migration(version='001'" in repr(migration)


def test_migrations_can_rollback_detection():
    """Test rollback capability detection."""
    migration_with_rollback = MockMigration("001", "With rollback")
    migration_without_rollback = MockMigrationWithoutRollback("002")

    assert migration_with_rollback.can_rollback()
    assert not migration_without_rollback.can_rollback()


def test_migrations_schema_validation_mixin(temp_db: Path):
    """Test schema validation utilities."""
    migration = MockMigration("001", "Test migration")

    with sqlite3.connect(temp_db) as conn:
        # Test table_exists
        assert not migration.table_exists(conn, "nonexistent_table")

        # Create a table and test again
        conn.execute("CREATE TABLE test_table (id INTEGER)")
        assert migration.table_exists(conn, "test_table")

        # Test column_exists
        assert migration.column_exists(conn, "test_table", "id")
        assert not migration.column_exists(conn, "test_table", "nonexistent_column")

        # Test get_table_schema
        schema = migration.get_table_schema(conn, "test_table")
        assert len(schema) == 1
        assert schema[0]["name"] == "id"
        assert schema[0]["type"] == "INTEGER"


def test_migrations_execute_sql_error_handling(temp_db: Path):
    """Test SQL execution error handling."""
    migration = MockMigration("001", "Test migration")

    with sqlite3.connect(temp_db) as conn:
        with pytest.raises(MigrationError):
            migration.execute_sql(conn, "INVALID SQL SYNTAX")


class MockMigrationRunner:
    """Test the MigrationRunner class."""


def test_migrations_runner_initialization(migration_runner: MigrationRunner):
    """Test runner initialization."""
    assert migration_runner.db_path.exists()

    # Check that schema_migrations table was created
    with sqlite3.connect(migration_runner.db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        assert cursor.fetchone() is not None


def test_migrations_register_migration(migration_runner: MigrationRunner):
    """Test migration registration."""

    class SingleMockMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Test migration")

    migration_runner.register_migration(SingleMockMigration)

    assert "001" in migration_runner._migrations


def test_migrations_register_duplicate_migration(migration_runner: MigrationRunner):
    """Test registering duplicate migration versions."""

    class DuplicateMockMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Duplicate migration")

    migration_runner.register_migration(DuplicateMockMigration)

    with pytest.raises(MigrationError, match="already registered"):
        migration_runner.register_migration(DuplicateMockMigration)


def test_migrations_get_applied_migrations_empty(migration_runner: MigrationRunner):
    """Test getting applied migrations when none exist."""
    applied = migration_runner.get_applied_migrations()
    assert applied == set()


def test_migrations_get_pending_migrations_empty(migration_runner: MigrationRunner):
    """Test getting pending migrations when none registered."""
    pending = migration_runner.get_pending_migrations()
    assert pending == []


def test_migrations_run_migrations_empty(migration_runner: MigrationRunner):
    """Test running migrations when none are registered."""
    applied = migration_runner.run_migrations()
    assert applied == []


def test_migrations_run_single_migration(migration_runner: MigrationRunner):
    """Test running a single migration."""

    # Create and register a test migration
    class SingleMockMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Single test migration")

    migration_runner.register_migration(SingleMockMigration)

    # Run migrations
    applied = migration_runner.run_migrations()
    assert applied == ["001"]

    # Check that migration was recorded
    applied_set = migration_runner.get_applied_migrations()
    assert "001" in applied_set

    # Check that table was created
    with sqlite3.connect(migration_runner.db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table_001'"
        )
        assert cursor.fetchone() is not None


def test_migrations_run_multiple_migrations_in_order(migration_runner: MigrationRunner):
    """Test running multiple migrations in correct order."""

    # Create test migrations
    class Migration001(MockMigration):
        def __init__(self):
            super().__init__("001", "First migration")

    class Migration002(MockMigration):
        def __init__(self):
            super().__init__("002", "Second migration")

    class Migration003(MockMigration):
        def __init__(self):
            super().__init__("003", "Third migration")

    # Register in random order
    migration_runner.register_migration(Migration003)
    migration_runner.register_migration(Migration001)
    migration_runner.register_migration(Migration002)

    # Run migrations
    applied = migration_runner.run_migrations()
    assert applied == ["001", "002", "003"]


def test_migrations_run_migrations_with_target_version(migration_runner: MigrationRunner):
    """Test running migrations up to a target version."""

    # Create test migrations
    class Migration001(MockMigration):
        def __init__(self):
            super().__init__("001", "First migration")

    class Migration002(MockMigration):
        def __init__(self):
            super().__init__("002", "Second migration")

    class Migration003(MockMigration):
        def __init__(self):
            super().__init__("003", "Third migration")

    migration_runner.register_migrations([Migration001, Migration002, Migration003])

    # Run migrations up to version 002
    applied = migration_runner.run_migrations(target_version="002")
    assert applied == ["001", "002"]

    # Verify only first two migrations were applied
    applied_set = migration_runner.get_applied_migrations()
    assert applied_set == {"001", "002"}


def test_migrations_dry_run_migrations(migration_runner: MigrationRunner):
    """Test dry run functionality."""

    class DryRunMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Dry run migration")

    migration_runner.register_migration(DryRunMigration)

    # Run dry run
    applied = migration_runner.run_migrations(dry_run=True)
    assert applied == ["001"]

    # Verify no migrations were actually applied
    applied_set = migration_runner.get_applied_migrations()
    assert applied_set == set()


def test_migrations_migration_failure_handling(migration_runner: MigrationRunner):
    """Test handling of migration failures."""

    class FailingMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Failing migration", should_fail=True)

    migration_runner.register_migration(FailingMigration)

    # Migration should fail
    with pytest.raises(MigrationError):
        migration_runner.run_migrations()

    # Verify no migrations were recorded as applied
    applied_set = migration_runner.get_applied_migrations()
    assert applied_set == set()


def test_migrations_rollback_migration(migration_runner: MigrationRunner):
    """Test rolling back a migration."""

    class RollbackMockMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Rollback test migration")

    migration_runner.register_migration(RollbackMockMigration)

    # Apply migration
    migration_runner.run_migrations()
    assert "001" in migration_runner.get_applied_migrations()

    # Rollback migration
    migration_runner.rollback_migration("001")
    assert "001" not in migration_runner.get_applied_migrations()

    # Verify table was dropped
    with sqlite3.connect(migration_runner.db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table_001'"
        )
        assert cursor.fetchone() is None


def test_migrations_rollback_nonexistent_migration(migration_runner: MigrationRunner):
    """Test rolling back a migration that doesn't exist."""
    with pytest.raises(MigrationError, match="not registered"):
        migration_runner.rollback_migration("999")


def test_migrations_rollback_unapplied_migration(migration_runner: MigrationRunner):
    """Test rolling back a migration that wasn't applied."""

    class UnAppliedMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Unapplied migration")

    migration_runner.register_migration(UnAppliedMigration)

    with pytest.raises(MigrationError, match="not applied"):
        migration_runner.rollback_migration("001")


def test_migrations_rollback_unsupported_migration(migration_runner: MigrationRunner):
    """Test rolling back a migration that doesn't support rollback."""

    class NoRollbackMigration(MockMigrationWithoutRollback):
        def __init__(self):
            super().__init__("001")

    migration_runner.register_migration(NoRollbackMigration)

    # Apply migration
    migration_runner.run_migrations()

    # Try to rollback
    with pytest.raises(MigrationError, match="does not support rollback"):
        migration_runner.rollback_migration("001")


def test_migrations_get_migration_status(migration_runner: MigrationRunner):
    """Test getting migration status."""

    class StatusMockMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Status test migration")

    migration_runner.register_migration(StatusMockMigration)

    # Check status before applying
    status = migration_runner.get_migration_status()
    assert "001" in status
    assert status["001"]["status"] == "pending"
    assert status["001"]["description"] == "Status test migration"
    assert status["001"]["can_rollback"] is True

    # Apply migration
    migration_runner.run_migrations()

    # Check status after applying
    status = migration_runner.get_migration_status()
    assert status["001"]["status"] == "applied"
    assert "applied_at" in status["001"]
    assert "execution_time_ms" in status["001"]


def test_migrations_validate_migrations(migration_runner: MigrationRunner):
    """Test migration validation."""

    class ValidatableMockMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Validatable migration")

    migration_runner.register_migration(ValidatableMockMigration)

    # Apply migration
    migration_runner.run_migrations()

    # Validate migrations
    is_valid = migration_runner.validate_migrations()
    assert is_valid is True


def test_migrations_validate_migrations_with_failure(migration_runner: MigrationRunner):
    """Test migration validation with validation failure."""

    class FailingValidationMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Failing validation migration")

        def validate(self, conn: sqlite3.Connection) -> bool:
            return False  # Always fail validation

    migration_runner.register_migration(FailingValidationMigration)

    # Apply migration should fail due to validation
    with pytest.raises(MigrationError, match="validation failed"):
        migration_runner.run_migrations()


def test_migrations_migration_dependencies(migration_runner: MigrationRunner):
    """Test migration dependency handling."""

    class Migration001(MockMigration):
        def __init__(self):
            super().__init__("001", "Base migration")

    class Migration002(MockMigration):
        def __init__(self):
            super().__init__("002", "Dependent migration")

        @property
        def dependencies(self) -> list[str]:
            return ["001"]

    # Register only the dependent migration
    migration_runner.register_migration(Migration002)

    # Should fail due to missing dependency
    with pytest.raises(MigrationError, match="depends on 001 which is not registered"):
        migration_runner.run_migrations()


def test_migrations_migration_execution_time_tracking(migration_runner: MigrationRunner):
    """Test that migration execution time is tracked."""

    class TimedMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Timed migration")

        def up(self, conn: sqlite3.Connection) -> None:
            super().up(conn)
            # Add a small delay to ensure measurable execution time
            import time

            time.sleep(0.01)

    migration_runner.register_migration(TimedMigration)
    migration_runner.run_migrations()

    # Check that execution time was recorded
    with sqlite3.connect(migration_runner.db_path) as conn:
        cursor = conn.execute(
            "SELECT execution_time_ms FROM schema_migrations WHERE version = '001'"
        )
        result = cursor.fetchone()
        assert result is not None
        assert result[0] > 0  # Should have some execution time


class MockMigrationIntegration:
    """Integration tests for the migration system."""


def test_migrations_migration_system_end_to_end(temp_db: Path):
    """Test complete migration system workflow."""
    runner = MigrationRunner(temp_db)

    # Define a series of migrations
    class CreateUsersTable(Migration, SchemaValidationMixin):
        @property
        def version(self) -> str:
            return "001"

        @property
        def description(self) -> str:
            return "Create users table"

        def up(self, conn: sqlite3.Connection) -> None:
            self.execute_sql(
                conn,
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            )

        def down(self, conn: sqlite3.Connection) -> None:
            self.execute_sql(conn, "DROP TABLE users")

        def validate(self, conn: sqlite3.Connection) -> bool:
            return self.table_exists(conn, "users") and self.column_exists(conn, "users", "email")

    class AddUserNameColumn(Migration, SchemaValidationMixin):
        @property
        def version(self) -> str:
            return "002"

        @property
        def description(self) -> str:
            return "Add name column to users table"

        def up(self, conn: sqlite3.Connection) -> None:
            self.execute_sql(conn, "ALTER TABLE users ADD COLUMN name TEXT")

        def down(self, conn: sqlite3.Connection) -> None:
            # SQLite doesn't support DROP COLUMN, so recreate table
            self.execute_sql(
                conn,
                """
                CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            )
            self.execute_sql(
                conn,
                """
                INSERT INTO users_new (id, email, created_at)
                SELECT id, email, created_at FROM users
            """,
            )
            self.execute_sql(conn, "DROP TABLE users")
            self.execute_sql(conn, "ALTER TABLE users_new RENAME TO users")

        def validate(self, conn: sqlite3.Connection) -> bool:
            return self.column_exists(conn, "users", "name")

    # Register migrations
    runner.register_migrations([CreateUsersTable, AddUserNameColumn])

    # Run migrations
    applied = runner.run_migrations()
    assert applied == ["001", "002"]

    # Verify final state
    with sqlite3.connect(temp_db) as conn:
        # Check users table exists with correct columns
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}
        assert columns == {"id", "email", "created_at", "name"}

    # Test rollback
    runner.rollback_migration("002")

    # Verify rollback worked
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}
        assert columns == {"id", "email", "created_at"}
        assert "name" not in columns

    # Validate remaining migrations
    assert runner.validate_migrations() is True


def test_migrations_concurrent_migration_safety(temp_db: Path):
    """Test that migrations are safe from concurrent execution."""
    # This is a basic test - in production you'd want more sophisticated testing
    runner1 = MigrationRunner(temp_db)
    runner2 = MigrationRunner(temp_db)

    class ConcurrentMockMigration(MockMigration):
        def __init__(self):
            super().__init__("001", "Concurrent test migration")

    runner1.register_migration(ConcurrentMockMigration)
    runner2.register_migration(ConcurrentMockMigration)

    # Run migration on first runner
    applied1 = runner1.run_migrations()
    assert applied1 == ["001"]

    # Second runner should see no pending migrations
    applied2 = runner2.run_migrations()
    assert applied2 == []
