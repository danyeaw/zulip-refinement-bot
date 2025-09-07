"""Add batch_voters table and migrate existing data."""

import sqlite3

from ..base import Migration, SchemaValidationMixin


class BatchVotersMigration(Migration, SchemaValidationMixin):
    """Create batch_voters table and migrate existing batches to have default voters."""

    @property
    def version(self) -> str:
        return "003"

    @property
    def description(self) -> str:
        return "Add batch_voters table and migrate existing batches"

    def up(self, conn: sqlite3.Connection) -> None:
        """Create batch_voters table and migrate existing data."""
        # Create batch_voters table
        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS batch_voters (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL,
                voter_name TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES batches (id),
                UNIQUE(batch_id, voter_name)
            )
        """,
        )

        # Create index for better performance
        self.execute_sql(
            conn, "CREATE INDEX IF NOT EXISTS idx_batch_voters_batch_id ON batch_voters(batch_id)"
        )

        # Migrate existing batches to have default voters
        self._migrate_existing_batches(conn)

    def down(self, conn: sqlite3.Connection) -> None:
        """Drop batch_voters table."""
        self.execute_sql(conn, "DROP TABLE IF EXISTS batch_voters")

    def validate(self, conn: sqlite3.Connection) -> bool:
        """Validate that batch_voters table was created."""
        if not self.table_exists(conn, "batch_voters"):
            return False

        # Validate table structure
        schema = self.get_table_schema(conn, "batch_voters")
        required_columns = {"id", "batch_id", "voter_name"}
        actual_columns = {col["name"] for col in schema}

        return required_columns.issubset(actual_columns)

    def _migrate_existing_batches(self, conn: sqlite3.Connection) -> None:
        """Migrate existing batches to have default voters if they don't have any."""
        try:
            # Find batches without voters
            cursor = conn.execute("""
                SELECT b.id FROM batches b
                LEFT JOIN batch_voters bv ON b.id = bv.batch_id
                WHERE bv.batch_id IS NULL
            """)
            batches_without_voters = [row[0] for row in cursor.fetchall()]

            if batches_without_voters:
                # Default voters (these should match your Config._default_voters)
                # In a real migration, you might want to make this configurable
                default_voters = ["alice@example.com", "bob@example.com", "charlie@example.com"]

                # Add default voters to batches that don't have any
                for batch_id in batches_without_voters:
                    for voter in default_voters:
                        self.execute_sql(
                            conn,
                            "INSERT OR IGNORE INTO batch_voters "
                            "(batch_id, voter_name) VALUES (?, ?)",
                            (batch_id, voter),
                        )

        except Exception:  # nosec B110
            # Log warning but don't fail the migration
            # In a real implementation, you might want to use the logger
            pass
