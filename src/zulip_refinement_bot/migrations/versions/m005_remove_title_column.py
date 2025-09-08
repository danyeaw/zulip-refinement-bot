import sqlite3

from ..base import Migration, SchemaValidationMixin


class RemoveTitleColumnMigration(Migration, SchemaValidationMixin):
    @property
    def version(self) -> str:
        return "005"

    @property
    def description(self) -> str:
        return "Remove title column from issues table (BSSN: fetch titles on-demand)"

    def up(self, conn: sqlite3.Connection) -> None:
        # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS issues_new (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER,
                issue_number TEXT NOT NULL,
                url TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES batches (id)
            )
        """,
        )

        # Copy data from old table to new table (excluding title)
        self.execute_sql(
            conn,
            """
            INSERT INTO issues_new (id, batch_id, issue_number, url)
            SELECT id, batch_id, issue_number, url FROM issues
        """,
        )

        # Drop old table and rename new table
        self.execute_sql(conn, "DROP TABLE issues")
        self.execute_sql(conn, "ALTER TABLE issues_new RENAME TO issues")

        # Recreate index
        self.execute_sql(conn, "CREATE INDEX IF NOT EXISTS idx_issues_batch_id ON issues(batch_id)")

    def down(self, conn: sqlite3.Connection) -> None:
        # Add title column back (this is a destructive migration)
        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS issues_new (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER,
                issue_number TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                url TEXT DEFAULT '',
                FOREIGN KEY (batch_id) REFERENCES batches (id)
            )
        """,
        )

        # Copy data from old table to new table (title will be empty string)
        self.execute_sql(
            conn,
            """
            INSERT INTO issues_new (id, batch_id, issue_number, title, url)
            SELECT id, batch_id, issue_number, '', url FROM issues
        """,
        )

        # Drop old table and rename new table
        self.execute_sql(conn, "DROP TABLE issues")
        self.execute_sql(conn, "ALTER TABLE issues_new RENAME TO issues")

        # Recreate index
        self.execute_sql(conn, "CREATE INDEX IF NOT EXISTS idx_issues_batch_id ON issues(batch_id)")
