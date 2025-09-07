"""Add message_id column to batches table."""

import sqlite3

from ..base import Migration, SchemaValidationMixin


class AddMessageIdMigration(Migration, SchemaValidationMixin):
    """Add message_id column to track Zulip message IDs for batches."""

    @property
    def version(self) -> str:
        return "002"

    @property
    def description(self) -> str:
        return "Add message_id column to batches table"

    def up(self, conn: sqlite3.Connection) -> None:
        """Add message_id column to batches table."""
        # Check if column already exists (for safety)
        if not self.column_exists(conn, "batches", "message_id"):
            self.execute_sql(conn, "ALTER TABLE batches ADD COLUMN message_id INTEGER")

    def down(self, conn: sqlite3.Connection) -> None:
        """Remove message_id column from batches table.

        Note: SQLite doesn't support DROP COLUMN directly, so we need to recreate the table.
        """
        # Create new table without message_id column
        self.execute_sql(
            conn,
            """
            CREATE TABLE batches_new (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                deadline TEXT NOT NULL,
                facilitator TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        )

        # Copy data from old table (excluding message_id)
        self.execute_sql(
            conn,
            """
            INSERT INTO batches_new (id, date, deadline, facilitator, status, created_at)
            SELECT id, date, deadline, facilitator, status, created_at
            FROM batches
        """,
        )

        # Drop old table and rename new one
        self.execute_sql(conn, "DROP TABLE batches")
        self.execute_sql(conn, "ALTER TABLE batches_new RENAME TO batches")

        # Recreate index
        self.execute_sql(conn, "CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status)")

    def validate(self, conn: sqlite3.Connection) -> bool:
        """Validate that message_id column was added."""
        return self.column_exists(conn, "batches", "message_id")
