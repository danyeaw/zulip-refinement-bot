"""Database connection pooling for the Zulip Refinement Bot."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Queue

import structlog

from .exceptions import DatabaseError
from .interfaces import DatabaseInterface
from .models import BatchData, EstimationVote, IssueData

logger = structlog.get_logger(__name__)


class DatabasePool(DatabaseInterface):
    """Database manager with connection pooling for better performance."""

    def __init__(self, db_path: Path, pool_size: int = 5) -> None:
        """Initialize database pool.

        Args:
            db_path: Path to the SQLite database file
            pool_size: Maximum number of connections in the pool
        """
        self.db_path = Path(db_path)
        self.pool_size = pool_size
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize the connection pool
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()

        # Create initial connections and initialize database
        self._init_pool()
        self._init_database()

        logger.info("Database pool initialized", db_path=str(self.db_path), pool_size=pool_size)

    def _init_pool(self) -> None:
        """Initialize the connection pool with connections."""
        for _ in range(self.pool_size):
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # Allow sharing across threads
                timeout=30.0,  # 30 second timeout
            )
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA temp_store=memory")
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB
            self._pool.put(conn)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a connection from the pool.

        Yields:
            Database connection

        Raises:
            DatabaseError: If unable to get connection
        """
        conn = None
        try:
            # Try to get a connection from the pool
            conn = self._pool.get(timeout=10.0)
            yield conn
        except Empty as e:
            raise DatabaseError("Unable to get database connection from pool") from e
        except Exception as e:
            raise DatabaseError(f"Database connection error: {str(e)}") from e
        finally:
            if conn:
                # Return connection to pool
                self._pool.put(conn)

    def _init_database(self) -> None:
        """Initialize database with required tables."""
        with self._get_connection() as conn:
            # Create batches table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batches (
                    id INTEGER PRIMARY KEY,
                    date TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    facilitator TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create issues table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY,
                    batch_id INTEGER,
                    issue_number TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT DEFAULT '',
                    FOREIGN KEY (batch_id) REFERENCES batches (id)
                )
            """)

            # Create votes table
            conn.execute("""
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
            """)

            # Migration: Add message_id column if it doesn't exist
            try:
                conn.execute("ALTER TABLE batches ADD COLUMN message_id INTEGER")
                logger.info("Added message_id column to batches table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    # Column already exists, which is fine
                    pass
                else:
                    # Some other error, re-raise it
                    raise

            conn.commit()

    def get_active_batch(self) -> BatchData | None:
        """Get the currently active batch if one exists.

        Returns:
            Active batch data or None if no active batch exists
        """
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM batches WHERE status = 'active' ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()

            if not row:
                return None

            batch_data = dict(row)

            # Get issues for this batch
            issues_cursor = conn.execute(
                "SELECT * FROM issues WHERE batch_id = ? ORDER BY id", (batch_data["id"],)
            )
            issues = [
                IssueData(
                    issue_number=issue_row["issue_number"],
                    title=issue_row["title"],
                    url=issue_row["url"],
                )
                for issue_row in issues_cursor.fetchall()
            ]

            return BatchData(**batch_data, issues=issues)

    def create_batch(self, date: str, deadline: str, facilitator: str) -> int:
        """Create a new batch and return its ID.

        Args:
            date: Batch date in YYYY-MM-DD format
            deadline: Deadline in ISO format
            facilitator: Name of the batch facilitator

        Returns:
            ID of the created batch
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO batches (date, deadline, facilitator) VALUES (?, ?, ?)",
                (date, deadline, facilitator),
            )
            conn.commit()
            batch_id = cursor.lastrowid
            if batch_id is None:
                raise DatabaseError("Failed to create batch: no ID returned")

        logger.info("Batch created", batch_id=batch_id, facilitator=facilitator)
        return batch_id

    def add_issues_to_batch(self, batch_id: int, issues: list[IssueData]) -> None:
        """Add issues to a batch.

        Args:
            batch_id: ID of the batch to add issues to
            issues: List of issues to add
        """
        with self._get_connection() as conn:
            conn.executemany(
                "INSERT INTO issues (batch_id, issue_number, title, url) VALUES (?, ?, ?, ?)",
                [(batch_id, issue.issue_number, issue.title, issue.url) for issue in issues],
            )
            conn.commit()

        logger.info("Issues added to batch", batch_id=batch_id, issue_count=len(issues))

    def cancel_batch(self, batch_id: int) -> None:
        """Cancel an active batch.

        Args:
            batch_id: ID of the batch to cancel
        """
        with self._get_connection() as conn:
            conn.execute("UPDATE batches SET status = 'cancelled' WHERE id = ?", (batch_id,))
            conn.commit()

        logger.info("Batch cancelled", batch_id=batch_id)

    def complete_batch(self, batch_id: int) -> None:
        """Mark a batch as completed.

        Args:
            batch_id: ID of the batch to complete
        """
        with self._get_connection() as conn:
            conn.execute("UPDATE batches SET status = 'completed' WHERE id = ?", (batch_id,))
            conn.commit()

        logger.info("Batch completed", batch_id=batch_id)

    def upsert_vote(
        self, batch_id: int, voter: str, issue_number: str, points: int
    ) -> tuple[bool, bool]:
        """Store or update a vote for an issue in a batch.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter
            issue_number: Issue number being voted on
            points: Story points estimate

        Returns:
            Tuple of (success: bool, was_update: bool)
        """
        with self._get_connection() as conn:
            # Check if vote already exists
            cursor = conn.execute(
                "SELECT points FROM votes WHERE batch_id = ? AND issue_number = ? AND voter = ?",
                (batch_id, issue_number, voter),
            )
            existing_vote = cursor.fetchone()

            if existing_vote:
                # Update existing vote
                old_points = existing_vote[0]
                conn.execute(
                    """UPDATE votes SET points = ?, created_at = CURRENT_TIMESTAMP
                       WHERE batch_id = ? AND issue_number = ? AND voter = ?""",
                    (points, batch_id, issue_number, voter),
                )
                conn.commit()
                logger.info(
                    "Vote updated",
                    batch_id=batch_id,
                    voter=voter,
                    issue_number=issue_number,
                    old_points=old_points,
                    new_points=points,
                )
                return True, True
            else:
                # Insert new vote
                conn.execute(
                    "INSERT INTO votes (batch_id, issue_number, voter, points) VALUES (?, ?, ?, ?)",
                    (batch_id, issue_number, voter, points),
                )
                conn.commit()
                logger.info(
                    "New vote stored",
                    batch_id=batch_id,
                    voter=voter,
                    issue_number=issue_number,
                    points=points,
                )
                return True, False

    def get_batch_votes(self, batch_id: int) -> list[EstimationVote]:
        """Get all votes for a batch.

        Args:
            batch_id: ID of the batch

        Returns:
            List of votes for the batch
        """
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM votes WHERE batch_id = ? ORDER BY created_at", (batch_id,)
            )
            return [
                EstimationVote(
                    voter=row["voter"],
                    issue_number=row["issue_number"],
                    points=row["points"],
                    timestamp=row["created_at"],
                )
                for row in cursor.fetchall()
            ]

    def get_vote_count_by_voter(self, batch_id: int) -> int:
        """Get the number of unique voters who have submitted votes for a batch.

        Args:
            batch_id: ID of the batch

        Returns:
            Number of unique voters
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(DISTINCT voter) FROM votes WHERE batch_id = ?", (batch_id,)
            )
            result = cursor.fetchone()
            count = result[0] if result else 0

            logger.debug("Vote count query result", batch_id=batch_id, vote_count=count)
            return count

    def update_batch_message_id(self, batch_id: int, message_id: int) -> None:
        """Update the message ID for a batch.

        Args:
            batch_id: ID of the batch
            message_id: Zulip message ID of the batch refinement message
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "UPDATE batches SET message_id = ? WHERE id = ?", (message_id, batch_id)
                )
                rows_affected = cursor.rowcount
                conn.commit()

                if rows_affected == 0:
                    logger.warning(
                        "No batch found to update message ID",
                        batch_id=batch_id,
                        message_id=message_id,
                    )
                else:
                    logger.info(
                        "Updated batch message ID", batch_id=batch_id, message_id=message_id
                    )
        except Exception as e:
            logger.error(
                "Failed to update batch message ID",
                batch_id=batch_id,
                message_id=message_id,
                error=str(e),
            )

    def close(self) -> None:
        """Close all connections in the pool."""
        logger.info("Closing database connection pool")
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break
        logger.info("Database connection pool closed")
