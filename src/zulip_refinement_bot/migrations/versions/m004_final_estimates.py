"""Add final_estimates table for storing discussion results."""

import sqlite3

from ..base import Migration, SchemaValidationMixin


class FinalEstimatesMigration(Migration, SchemaValidationMixin):
    """Create final_estimates table for storing final estimates after discussion."""

    @property
    def version(self) -> str:
        return "004"

    @property
    def description(self) -> str:
        return "Add final_estimates table for discussion results"

    def up(self, conn: sqlite3.Connection) -> None:
        """Create final_estimates table."""
        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS final_estimates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                issue_number TEXT NOT NULL,
                final_points INTEGER NOT NULL,
                rationale TEXT DEFAULT '',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches (id),
                UNIQUE(batch_id, issue_number)
            )
        """,
        )

        # Create indexes for better performance
        self.execute_sql(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_final_estimates_batch_id ON final_estimates(batch_id)",
        )
        self.execute_sql(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_final_estimates_issue ON final_estimates(issue_number)",
        )

    def down(self, conn: sqlite3.Connection) -> None:
        """Drop final_estimates table."""
        self.execute_sql(conn, "DROP TABLE IF EXISTS final_estimates")

    def validate(self, conn: sqlite3.Connection) -> bool:
        """Validate that final_estimates table was created correctly."""
        if not self.table_exists(conn, "final_estimates"):
            return False

        # Validate table structure
        schema = self.get_table_schema(conn, "final_estimates")
        required_columns = {
            "id",
            "batch_id",
            "issue_number",
            "final_points",
            "rationale",
            "timestamp",
        }
        actual_columns = {col["name"] for col in schema}

        return required_columns.issubset(actual_columns)
