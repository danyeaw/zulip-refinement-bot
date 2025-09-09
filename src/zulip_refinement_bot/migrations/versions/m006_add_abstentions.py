import sqlite3

from ..base import Migration, SchemaValidationMixin


class AddAbstentionsMigration(Migration, SchemaValidationMixin):
    @property
    def version(self) -> str:
        return "006"

    @property
    def description(self) -> str:
        return "Add abstentions table to support abstaining from voting"

    def up(self, conn: sqlite3.Connection) -> None:
        self.execute_sql(
            conn,
            """
            CREATE TABLE IF NOT EXISTS abstentions (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER,
                issue_number TEXT NOT NULL,
                voter TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches (id),
                UNIQUE(batch_id, issue_number, voter)
            )
        """,
        )

        self.execute_sql(
            conn, "CREATE INDEX IF NOT EXISTS idx_abstentions_batch_id ON abstentions(batch_id)"
        )
        self.execute_sql(
            conn, "CREATE INDEX IF NOT EXISTS idx_abstentions_voter ON abstentions(voter)"
        )

    def down(self, conn: sqlite3.Connection) -> None:
        self.execute_sql(conn, "DROP TABLE IF EXISTS abstentions")

    def validate(self, conn: sqlite3.Connection) -> bool:
        if not self.table_exists(conn, "abstentions"):
            return False

        abstentions_schema = self.get_table_schema(conn, "abstentions")
        required_columns = {"id", "batch_id", "issue_number", "voter", "created_at"}
        actual_columns = {col["name"] for col in abstentions_schema}

        return required_columns.issubset(actual_columns)
