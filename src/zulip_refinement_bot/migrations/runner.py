from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import structlog

from .base import Migration, MigrationError

logger = structlog.get_logger(__name__)


class MigrationRunner:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._migrations: dict[str, Migration] = {}
        self._ensure_migration_table()

    def register_migration(self, migration_class: type[Migration]) -> None:
        migration = migration_class()
        version = migration.version

        if version in self._migrations:
            raise MigrationError(f"Migration {version} is already registered")

        self._migrations[version] = migration
        logger.debug("Registered migration", version=version, description=migration.description)

    def register_migrations(self, migration_classes: list[type[Migration]]) -> None:
        for migration_class in migration_classes:
            self.register_migration(migration_class)

    def _ensure_migration_table(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TIMESTAMP NOT NULL,
                    execution_time_ms INTEGER
                )
            """)
            conn.commit()

    def get_applied_migrations(self) -> set[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
            return {row[0] for row in cursor.fetchall()}

    def get_pending_migrations(self) -> list[Migration]:
        applied = self.get_applied_migrations()
        pending: list[Migration] = []

        sorted_migrations = sorted(self._migrations.items())

        for version, migration in sorted_migrations:
            if version not in applied:
                for dep_version in migration.dependencies:
                    if dep_version not in applied and dep_version not in [
                        m.version for m in pending
                    ]:
                        if dep_version in self._migrations:
                            dep_migration = self._migrations[dep_version]
                            if dep_migration not in pending:
                                pending.append(dep_migration)
                        else:
                            raise MigrationError(
                                f"Migration {version} depends on {dep_version} "
                                f"which is not registered"
                            )

                pending.append(migration)

        return pending

    def run_migrations(self, target_version: str | None = None, dry_run: bool = False) -> list[str]:
        pending = self.get_pending_migrations()

        if target_version:
            pending = [m for m in pending if m.version <= target_version]

        if not pending:
            logger.info("No pending migrations to run")
            return []

        applied_versions = []

        for migration in pending:
            if dry_run:
                logger.info(
                    "Would apply migration",
                    version=migration.version,
                    description=migration.description,
                )
                applied_versions.append(migration.version)
            else:
                applied_versions.append(self._apply_migration(migration))

        logger.info("Migrations completed", migrations_count=len(applied_versions))
        return applied_versions

    def _apply_migration(self, migration: Migration) -> str:
        start_time = datetime.now()

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                logger.info(
                    "Applying migration",
                    version=migration.version,
                    description=migration.description,
                )

                migration.up(conn)

                if not migration.validate(conn):
                    raise MigrationError(f"Migration {migration.version} validation failed")

                execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
                migration.applied_at = datetime.now()

                conn.execute(
                    """
                    INSERT INTO schema_migrations
                    (version, description, applied_at, execution_time_ms)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        migration.version,
                        migration.description,
                        migration.applied_at.isoformat(),
                        execution_time,
                    ),
                )

                conn.commit()
                logger.info(
                    "Migration applied successfully",
                    version=migration.version,
                    execution_time_ms=execution_time,
                )
                return migration.version

        except Exception as e:
            logger.error("Migration failed", version=migration.version, error=str(e))
            raise MigrationError(f"Migration {migration.version} failed: {e}") from e

    def rollback_migration(self, version: str) -> None:
        if version not in self._migrations:
            raise MigrationError(f"Migration {version} is not registered")

        migration = self._migrations[version]

        if not migration.can_rollback():
            raise MigrationError(f"Migration {version} does not support rollback")

        applied = self.get_applied_migrations()
        if version not in applied:
            raise MigrationError(f"Migration {version} is not applied")

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                logger.info("Rolling back migration", version=version)

                migration.down(conn)
                conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
                conn.commit()

                logger.info("Migration rolled back successfully", version=version)

        except Exception as e:
            logger.error("Migration rollback failed", version=version, error=str(e))
            raise MigrationError(f"Rollback of migration {version} failed: {e}") from e

    def get_migration_status(self) -> dict[str, dict]:
        applied = self.get_applied_migrations()
        status = {}

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT version, description, applied_at, execution_time_ms
                FROM schema_migrations
                ORDER BY version
            """)
            applied_details = {row["version"]: dict(row) for row in cursor.fetchall()}

        for version, migration in sorted(self._migrations.items()):
            if version in applied:
                details = applied_details.get(version, {})
                status[version] = {
                    "status": "applied",
                    "description": migration.description,
                    "applied_at": details.get("applied_at"),
                    "execution_time_ms": details.get("execution_time_ms"),
                    "can_rollback": migration.can_rollback(),
                }
            else:
                status[version] = {
                    "status": "pending",
                    "description": migration.description,
                    "dependencies": migration.dependencies,
                    "can_rollback": migration.can_rollback(),
                }

        return status

    def validate_migrations(self) -> bool:
        applied = self.get_applied_migrations()
        all_valid = True

        with sqlite3.connect(self.db_path) as conn:
            for version in applied:
                if version in self._migrations:
                    migration = self._migrations[version]
                    try:
                        if not migration.validate(conn):
                            logger.error("Migration validation failed", version=version)
                            all_valid = False
                    except Exception as e:
                        logger.error("Migration validation error", version=version, error=str(e))
                        all_valid = False
                else:
                    logger.warning("Applied migration not found in registry", version=version)

        return all_valid
