"""Add batch_reminders table to track sent reminders."""

import sqlite3

from ..base import Migration, SchemaValidationMixin


class AddRemindersMigration(Migration, SchemaValidationMixin):
    """Add batch_reminders table to track which reminders have been sent."""

    @property
    def version(self) -> str:
        return "007"

    @property
    def description(self) -> str:
        return "Add batch_reminders table to track sent reminders"

    def up(self, conn: sqlite3.Connection) -> None:
        """Create batch_reminders table."""
        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS batch_reminders (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches (id),
                UNIQUE(batch_id, reminder_type)
            )
        """,
        )

        self.execute_sql(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_batch_reminders_batch_id ON batch_reminders(batch_id)",
        )

    def down(self, conn: sqlite3.Connection) -> None:
        """Drop batch_reminders table."""
        self.execute_sql(conn, "DROP TABLE IF EXISTS batch_reminders")

    def validate(self, conn: sqlite3.Connection) -> bool:
        """Validate that batch_reminders table was created."""
        if not self.table_exists(conn, "batch_reminders"):
            return False

        schema = self.get_table_schema(conn, "batch_reminders")
        required_columns = {"id", "batch_id", "reminder_type", "sent_at"}
        actual_columns = {col["name"] for col in schema}

        return required_columns.issubset(actual_columns)
