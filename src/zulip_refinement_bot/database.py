"""Database management with migration system for the Zulip Refinement Bot."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import structlog

from .interfaces import DatabaseInterface
from .migrations.runner import MigrationRunner
from .migrations.versions import ALL_MIGRATIONS
from .models import BatchData, EstimationVote, FinalEstimate, IssueData

logger = structlog.get_logger(__name__)


class DatabaseManager(DatabaseInterface):
    """Database manager that uses the migration system for schema management."""

    def __init__(self, db_path: Path, auto_migrate: bool = True):
        """Initialize database manager with migration support.

        Args:
            db_path: Path to the SQLite database file
            auto_migrate: Whether to automatically run pending migrations on startup
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.migration_runner = MigrationRunner(self.db_path)
        self.migration_runner.register_migrations(ALL_MIGRATIONS)

        if auto_migrate:
            self._run_migrations()

        logger.info("Database initialized with migration system", db_path=str(self.db_path))

    def _run_migrations(self) -> None:
        """Run any pending migrations."""
        try:
            applied = self.migration_runner.run_migrations()
            if applied:
                logger.info("Applied migrations on startup", migrations=applied)
        except Exception as e:
            logger.error("Failed to run migrations on startup", error=str(e))
            raise

    def get_migration_status(self) -> dict[str, dict]:
        """Get the status of all migrations."""
        return self.migration_runner.get_migration_status()

    def validate_schema(self) -> bool:
        """Validate that all applied migrations are still valid."""
        return self.migration_runner.validate_migrations()

    def get_active_batch(self) -> BatchData | None:
        """Get the currently active batch if one exists.

        Returns:
            Active batch data or None if no active batch exists
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM batches WHERE status IN ('active', 'discussing') "
                "ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()

            if not row:
                return None

            batch_data = dict(row)

            issues_cursor = conn.execute(
                "SELECT * FROM issues WHERE batch_id = ? ORDER BY id", (batch_data["id"],)
            )
            issues = [
                IssueData(
                    issue_number=issue_row["issue_number"],
                    url=issue_row["url"],
                )
                for issue_row in issues_cursor.fetchall()
            ]

            return BatchData(**batch_data, issues=issues)

    def get_most_recent_batch(self) -> BatchData | None:
        """Get the most recent batch regardless of status.

        Returns:
            Most recent batch data or None if no batches exist
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM batches ORDER BY created_at DESC LIMIT 1")
            row = cursor.fetchone()

            if not row:
                return None

            batch_data = dict(row)

            issues_cursor = conn.execute(
                "SELECT * FROM issues WHERE batch_id = ? ORDER BY id", (batch_data["id"],)
            )
            issues = [
                IssueData(
                    issue_number=issue_row["issue_number"],
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

        t       Returns:
                    ID of the created batch
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO batches (date, deadline, facilitator) VALUES (?, ?, ?)",
                (date, deadline, facilitator),
            )
            conn.commit()
            batch_id = cursor.lastrowid
            if batch_id is None:
                raise RuntimeError("Failed to create batch: no ID returned")

        logger.info("Batch created", batch_id=batch_id, facilitator=facilitator)
        return batch_id

    def add_issues_to_batch(self, batch_id: int, issues: list[IssueData]) -> None:
        """Add issues to a batch.

        Args:
            batch_id: ID of the batch to add issues to
            issues: List of issues to add
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT INTO issues (batch_id, issue_number, url) VALUES (?, ?, ?)",
                [(batch_id, issue.issue_number, issue.url) for issue in issues],
            )
            conn.commit()

        logger.info("Issues added to batch", batch_id=batch_id, issue_count=len(issues))

    def get_batch_issues(self, batch_id: int) -> list[IssueData]:
        """Get all issues for a batch.

        Args:
            batch_id: ID of the batch

        Returns:
            List of issues in the batch
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM issues WHERE batch_id = ? ORDER BY id", (batch_id,)
            )
            return [
                IssueData(issue_number=row["issue_number"], url=row["url"])
                for row in cursor.fetchall()
            ]

    def cancel_batch(self, batch_id: int) -> None:
        """Cancel an active batch.

        Args:
            batch_id: ID of the batch to cancel
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE batches SET status = 'cancelled' WHERE id = ?", (batch_id,))
            conn.commit()

        logger.info("Batch cancelled", batch_id=batch_id)

    def complete_batch(self, batch_id: int) -> None:
        """Mark a batch as completed.

        Args:
            batch_id: ID of the batch to complete
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE batches SET status = 'completed' WHERE id = ?", (batch_id,))
            conn.commit()

        logger.info("Batch completed", batch_id=batch_id)

    def set_batch_discussing(self, batch_id: int) -> None:
        """Set batch status to discussing.

        Args:
            batch_id: ID of the batch to update
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE batches SET status = 'discussing' WHERE id = ?", (batch_id,))
            conn.commit()

        logger.info("Batch set to discussing", batch_id=batch_id)

    def store_final_estimate(
        self, batch_id: int, issue_number: str, final_points: int, rationale: str
    ) -> None:
        """Store a final estimate for an issue after discussion.

        Args:
            batch_id: ID of the batch
            issue_number: Issue number
            final_points: Final agreed story points
            rationale: Brief rationale for the estimate
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO final_estimates
                    (batch_id, issue_number, final_points, rationale, timestamp)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (batch_id, issue_number, final_points, rationale),
                )

                conn.commit()
                logger.info(
                    "Final estimate stored",
                    batch_id=batch_id,
                    issue_number=issue_number,
                    final_points=final_points,
                )

        except sqlite3.Error as e:
            logger.error("Error storing final estimate", error=str(e))
            raise

    def get_final_estimates(self, batch_id: int) -> list[FinalEstimate]:
        """Get all final estimates for a batch.

        Args:
            batch_id: ID of the batch

        Returns:
            List of final estimates
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT issue_number, final_points, rationale, timestamp
                    FROM final_estimates
                    WHERE batch_id = ?
                    ORDER BY issue_number
                """,
                    (batch_id,),
                )

                final_estimates = []
                for row in cursor.fetchall():
                    final_estimates.append(
                        FinalEstimate(
                            issue_number=row["issue_number"],
                            final_points=row["final_points"],
                            rationale=row["rationale"] or "",
                            timestamp=datetime.fromisoformat(row["timestamp"]),
                        )
                    )

                return final_estimates

        except sqlite3.Error as e:
            logger.error("Error getting final estimates", error=str(e))
            return []

    def store_vote(self, batch_id: int, voter: str, issue_number: str, points: int) -> bool:
        """Store a vote for an issue in a batch.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter
            issue_number: Issue number being voted on
            points: Story points estimate

        Returns:
            True if vote was stored successfully, False if it was a duplicate
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO votes (batch_id, issue_number, voter, points) VALUES (?, ?, ?, ?)",
                    (batch_id, issue_number, voter, points),
                )
                conn.commit()
                logger.info(
                    "Vote stored",
                    batch_id=batch_id,
                    voter=voter,
                    issue_number=issue_number,
                    points=points,
                )
                return True
        except sqlite3.IntegrityError:
            logger.warning(
                "Duplicate vote attempt", batch_id=batch_id, voter=voter, issue_number=issue_number
            )
            return False

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
            - success: True if vote was stored/updated successfully
            - was_update: True if this was an update, False if it was a new vote
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT points FROM votes WHERE batch_id = ? AND issue_number = ? AND voter = ?",
                (batch_id, issue_number, voter),
            )
            existing_vote = cursor.fetchone()

            if existing_vote:
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
        with sqlite3.connect(self.db_path) as conn:
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(DISTINCT voter) FROM votes WHERE batch_id = ?", (batch_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_completed_voters_count(self, batch_id: int) -> int:
        """Get the number of voters who have completed all voting.

        Args:
            batch_id: ID of the batch

        Returns:
            Number of voters who have completed voting
        """
        with sqlite3.connect(self.db_path) as conn:
            # Get total number of issues in the batch
            cursor = conn.execute("SELECT COUNT(*) FROM issues WHERE batch_id = ?", (batch_id,))
            total_issues = cursor.fetchone()[0]

            if total_issues == 0:
                return 0

            cursor = conn.execute(
                """
                SELECT voter FROM (
                    SELECT voter, COUNT(DISTINCT issue_number) as actions_count
                    FROM (
                        SELECT voter, issue_number FROM votes WHERE batch_id = ?
                        UNION
                        SELECT voter, issue_number FROM abstentions WHERE batch_id = ?
                    ) combined
                    GROUP BY voter
                ) voter_counts
                WHERE actions_count = ?
                """,
                (batch_id, batch_id, total_issues),
            )
            return len(cursor.fetchall())

    def has_voter_voted(self, batch_id: int, voter: str) -> bool:
        """Check if a voter has already submitted votes for a batch.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter

        Returns:
            True if the voter has already voted, False otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM votes WHERE batch_id = ? AND voter = ?", (batch_id, voter)
            )
            result = cursor.fetchone()
            return (result[0] if result else 0) > 0

    def update_batch_message_id(self, batch_id: int, message_id: int) -> None:
        """Update the message ID for a batch.

        Args:
            batch_id: ID of the batch
            message_id: Zulip message ID of the batch refinement message
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
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

    def update_batch_results_message_id(self, batch_id: int, results_message_id: int) -> None:
        """Update the results message ID for a batch.

        Args:
            batch_id: ID of the batch
            results_message_id: Zulip message ID of the estimation results message
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "UPDATE batches SET results_message_id = ? WHERE id = ?",
                    (results_message_id, batch_id),
                )
                rows_affected = cursor.rowcount
                conn.commit()

                if rows_affected == 0:
                    logger.warning(
                        "No batch found to update results message ID",
                        batch_id=batch_id,
                        results_message_id=results_message_id,
                    )
                else:
                    logger.info(
                        "Updated batch results message ID",
                        batch_id=batch_id,
                        results_message_id=results_message_id,
                    )
        except Exception as e:
            logger.error(
                "Failed to update batch results message ID",
                batch_id=batch_id,
                results_message_id=results_message_id,
                error=str(e),
            )

    def add_batch_voters(self, batch_id: int, voters: list[str]) -> None:
        """Add voters to a batch.

        Args:
            batch_id: ID of the batch
            voters: List of voter names
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT INTO batch_voters (batch_id, voter_name) VALUES (?, ?)",
                [(batch_id, voter) for voter in voters],
            )
            conn.commit()

        logger.info("Voters added to batch", batch_id=batch_id, voter_count=len(voters))

    def get_batch_voters(self, batch_id: int) -> list[str]:
        """Get all voters for a batch.

        Args:
            batch_id: ID of the batch

        Returns:
            List of voter names for the batch
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT voter_name FROM batch_voters WHERE batch_id = ? ORDER BY voter_name",
                (batch_id,),
            )
            voters = [row[0] for row in cursor.fetchall()]

        logger.debug("Retrieved batch voters", batch_id=batch_id, voters=voters)
        return voters

    def add_voter_to_batch(self, batch_id: int, voter: str) -> bool:
        """Add a single voter to a batch if they're not already added.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter to add

        Returns:
            True if voter was added, False if they were already in the batch
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO batch_voters (batch_id, voter_name) VALUES (?, ?)",
                    (batch_id, voter),
                )
                conn.commit()
                logger.info("Added new voter to batch", batch_id=batch_id, voter=voter)
                return True
        except sqlite3.IntegrityError:
            # Voter already exists in batch (UNIQUE constraint violation)
            logger.debug("Voter already exists in batch", batch_id=batch_id, voter=voter)
            return False

    def remove_voter_from_batch(self, batch_id: int, voter: str) -> bool:
        """Remove a voter from a batch.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter to remove

        Returns:
            True if voter was removed, False if they weren't in the batch
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM batch_voters WHERE batch_id = ? AND voter_name = ?",
                (batch_id, voter),
            )
            rows_affected = cursor.rowcount
            conn.commit()

            if rows_affected > 0:
                logger.info("Removed voter from batch", batch_id=batch_id, voter=voter)
                return True
            else:
                logger.debug("Voter not found in batch", batch_id=batch_id, voter=voter)
                return False

    def upsert_abstention(self, batch_id: int, voter: str, issue_number: str) -> tuple[bool, bool]:
        """Store or update an abstention for an issue in a batch.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter
            issue_number: Issue number being abstained from

        Returns:
            Tuple of (success: bool, was_update: bool)
        """
        with sqlite3.connect(self.db_path) as conn:
            # Check if abstention already exists
            cursor = conn.execute(
                "SELECT id FROM abstentions WHERE batch_id = ? AND issue_number = ? AND voter = ?",
                (batch_id, issue_number, voter),
            )
            existing_abstention = cursor.fetchone()

            if existing_abstention:
                # Update existing abstention timestamp
                conn.execute(
                    """UPDATE abstentions SET created_at = CURRENT_TIMESTAMP
                       WHERE batch_id = ? AND issue_number = ? AND voter = ?""",
                    (batch_id, issue_number, voter),
                )
                conn.commit()
                logger.info(
                    "Abstention updated",
                    batch_id=batch_id,
                    voter=voter,
                    issue_number=issue_number,
                )
                return True, True
            else:
                conn.execute(
                    "INSERT INTO abstentions (batch_id, issue_number, voter) VALUES (?, ?, ?)",
                    (batch_id, issue_number, voter),
                )
                conn.commit()
                logger.info(
                    "Abstention recorded",
                    batch_id=batch_id,
                    voter=voter,
                    issue_number=issue_number,
                )
                return True, False

    def get_voter_abstentions(self, batch_id: int, voter: str) -> list[str]:
        """Get list of issue numbers a voter has abstained from.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter

        Returns:
            List of issue numbers
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT issue_number FROM abstentions WHERE batch_id = ? AND voter = ?",
                (batch_id, voter),
            )
            return [row[0] for row in cursor.fetchall()]

    def has_voter_abstained(self, batch_id: int, voter: str, issue_number: str) -> bool:
        """Check if a voter has abstained from a specific issue.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter
            issue_number: Issue number to check

        Returns:
            True if voter has abstained from this issue
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM abstentions WHERE batch_id = ? AND voter = ? AND issue_number = ?",
                (batch_id, voter, issue_number),
            )
            return cursor.fetchone() is not None

    def remove_vote_if_exists(self, batch_id: int, voter: str, issue_number: str) -> bool:
        """Remove a vote if it exists.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter
            issue_number: Issue number

        Returns:
            True if a vote was removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM votes WHERE batch_id = ? AND voter = ? AND issue_number = ?",
                (batch_id, voter, issue_number),
            )
            rows_affected = cursor.rowcount
            conn.commit()

            if rows_affected > 0:
                logger.info(
                    "Vote removed",
                    batch_id=batch_id,
                    voter=voter,
                    issue_number=issue_number,
                )
                return True
            return False

    def remove_abstention_if_exists(self, batch_id: int, voter: str, issue_number: str) -> bool:
        """Remove an abstention if it exists.

        Args:
            batch_id: ID of the batch
            voter: Name of the voter
            issue_number: Issue number

        Returns:
            True if an abstention was removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM abstentions WHERE batch_id = ? AND voter = ? AND issue_number = ?",
                (batch_id, voter, issue_number),
            )
            rows_affected = cursor.rowcount
            conn.commit()

            if rows_affected > 0:
                logger.info(
                    "Abstention removed",
                    batch_id=batch_id,
                    voter=voter,
                    issue_number=issue_number,
                )
                return True
            return False

    def has_reminder_been_sent(self, batch_id: int, reminder_type: str) -> bool:
        """Check if a specific reminder has already been sent for a batch.

        Args:
            batch_id: ID of the batch
            reminder_type: Type of reminder (e.g., 'halfway', '1_hour')

        Returns:
            True if reminder has been sent, False otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM batch_reminders WHERE batch_id = ? AND reminder_type = ?",
                (batch_id, reminder_type),
            )
            result = cursor.fetchone()
            return result is not None

    def record_reminder_sent(self, batch_id: int, reminder_type: str) -> None:
        """Record that a reminder has been sent for a batch.

        Args:
            batch_id: ID of the batch
            reminder_type: Type of reminder (e.g., 'halfway', '1_hour')
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO batch_reminders (batch_id, reminder_type) VALUES (?, ?)",
                    (batch_id, reminder_type),
                )
                conn.commit()
                logger.info("Reminder recorded", batch_id=batch_id, reminder_type=reminder_type)
        except sqlite3.IntegrityError:
            # Reminder already recorded (UNIQUE constraint violation)
            logger.debug(
                "Reminder already recorded", batch_id=batch_id, reminder_type=reminder_type
            )

    def get_voters_without_votes(self, batch_id: int) -> list[str]:
        """Get list of voters who haven't submitted any votes or abstentions yet.

        Args:
            batch_id: ID of the batch

        Returns:
            List of voter names who haven't voted
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT bv.voter_name
                FROM batch_voters bv
                WHERE bv.batch_id = ?
                AND bv.voter_name NOT IN (
                    SELECT DISTINCT voter FROM votes WHERE batch_id = ?
                    UNION
                    SELECT DISTINCT voter FROM abstentions WHERE batch_id = ?
                )
                ORDER BY bv.voter_name
                """,
                (batch_id, batch_id, batch_id),
            )
            voters = [row[0] for row in cursor.fetchall()]

        logger.debug("Retrieved voters without votes", batch_id=batch_id, voters=voters)
        return voters
