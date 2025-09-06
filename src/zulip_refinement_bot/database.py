"""Database management for the Zulip Refinement Bot."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

import structlog

from .models import BatchData, IssueData

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Handles SQLite database operations for batch and issue storage."""

    def __init__(self, db_path: Path):
        """Initialize database manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        logger.info("Database initialized", db_path=str(self.db_path))

    def _init_database(self) -> None:
        """Initialize database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            # Create batches table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batches (
                    id INTEGER PRIMARY KEY,
                    date TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    facilitator TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
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

            # Create votes table for future use
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

            conn.commit()

    def get_active_batch(self) -> Optional[BatchData]:
        """Get the currently active batch if one exists.
        
        Returns:
            Active batch data or None if no active batch exists
        """
        with sqlite3.connect(self.db_path) as conn:
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
                "SELECT * FROM issues WHERE batch_id = ? ORDER BY id",
                (batch_data["id"],)
            )
            issues = [
                IssueData(
                    issue_number=issue_row["issue_number"],
                    title=issue_row["title"],
                    url=issue_row["url"]
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO batches (date, deadline, facilitator) VALUES (?, ?, ?)",
                (date, deadline, facilitator)
            )
            conn.commit()
            batch_id = cursor.lastrowid
            
        logger.info("Batch created", batch_id=batch_id, facilitator=facilitator)
        return batch_id

    def add_issues_to_batch(self, batch_id: int, issues: List[IssueData]) -> None:
        """Add issues to a batch.
        
        Args:
            batch_id: ID of the batch to add issues to
            issues: List of issues to add
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT INTO issues (batch_id, issue_number, title, url) VALUES (?, ?, ?, ?)",
                [
                    (batch_id, issue.issue_number, issue.title, issue.url)
                    for issue in issues
                ]
            )
            conn.commit()
            
        logger.info("Issues added to batch", batch_id=batch_id, issue_count=len(issues))

    def get_batch_issues(self, batch_id: int) -> List[IssueData]:
        """Get all issues for a batch.
        
        Args:
            batch_id: ID of the batch
            
        Returns:
            List of issues in the batch
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM issues WHERE batch_id = ? ORDER BY id",
                (batch_id,)
            )
            return [
                IssueData(
                    issue_number=row["issue_number"],
                    title=row["title"],
                    url=row["url"]
                )
                for row in cursor.fetchall()
            ]

    def cancel_batch(self, batch_id: int) -> None:
        """Cancel an active batch.
        
        Args:
            batch_id: ID of the batch to cancel
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE batches SET status = 'cancelled' WHERE id = ?",
                (batch_id,)
            )
            conn.commit()
            
        logger.info("Batch cancelled", batch_id=batch_id)

    def complete_batch(self, batch_id: int) -> None:
        """Mark a batch as completed.
        
        Args:
            batch_id: ID of the batch to complete
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE batches SET status = 'completed' WHERE id = ?",
                (batch_id,)
            )
            conn.commit()
            
        logger.info("Batch completed", batch_id=batch_id)
