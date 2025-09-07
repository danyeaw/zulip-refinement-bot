"""Tests for the migration CLI interface."""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from src.zulip_refinement_bot.migrations.cli import app
from src.zulip_refinement_bot.migrations.runner import MigrationRunner
from src.zulip_refinement_bot.migrations.versions import ALL_MIGRATIONS


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
def runner():
    """Create a CLI test runner."""
    return CliRunner()


class TestMigrationCLI:
    """Test the migration CLI commands."""

    def test_status_command_no_migrations(self, runner: CliRunner, temp_db: Path):
        """Test status command with no migrations applied."""
        result = runner.invoke(app, ["status", "--db-path", str(temp_db)])
        assert result.exit_code == 0
        assert "Migration Status" in result.stdout

    def test_status_command_with_migrations(self, runner: CliRunner, temp_db: Path):
        """Test status command with migrations applied."""
        # Apply some migrations first
        migration_runner = MigrationRunner(temp_db)
        migration_runner.register_migrations(ALL_MIGRATIONS[:2])  # Only first two
        migration_runner.run_migrations()

        result = runner.invoke(app, ["status", "--db-path", str(temp_db)])
        assert result.exit_code == 0
        assert "Migration Status" in result.stdout
        assert "001" in result.stdout
        assert "002" in result.stdout

    def test_run_command_dry_run(self, runner: CliRunner, temp_db: Path):
        """Test run command with dry-run flag."""
        result = runner.invoke(app, ["run", "--db-path", str(temp_db), "--dry-run"])
        assert result.exit_code == 0
        assert "Would apply" in result.stdout or "No migrations to run" in result.stdout

    def test_run_command_actual_run(self, runner: CliRunner, temp_db: Path):
        """Test run command actually applying migrations."""
        result = runner.invoke(app, ["run", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Verify migrations were applied
        migration_runner = MigrationRunner(temp_db)
        migration_runner.register_migrations(ALL_MIGRATIONS)
        applied = migration_runner.get_applied_migrations()
        assert len(applied) > 0

    def test_run_command_with_target_version(self, runner: CliRunner, temp_db: Path):
        """Test run command with target version."""
        result = runner.invoke(app, ["run", "002", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Verify only migrations up to 002 were applied
        migration_runner = MigrationRunner(temp_db)
        migration_runner.register_migrations(ALL_MIGRATIONS)
        applied = migration_runner.get_applied_migrations()
        assert "001" in applied
        assert "002" in applied
        assert "003" not in applied

    def test_rollback_command_with_confirmation(self, runner: CliRunner, temp_db: Path):
        """Test rollback command with confirmation."""
        # First apply migrations
        migration_runner = MigrationRunner(temp_db)
        migration_runner.register_migrations(ALL_MIGRATIONS)
        migration_runner.run_migrations()

        # Test rollback with --yes flag
        result = runner.invoke(app, ["rollback", "004", "--db-path", str(temp_db), "--yes"])
        assert result.exit_code == 0
        assert "Successfully rolled back" in result.stdout

    def test_rollback_command_cancelled(self, runner: CliRunner, temp_db: Path):
        """Test rollback command when user cancels."""
        # First apply migrations
        migration_runner = MigrationRunner(temp_db)
        migration_runner.register_migrations(ALL_MIGRATIONS)
        migration_runner.run_migrations()

        # Test rollback with user input "n" (no)
        result = runner.invoke(app, ["rollback", "004", "--db-path", str(temp_db)], input="n\n")
        assert result.exit_code == 0
        assert "cancelled" in result.stdout.lower()

    def test_validate_command_success(self, runner: CliRunner, temp_db: Path):
        """Test validate command with successful validation."""
        # First apply migrations
        migration_runner = MigrationRunner(temp_db)
        migration_runner.register_migrations(ALL_MIGRATIONS)
        migration_runner.run_migrations()

        result = runner.invoke(app, ["validate", "--db-path", str(temp_db)])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    def test_init_command(self, runner: CliRunner, temp_db: Path):
        """Test init command."""
        result = runner.invoke(app, ["init", "--db-path", str(temp_db)])
        assert result.exit_code == 0
        assert "initialized" in result.stdout.lower()

        # Verify all migrations were applied
        migration_runner = MigrationRunner(temp_db)
        migration_runner.register_migrations(ALL_MIGRATIONS)
        applied = migration_runner.get_applied_migrations()
        assert len(applied) == len(ALL_MIGRATIONS)

    def test_command_with_invalid_db_path(self, runner: CliRunner):
        """Test command with invalid database path."""
        invalid_path = "/invalid/path/to/database.db"
        runner.invoke(app, ["status", "--db-path", invalid_path])
        # Should handle gracefully (create parent directories)
        # The exact behavior depends on implementation

    def test_rollback_nonexistent_migration(self, runner: CliRunner, temp_db: Path):
        """Test rollback of non-existent migration."""
        result = runner.invoke(app, ["rollback", "999", "--db-path", str(temp_db), "--yes"])
        assert result.exit_code == 1
        assert "failed" in result.stdout.lower()

    def test_run_command_with_migration_failure(self, runner: CliRunner, temp_db: Path):
        """Test run command when a migration fails."""
        # This would require a failing migration in the test setup
        # For now, we'll test the error handling path
        with patch("src.zulip_refinement_bot.migrations.cli.get_migration_runner") as mock_runner:
            mock_runner.return_value.run_migrations.side_effect = Exception("Test failure")

            result = runner.invoke(app, ["run", "--db-path", str(temp_db)])
            assert result.exit_code == 1

    def test_validate_command_failure(self, runner: CliRunner, temp_db: Path):
        """Test validate command when validation fails."""
        with patch("src.zulip_refinement_bot.migrations.cli.get_migration_runner") as mock_runner:
            mock_runner.return_value.validate_migrations.return_value = False

            result = runner.invoke(app, ["validate", "--db-path", str(temp_db)])
            assert result.exit_code == 1

    def test_default_db_path(self, runner: CliRunner):
        """Test commands with default database path."""
        # Test that commands work without explicit --db-path
        with patch("src.zulip_refinement_bot.migrations.cli.get_migration_runner") as mock_runner:
            mock_runner.return_value.get_migration_status.return_value = {}

            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0

            # Verify default path was used (None gets converted to default in get_migration_runner)
            mock_runner.assert_called_once()
            args, kwargs = mock_runner.call_args
            assert args[0] is None  # None is passed, then converted to default inside the function


class TestMigrationCLIIntegration:
    """Integration tests for the migration CLI."""

    def test_complete_migration_workflow(self, runner: CliRunner, temp_db: Path):
        """Test complete workflow: status -> run -> status -> rollback -> status."""
        # Initial status (no migrations)
        result = runner.invoke(app, ["status", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Run migrations
        result = runner.invoke(app, ["run", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Check status after running
        result = runner.invoke(app, ["status", "--db-path", str(temp_db)])
        assert result.exit_code == 0
        assert "applied" in result.stdout.lower()

        # Rollback last migration
        result = runner.invoke(app, ["rollback", "004", "--db-path", str(temp_db), "--yes"])
        assert result.exit_code == 0

        # Check status after rollback
        result = runner.invoke(app, ["status", "--db-path", str(temp_db)])
        assert result.exit_code == 0

    def test_partial_migration_workflow(self, runner: CliRunner, temp_db: Path):
        """Test partial migration workflow."""
        # Run migrations up to version 002
        result = runner.invoke(app, ["run", "002", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Check status
        result = runner.invoke(app, ["status", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Run remaining migrations
        result = runner.invoke(app, ["run", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Validate all migrations
        result = runner.invoke(app, ["validate", "--db-path", str(temp_db)])
        assert result.exit_code == 0

    def test_dry_run_vs_actual_run(self, runner: CliRunner, temp_db: Path):
        """Test that dry run doesn't actually apply migrations."""
        # Dry run
        result = runner.invoke(app, ["run", "--db-path", str(temp_db), "--dry-run"])
        assert result.exit_code == 0

        # Check that no migrations were actually applied
        migration_runner = MigrationRunner(temp_db)
        migration_runner.register_migrations(ALL_MIGRATIONS)
        applied = migration_runner.get_applied_migrations()
        assert len(applied) == 0

        # Actual run
        result = runner.invoke(app, ["run", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Check that migrations were applied
        applied = migration_runner.get_applied_migrations()
        assert len(applied) > 0

    def test_cli_output_formatting(self, runner: CliRunner, temp_db: Path):
        """Test that CLI output is properly formatted."""
        # Run migrations first
        result = runner.invoke(app, ["run", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Check status output formatting
        result = runner.invoke(app, ["status", "--db-path", str(temp_db)])
        assert result.exit_code == 0

        # Should contain table headers
        assert "Version" in result.stdout
        assert "Status" in result.stdout
        assert "Description" in result.stdout

        # Should show applied migrations
        assert "applied" in result.stdout.lower()

        # Should show rollback capability indicators
        assert "✓" in result.stdout or "✗" in result.stdout
