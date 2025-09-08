import sqlite3

from ..base import Migration, SchemaValidationMixin


class InitialSchemaMigration(Migration, SchemaValidationMixin):
    @property
    def version(self) -> str:
        return "001"

    @property
    def description(self) -> str:
        return "Create initial schema with batches, issues, and votes tables"

    def up(self, conn: sqlite3.Connection) -> None:
        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                deadline TEXT NOT NULL,
                facilitator TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        )

        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER,
                issue_number TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT DEFAULT '',
                FOREIGN KEY (batch_id) REFERENCES batches (id)
            )
        """,
        )

        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER,
                issue_number TEXT NOT NULL,
                voter TEXT NOT NULL,
                points INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches (id),
                UNIQUE(batch_id, issue_number, voter)
            )
        """,
        )

        self.execute_sql(conn, "CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status)")
        self.execute_sql(conn, "CREATE INDEX IF NOT EXISTS idx_issues_batch_id ON issues(batch_id)")
        self.execute_sql(conn, "CREATE INDEX IF NOT EXISTS idx_votes_batch_id ON votes(batch_id)")
        self.execute_sql(conn, "CREATE INDEX IF NOT EXISTS idx_votes_voter ON votes(voter)")

    def down(self, conn: sqlite3.Connection) -> None:
        self.execute_sql(conn, "DROP TABLE IF EXISTS votes")
        self.execute_sql(conn, "DROP TABLE IF EXISTS issues")
        self.execute_sql(conn, "DROP TABLE IF EXISTS batches")

    def validate(self, conn: sqlite3.Connection) -> bool:
        required_tables = ["batches", "issues", "votes"]

        for table in required_tables:
            if not self.table_exists(conn, table):
                return False

        batches_schema = self.get_table_schema(conn, "batches")
        required_columns = {"id", "date", "deadline", "facilitator", "status", "created_at"}
        actual_columns = {col["name"] for col in batches_schema}

        if not required_columns.issubset(actual_columns):
            return False

        issues_schema = self.get_table_schema(conn, "issues")
        # Core columns that must exist (title is optional after migration 005)
        required_columns = {"id", "batch_id", "issue_number", "url"}
        actual_columns = {col["name"] for col in issues_schema}

        if not required_columns.issubset(actual_columns):
            return False

        votes_schema = self.get_table_schema(conn, "votes")
        required_columns = {"id", "batch_id", "issue_number", "voter", "points", "created_at"}
        actual_columns = {col["name"] for col in votes_schema}

        if not required_columns.issubset(actual_columns):
            return False

        return True
