"""Main bot implementation for the Zulip Refinement Bot."""

from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, cast

import structlog
import zulip

from .config import Config
from .database import DatabaseManager
from .github_api import GitHubAPI
from .models import BatchData, EstimationVote, IssueData, MessageData
from .parser import InputParser

logger = structlog.get_logger(__name__)


class ZulipResponse(TypedDict, total=False):
    """Type definition for Zulip API responses.

    Note: Uses total=False since most fields are optional.
    The API uses "retry-after" (with hyphen) which we access via dict key.
    """

    result: str
    msg: str
    id: int
    code: str


class RefinementBot:
    """Main bot handler for the refinement bot."""

    def __init__(self, config: Config):
        """Initialize the refinement bot.

        Args:
            config: Bot configuration
        """
        self.config = config
        self.db_manager = DatabaseManager(config.database_path)
        self.github_api = GitHubAPI(timeout=config.github_timeout)
        self.parser = InputParser(config, self.github_api)

        self.zulip_client = zulip.Client(
            email=config.zulip_email,
            api_key=config.zulip_api_key,
            site=config.zulip_site,
        )

        # Start deadline checker thread
        self._deadline_checker_running = True
        self._deadline_checker_thread = threading.Thread(
            target=self._deadline_checker_loop, daemon=True
        )
        self._deadline_checker_thread.start()

        logger.info("Refinement bot initialized", config=config.dict(exclude={"zulip_api_key"}))

    def usage(self) -> str:
        """Return usage instructions for the bot."""
        return f"""
        **Zulip Story Point Estimation Bot - Phase 1**

        **Commands (DM only):**
        • `start batch` - Create new estimation batch
        • `status` - Show active batch info
        • `cancel` - Cancel active batch (facilitator only)
        • `complete` - Complete active batch and show results (facilitator only)

        **Batch format (GitHub URLs only):**
        ```
        start batch
        https://github.com/conda/conda/issues/15169
        https://github.com/conda/conda/issues/15168
        https://github.com/conda/conda/issues/15167
        ```

        **Voting format:**
        ```
        #15169: 5, #15168: 8, #15167: 3
        ```

        **Rules:**
        • Maximum {self.config.max_issues_per_batch} issues per batch
        • Only one active batch at a time
        • Issue titles truncated at {self.config.max_title_length} characters
        • {self.config.default_deadline_hours}-hour default deadline
        • Valid story points: 1, 2, 3, 5, 8, 13, 21
        • Must vote for all issues in the batch
        • Can update votes by submitting new estimates (replaces previous votes)
        • Batch completes automatically when all voters submit or when deadline expires
        """

    def handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming messages.

        Args:
            message: Zulip message data
        """
        try:
            msg_data = MessageData(**message)

            if msg_data.sender_email == self.config.zulip_email:
                return

            if msg_data.type != "private":
                return

            content = msg_data.content.strip()

            if not content or content.lower() in ["help", "usage"]:
                self._send_reply(message, self.usage())
                return

            if content.lower().startswith("start batch"):
                self._handle_start_batch(message, content)
            elif content.lower() == "status":
                self._handle_status(message)
            elif content.lower() == "cancel":
                self._handle_cancel(message)
            elif content.lower() == "complete":
                self._handle_complete(message)
            else:
                if self._is_vote_format(content):
                    self._handle_vote_submission(message, content)
                else:
                    self._send_reply(
                        message, "❌ Unknown command. Send 'help' for usage instructions."
                    )

        except Exception as e:
            logger.error("Error handling message", error=str(e), message=message)
            self._send_reply(
                message, "❌ An error occurred processing your message. Please try again."
            )

    def _handle_start_batch(self, message: dict[str, Any], content: str) -> None:
        """Handle batch creation request.

        Args:
            message: Zulip message data
            content: Message content
        """
        active_batch = self.db_manager.get_active_batch()
        if active_batch:
            self._send_reply(
                message, "❌ Active batch already running. Use 'status' to check progress."
            )
            return

        parse_result = self.parser.parse_batch_input(content)
        if not parse_result.success:
            self._send_reply(message, parse_result.error)
            return
        facilitator = message["sender_full_name"]
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")
        deadline = now + timedelta(hours=self.config.default_deadline_hours)
        deadline_str = deadline.isoformat()

        try:
            batch_id = self.db_manager.create_batch(date_str, deadline_str, facilitator)
            self.db_manager.add_issues_to_batch(batch_id, parse_result.issues)

            self._send_batch_confirmation(message, parse_result.issues, deadline, date_str)
            self._create_batch_topic(batch_id, parse_result.issues, deadline, facilitator, date_str)

        except Exception as e:
            logger.error("Error creating batch", error=str(e))
            self._send_reply(message, f"❌ Error creating batch: {str(e)}. Please try again.")

    def _handle_status(self, message: dict[str, Any]) -> None:
        """Handle status request.

        Args:
            message: Zulip message data
        """
        active_batch = self.db_manager.get_active_batch()
        if not active_batch:
            self._send_reply(message, "✅ No active batch currently running.")
            return

        deadline = datetime.fromisoformat(active_batch.deadline)

        issue_list = "\n".join(
            [
                f"• #{issue.issue_number}: {issue.title}"
                + (f" ([link]({issue.url}))" if issue.url else "")
                for issue in active_batch.issues
            ]
        )

        status_msg = f"""**📊 Active Batch Status**
**Date**: {active_batch.date}
**Facilitator**: {active_batch.facilitator}
**Deadline**: {deadline.strftime("%Y-%m-%d %H:%M UTC")}
**Issues** ({len(active_batch.issues)}):
{issue_list}

**Topic**: Refinement: {active_batch.date} ({len(active_batch.issues)} issues)
**Stream**: #{self.config.stream_name}"""

        self._send_reply(message, status_msg)

    def _handle_cancel(self, message: dict[str, Any]) -> None:
        """Handle batch cancellation request.

        Args:
            message: Zulip message data
        """
        active_batch = self.db_manager.get_active_batch()
        if not active_batch:
            self._send_reply(message, "✅ No active batch to cancel.")
            return

        if message["sender_full_name"] != active_batch.facilitator:
            self._send_reply(
                message,
                f"❌ Only the facilitator ({active_batch.facilitator}) can cancel this batch.",
            )
            return

        if active_batch.id is None:
            self._send_reply(message, "❌ Error: Batch ID is missing.")
            return

        self.db_manager.cancel_batch(active_batch.id)
        self._send_reply(message, "✅ Batch cancelled successfully.")

    def _handle_complete(self, message: dict[str, Any]) -> None:
        """Handle batch completion request.

        Args:
            message: Zulip message data
        """
        active_batch = self.db_manager.get_active_batch()
        if not active_batch:
            self._send_reply(message, "✅ No active batch to complete.")
            return

        if message["sender_full_name"] != active_batch.facilitator:
            self._send_reply(
                message,
                f"❌ Only the facilitator ({active_batch.facilitator}) can complete this batch.",
            )
            return

        if active_batch.id is None:
            self._send_reply(message, "❌ Error: Batch ID is missing.")
            return

        # Process completion immediately
        self._process_batch_completion(active_batch)
        self._send_reply(message, "✅ Batch completed successfully. Results posted to the stream.")

    def _send_batch_confirmation(
        self, message: dict[str, Any], issues: list[IssueData], deadline: datetime, date_str: str
    ) -> None:
        """Send confirmation message to user who created the batch.

        Args:
            message: Original message
            issues: List of issues in the batch
            deadline: Batch deadline
            date_str: Batch date string
        """
        issue_list = "\n".join(
            [
                f"• #{issue.issue_number}: {issue.title}"
                + (f" ([link]({issue.url}))" if issue.url else "")
                for issue in issues
            ]
        )

        confirmation = f"""✅ **Batch created: {len(issues)} issues**
📅 **Deadline**: {deadline.strftime("%Y-%m-%d %H:%M UTC")}
🎯 **Topic**: Refinement: {date_str} ({len(issues)} issues)

**Issues:**
{issue_list}

Posting to #{self.config.stream_name} now..."""

        self._send_reply(message, confirmation)

    def _create_batch_topic(
        self,
        batch_id: int,
        issues: list[IssueData],
        deadline: datetime,
        facilitator: str,
        date_str: str,
    ) -> None:
        """Create the batch topic in the stream.

        Args:
            batch_id: Database batch ID
            issues: List of issues
            deadline: Batch deadline
            facilitator: Facilitator name
            date_str: Batch date string
        """
        issue_list = "\n".join(
            [
                f"• #{issue.issue_number} - " + f"[{issue.title}]({issue.url})"
                if issue.url
                else f"{issue.title}"
                for issue in issues
            ]
        )

        voter_mentions = ", ".join([f"@**{voter}**" for voter in self.config.voter_list])

        topic_content = f"""**📦 BATCH REFINEMENT**
**Stories**:
{issue_list}

**Deadline**: {deadline.strftime("%Y-%m-%d %H:%M UTC")} ({self.config.default_deadline_hours} hours from now)
**Facilitator**: @**{facilitator}**

**How to estimate**:
1. Review issues in GitHub
2. Consider complexity, unknowns, dependencies for each
3. DM @**Refinement Bot** your story point estimates in this format:
   `#{issues[0].issue_number}: 5, #{issues[1].issue_number if len(issues) > 1 else issues[0].issue_number}: 8, #{issues[2].issue_number if len(issues) > 2 else issues[0].issue_number}: 3`
4. Use scale: 1, 2, 3, 5, 8, 13, 21

**Voters needed**: {voter_mentions}

**Status**: ⏳ Collecting estimates (0/{len(self.config.voter_list)} received)

*Will reveal results here once all votes are in*"""

        topic_name = f"Refinement: {date_str} ({len(issues)} issues)"

        try:
            response = self._send_message_with_retry(
                {
                    "type": "stream",
                    "to": self.config.stream_name,
                    "topic": topic_name,
                    "content": topic_content,
                }
            )

            if response.get("result") == "success" and "id" in response:
                message_id = response["id"]
                self.db_manager.update_batch_message_id(batch_id, message_id)
                logger.info(
                    "Created batch topic",
                    batch_id=batch_id,
                    topic=topic_name,
                    message_id=message_id,
                )
            elif response.get("result") == "success":
                logger.warning(
                    "Batch message sent successfully but no message ID in response",
                    batch_id=batch_id,
                    response=response,
                )
            elif response.get("result") == "error":
                error_code = response.get("code", "UNKNOWN")
                error_msg = response.get("msg", "Unknown error")
                logger.error(
                    "Failed to create batch topic - API error",
                    batch_id=batch_id,
                    error_code=error_code,
                    error_msg=error_msg,
                    response=response,
                )
                return
            else:
                logger.warning(
                    "Unexpected response format from Zulip API",
                    batch_id=batch_id,
                    response=response,
                )

        except Exception as e:
            logger.error("Failed to create batch topic", batch_id=batch_id, error=str(e))

    def _is_vote_format(self, content: str) -> bool:
        """Check if content looks like a vote submission.

        Args:
            content: Message content to check

        Returns:
            True if content appears to be in vote format
        """
        import re

        vote_pattern = re.compile(r"#\d+:\s*\d+")
        return bool(vote_pattern.search(content))

    def _handle_vote_submission(self, message: dict[str, Any], content: str) -> None:
        """Handle vote submission from a user.

        Args:
            message: Zulip message data
            content: Vote content
        """
        voter_name = message["sender_full_name"]

        if voter_name not in self.config.voter_list:
            self._send_reply(
                message,
                f"❌ You are not authorized to vote. Authorized voters: {', '.join(self.config.voter_list)}",
            )
            return

        active_batch = self.db_manager.get_active_batch()
        if not active_batch or active_batch.id is None:
            self._send_reply(message, "❌ No active batch found. Cannot submit votes.")
            return

        # Note: We now allow vote updates, so we don't check if voter has already voted

        # Parse the votes
        estimates, validation_errors = self.parser.parse_estimation_input(content)

        # Check for validation errors (invalid Fibonacci values)
        if validation_errors:
            error_msg = "❌ Invalid story point values found:\n"
            for error in validation_errors:
                error_msg += f"  • {error}\n"
            error_msg += "\nValid story points (Fibonacci sequence): 1, 2, 3, 5, 8, 13, 21"
            self._send_reply(message, error_msg)
            return

        if not estimates:
            self._send_reply(
                message,
                "❌ No valid votes found. Please use format: `#1234: 5, #1235: 8, #1236: 3`\n"
                "Valid story points: 1, 2, 3, 5, 8, 13, 21",
            )
            return

        # Validate that all issues in the batch are voted on
        batch_issue_numbers = {issue.issue_number for issue in active_batch.issues}
        voted_issue_numbers = set(estimates.keys())

        missing_votes = batch_issue_numbers - voted_issue_numbers
        extra_votes = voted_issue_numbers - batch_issue_numbers

        if missing_votes or extra_votes:
            error_msg = "❌ Vote validation failed:\n"
            if missing_votes:
                error_msg += (
                    f"Missing votes for issues: {', '.join(f'#{num}' for num in missing_votes)}\n"
                )
            if extra_votes:
                error_msg += f"Votes for issues not in batch: {', '.join(f'#{num}' for num in extra_votes)}\n"
            error_msg += f"\nPlease vote for exactly these issues: {', '.join(f'#{num}' for num in batch_issue_numbers)}"
            self._send_reply(message, error_msg)
            return

        # Store all votes (with update capability)
        stored_count = 0
        updated_count = 0
        new_count = 0

        logger.info(
            "Storing/updating votes for batch",
            batch_id=active_batch.id,
            voter=voter_name,
            vote_count=len(estimates),
            estimates=estimates,
        )

        for issue_number, points in estimates.items():
            success, was_update = self.db_manager.upsert_vote(
                active_batch.id, voter_name, issue_number, points
            )
            if success:
                stored_count += 1
                if was_update:
                    updated_count += 1
                else:
                    new_count += 1
                logger.debug(
                    "Vote processed successfully",
                    batch_id=active_batch.id,
                    voter=voter_name,
                    issue_number=issue_number,
                    points=points,
                    was_update=was_update,
                )
            else:
                logger.error(
                    "Failed to store/update vote",
                    batch_id=active_batch.id,
                    voter=voter_name,
                    issue_number=issue_number,
                    points=points,
                )

        logger.info(
            "Vote processing complete",
            batch_id=active_batch.id,
            voter=voter_name,
            stored_count=stored_count,
            expected_count=len(estimates),
            new_votes=new_count,
            updated_votes=updated_count,
        )

        if stored_count == len(estimates):
            # All votes stored/updated successfully
            vote_summary = ", ".join([f"#{issue}: {points}" for issue, points in estimates.items()])

            # Create appropriate success message
            if updated_count > 0 and new_count > 0:
                action_msg = (
                    f"**Votes processed successfully!** ({new_count} new, {updated_count} updated)"
                )
            elif updated_count > 0:
                action_msg = f"**Votes updated successfully!** ({updated_count} vote{'s' if updated_count != 1 else ''} updated)"
            else:
                action_msg = f"**Votes recorded successfully!** ({new_count} new vote{'s' if new_count != 1 else ''})"

            self._send_reply(
                message,
                f"✅ {action_msg}\n\n"
                f"Your estimates: {vote_summary}\n\n"
                f"Thank you for participating in the refinement process.",
            )

            # Update the batch message with current vote count (for both new and updated votes)
            if new_count > 0 or updated_count > 0:
                self._update_batch_message(active_batch.id, active_batch)

                # Check if all voters have now completed their votes
                self._check_and_complete_if_all_voted(active_batch)
        else:
            self._send_reply(
                message,
                f"⚠️ Only {stored_count} out of {len(estimates)} votes were processed successfully. "
                "Please try again or contact the facilitator.",
            )

    def _check_and_complete_if_all_voted(self, batch: BatchData) -> None:
        """Check if all voters have submitted votes and complete batch if so.

        Args:
            batch: The active batch to check
        """
        if batch.id is None:
            return

        try:
            # Get current vote count
            vote_count = self.db_manager.get_vote_count_by_voter(batch.id)
            total_voters = len(self.config.voter_list)

            logger.info(
                "Checking completion status after vote submission",
                batch_id=batch.id,
                vote_count=vote_count,
                total_voters=total_voters,
            )

            # If all voters have voted, complete the batch automatically
            if vote_count >= total_voters:
                logger.info(
                    "All voters have completed voting, auto-completing batch",
                    batch_id=batch.id,
                    vote_count=vote_count,
                    total_voters=total_voters,
                )

                # Process batch completion with auto-completion flag
                self._process_batch_completion_auto(batch)

        except Exception as e:
            logger.error(
                "Error checking completion status after vote",
                batch_id=batch.id,
                error=str(e),
            )

    def _update_batch_message(self, batch_id: int, active_batch: BatchData | None = None) -> None:
        """Update the batch refinement message with current vote count.

        Args:
            batch_id: ID of the batch to update
            active_batch: Optional batch data to avoid re-fetching
        """
        try:
            # Use provided batch data or fetch it
            if active_batch is None:
                active_batch = self.db_manager.get_active_batch()
                if not active_batch or active_batch.id != batch_id:
                    logger.warning(
                        "Cannot update batch message: batch not found or not active",
                        batch_id=batch_id,
                    )
                    return

            # Get vote count
            vote_count = self.db_manager.get_vote_count_by_voter(batch_id)
            total_voters = len(self.config.voter_list)

            logger.info(
                "Updating batch message",
                batch_id=batch_id,
                vote_count=vote_count,
                total_voters=total_voters,
                message_id=active_batch.message_id,
            )

            # Reconstruct the batch message with updated vote count
            deadline = datetime.fromisoformat(active_batch.deadline)

            issue_list = "\n".join(
                [
                    f"• #{issue.issue_number} - " + f"[{issue.title}]({issue.url})"
                    if issue.url
                    else f"{issue.title}"
                    for issue in active_batch.issues
                ]
            )

            voter_mentions = ", ".join([f"@**{voter}**" for voter in self.config.voter_list])

            topic_content = f"""**📦 BATCH REFINEMENT**
**Stories**:
{issue_list}

**Deadline**: {deadline.strftime("%Y-%m-%d %H:%M UTC")} ({self.config.default_deadline_hours} hours from now)
**Facilitator**: @**{active_batch.facilitator}**

**How to estimate**:
1. Review issues in GitHub
2. Consider complexity, unknowns, dependencies for each
3. DM @**Refinement Bot** your story point estimates in this format:
   `#{active_batch.issues[0].issue_number}: 5, #{active_batch.issues[1].issue_number if len(active_batch.issues) > 1 else active_batch.issues[0].issue_number}: 8, #{active_batch.issues[2].issue_number if len(active_batch.issues) > 2 else active_batch.issues[0].issue_number}: 3`
4. Use scale: 1, 2, 3, 5, 8, 13, 21

**Voters needed**: {voter_mentions}

**Status**: ⏳ Collecting estimates ({vote_count}/{total_voters} received)

*Will reveal results here once all votes are in*"""

            # Update the message in the stream if we have the message ID
            if active_batch.message_id:
                try:
                    logger.debug(
                        "Attempting to update message",
                        message_id=active_batch.message_id,
                        content_length=len(topic_content),
                    )

                    edit_response = self.zulip_client.update_message(
                        {
                            "message_id": active_batch.message_id,
                            "content": topic_content,
                        }
                    )

                    if edit_response.get("result") == "success":
                        logger.info(
                            "Batch message updated successfully",
                            batch_id=batch_id,
                            message_id=active_batch.message_id,
                            vote_count=vote_count,
                            total_voters=total_voters,
                        )
                    else:
                        logger.error(
                            "Failed to update batch message - API returned error",
                            batch_id=batch_id,
                            message_id=active_batch.message_id,
                            response=edit_response,
                            error_code=edit_response.get("code"),
                            error_msg=edit_response.get("msg"),
                        )
                except Exception as edit_error:
                    logger.error(
                        "Exception while updating batch message",
                        batch_id=batch_id,
                        message_id=active_batch.message_id,
                        error=str(edit_error),
                        error_type=type(edit_error).__name__,
                    )
            else:
                logger.warning(
                    "Cannot update batch message: no message ID stored - batch message was likely not created successfully",
                    batch_id=batch_id,
                    vote_count=vote_count,
                    total_voters=total_voters,
                )

        except Exception as e:
            logger.error("Failed to update batch message", batch_id=batch_id, error=str(e))

    def _deadline_checker_loop(self) -> None:
        """Background thread that checks for expired batches."""
        while self._deadline_checker_running:
            try:
                self._check_expired_batches()
            except Exception as e:
                logger.error("Error in deadline checker", error=str(e))

            # Check every 5 minutes
            time.sleep(300)

    def _check_expired_batches(self) -> None:
        """Check for and process any expired batches."""
        active_batch = self.db_manager.get_active_batch()
        if not active_batch or active_batch.id is None:
            return

        deadline = datetime.fromisoformat(active_batch.deadline)
        now = datetime.now(UTC)

        if now >= deadline:
            logger.info(
                "Batch deadline expired, processing results",
                batch_id=active_batch.id,
                deadline=deadline,
                now=now,
            )
            self._process_batch_completion(active_batch)

    def _process_batch_completion(self, batch: BatchData) -> None:
        """Process completion of an expired batch."""
        if batch.id is None:
            logger.error("Cannot process batch completion: batch ID is None")
            return

        try:
            # Get all votes for this batch
            votes = self.db_manager.get_batch_votes(batch.id)
            vote_count = self.db_manager.get_vote_count_by_voter(batch.id)
            total_voters = len(self.config.voter_list)

            # Update original message status
            self._update_batch_completion_status(
                batch, vote_count, total_voters, auto_completed=False
            )

            # Generate and post results
            self._post_estimation_results(batch, votes, vote_count, total_voters)

            # Mark batch as completed
            self.db_manager.complete_batch(batch.id)

            logger.info(
                "Batch completion processed successfully",
                batch_id=batch.id,
                vote_count=vote_count,
                total_voters=total_voters,
            )

        except Exception as e:
            logger.error("Error processing batch completion", batch_id=batch.id, error=str(e))

    def _process_batch_completion_auto(self, batch: BatchData) -> None:
        """Process completion of a batch when all voters have voted.

        Args:
            batch: The batch to complete
        """
        if batch.id is None:
            logger.error("Cannot process auto batch completion: batch ID is None")
            return

        try:
            # Get all votes for this batch
            votes = self.db_manager.get_batch_votes(batch.id)
            vote_count = self.db_manager.get_vote_count_by_voter(batch.id)
            total_voters = len(self.config.voter_list)

            # Update original message status (with auto-completion flag)
            self._update_batch_completion_status(
                batch, vote_count, total_voters, auto_completed=True
            )

            # Generate and post results
            self._post_estimation_results(batch, votes, vote_count, total_voters)

            # Mark batch as completed
            self.db_manager.complete_batch(batch.id)

            logger.info(
                "Auto batch completion processed successfully",
                batch_id=batch.id,
                vote_count=vote_count,
                total_voters=total_voters,
            )

        except Exception as e:
            logger.error("Error processing auto batch completion", batch_id=batch.id, error=str(e))

    def _update_batch_completion_status(
        self, batch: BatchData, vote_count: int, total_voters: int, auto_completed: bool = False
    ) -> None:
        """Update the original batch message to show completion status.

        Args:
            batch: The batch data
            vote_count: Number of voters who submitted votes
            total_voters: Total number of expected voters
            auto_completed: True if completed automatically due to all votes received
        """
        if not batch.message_id:
            logger.warning("Cannot update completion status: no message ID", batch_id=batch.id)
            return

        try:
            deadline = datetime.fromisoformat(batch.deadline)
            issue_list = "\n".join(
                [
                    f"• #{issue.issue_number} - " + f"[{issue.title}]({issue.url})"
                    if issue.url
                    else f"{issue.title}"
                    for issue in batch.issues
                ]
            )

            voter_mentions = ", ".join([f"@**{voter}**" for voter in self.config.voter_list])

            # Determine completion reason
            completion_reason = "All votes received" if auto_completed else "Deadline reached"

            completed_content = f"""**📦 BATCH REFINEMENT - COMPLETED** ({completion_reason})
**Stories**:
{issue_list}

**Deadline**: {deadline.strftime("%Y-%m-%d %H:%M UTC")} ({self.config.default_deadline_hours} hours from now)
**Facilitator**: @**{batch.facilitator}**

**How to estimate**:
1. Review issues in GitHub
2. Consider complexity, unknowns, dependencies for each
3. DM @**Refinement Bot** your story point estimates in this format:
   `#{batch.issues[0].issue_number}: 5, #{batch.issues[1].issue_number if len(batch.issues) > 1 else batch.issues[0].issue_number}: 8, #{batch.issues[2].issue_number if len(batch.issues) > 2 else batch.issues[0].issue_number}: 3`
4. Use scale: 1, 2, 3, 5, 8, 13, 21

**Voters needed**: {voter_mentions}

**Status**: ✅ Vote complete ({vote_count}/{total_voters} received)

*Results posted below*"""

            edit_response = self.zulip_client.update_message(
                {
                    "message_id": batch.message_id,
                    "content": completed_content,
                }
            )

            if edit_response.get("result") == "success":
                logger.info(
                    "Updated batch message with completion status",
                    batch_id=batch.id,
                    message_id=batch.message_id,
                )
            else:
                logger.error(
                    "Failed to update batch completion status",
                    batch_id=batch.id,
                    response=edit_response,
                )

        except Exception as e:
            logger.error("Error updating batch completion status", batch_id=batch.id, error=str(e))

    def _post_estimation_results(
        self, batch: BatchData, votes: list[EstimationVote], vote_count: int, total_voters: int
    ) -> None:
        """Post detailed estimation results to the stream."""
        try:
            # Generate results content
            results_content = self._generate_results_content(batch, votes, vote_count, total_voters)

            # Post to the same topic
            topic_name = f"Refinement: {batch.date} ({len(batch.issues)} issues)"

            response = self._send_message_with_retry(
                {
                    "type": "stream",
                    "to": self.config.stream_name,
                    "topic": topic_name,
                    "content": results_content,
                }
            )

            if response.get("result") == "success":
                logger.info(
                    "Posted estimation results",
                    batch_id=batch.id,
                    topic=topic_name,
                )
            else:
                logger.error(
                    "Failed to post estimation results",
                    batch_id=batch.id,
                    response=response,
                )

        except Exception as e:
            logger.error("Error posting estimation results", batch_id=batch.id, error=str(e))

    def _generate_results_content(
        self, batch: BatchData, votes: list[EstimationVote], vote_count: int, total_voters: int
    ) -> str:
        """Generate the content for the estimation results message."""
        # Group votes by issue
        votes_by_issue: dict[str, list[EstimationVote]] = {}
        for vote in votes:
            if vote.issue_number not in votes_by_issue:
                votes_by_issue[vote.issue_number] = []
            votes_by_issue[vote.issue_number].append(vote)

        # Find voters who didn't vote
        all_voters = set(self.config.voter_list)
        voted_voters = {vote.voter for vote in votes}
        non_voters = all_voters - voted_voters

        results_content = "🎲 **ESTIMATION RESULTS**\n\n"

        if non_voters:
            results_content += f"Note: {', '.join(f'@**{voter}**' for voter in sorted(non_voters))} didn't vote in this batch.\n\n"

        consensus_issues = []
        discussion_issues = []

        # Process each issue
        for issue in batch.issues:
            issue_votes = votes_by_issue.get(issue.issue_number, [])
            if not issue_votes:
                continue

            estimates = [vote.points for vote in issue_votes]
            estimates.sort()

            # Note: Fibonacci validation is now enforced during vote submission

            # Analyze consensus
            estimate_counts = Counter(estimates)
            most_common = estimate_counts.most_common()

            # Determine consensus vs discussion needed
            if len(most_common) == 1:
                # Perfect consensus
                final_estimate = most_common[0][0]
                consensus_issues.append((issue, estimates, final_estimate, "perfect"))
            elif len(estimates) >= 3:
                # Check for clustering
                sorted_estimates = sorted(estimates)
                clusters = self._find_clusters(sorted_estimates)

                if len(clusters) == 1 and len(clusters[0]) >= len(estimates) * 0.6:
                    # Strong cluster consensus
                    cluster = clusters[0]
                    final_estimate = max(cluster)  # Take highest in cluster for safety
                    consensus_issues.append((issue, estimates, final_estimate, "cluster"))
                else:
                    # Needs discussion
                    discussion_issues.append((issue, estimates, clusters))
            else:
                # Too few votes for meaningful analysis
                discussion_issues.append((issue, estimates, []))

        # Generate consensus section
        if consensus_issues:
            results_content += "✅ **CONSENSUS REACHED**\n"
            for issue, estimates, final_estimate, consensus_type in consensus_issues:
                estimates_str = ", ".join(map(str, estimates))
                if consensus_type == "perfect":
                    cluster_info = "(perfect consensus)"
                else:
                    cluster_info = f"({self._format_cluster_info(estimates, final_estimate)})"

                results_content += f"Issue {issue.issue_number} - {issue.title}\n"
                results_content += f"Estimates: {estimates_str}\n"
                results_content += (
                    f"Cluster: {cluster_info} | Final: **{final_estimate} points**\n\n"
                )

        # Generate discussion section
        if discussion_issues:
            results_content += "⚠️ **DISCUSSION NEEDED**\n"
            for issue, estimates, clusters in discussion_issues:
                estimates_str = ", ".join(map(str, estimates))
                results_content += f"Issue {issue.issue_number} - {issue.title}\n"
                results_content += f"Estimates: {estimates_str}\n"

                if len(clusters) > 1:
                    cluster_strs = []
                    for cluster in clusters:
                        cluster_strs.append(f"[{','.join(map(str, cluster))}]")
                    results_content += f"Clusters: {' vs '.join(cluster_strs)} - Mixed agreement\n"
                else:
                    results_content += "Wide spread - Needs discussion\n"

                # Add questions for voters with outlying estimates
                if estimates:
                    min_est, max_est = min(estimates), max(estimates)
                    if max_est - min_est > 5:  # Significant spread
                        high_voters = [
                            v.voter
                            for v in votes_by_issue[issue.issue_number]
                            if v.points == max_est
                        ]
                        low_voters = [
                            v.voter
                            for v in votes_by_issue[issue.issue_number]
                            if v.points == min_est
                        ]

                        if high_voters:
                            results_content += f"    @**{' @**'.join(high_voters)}** : What complexity are you seeing that pushes this to {max_est}?\n"
                        if low_voters:
                            results_content += f"    @**{' @**'.join(low_voters)}** : What's making this feel like a smaller story ({min_est} points)?\n"

                results_content += "\n"

        if discussion_issues:
            results_content += "Next steps: Discussion phase for the disputed stories, then re-estimate if needed.\n"

        return results_content

    def _find_clusters(self, sorted_estimates: list[int]) -> list[list[int]]:
        """Find clusters in sorted estimates using a simple gap-based approach."""
        if not sorted_estimates:
            return []

        clusters = [[sorted_estimates[0]]]

        for i in range(1, len(sorted_estimates)):
            current = sorted_estimates[i]
            previous = sorted_estimates[i - 1]

            # If gap is too large, start new cluster
            # Use Fibonacci gaps: 1->2 (gap 1), 2->3 (gap 1), 3->5 (gap 2), 5->8 (gap 3), etc.
            if current - previous > 2:
                clusters.append([current])
            else:
                clusters[-1].append(current)

        return clusters

    def _format_cluster_info(self, estimates: list[int], final_estimate: int) -> str:
        """Format cluster information for display."""
        clusters = self._find_clusters(sorted(estimates))

        if len(clusters) == 1:
            cluster = clusters[0]
            if len(set(cluster)) == 1:
                return "tight consensus"
            else:
                cluster_str = ",".join(map(str, sorted(set(cluster))))
                outliers = [est for est in estimates if est not in cluster]
                if outliers:
                    outlier_str = ",".join(map(str, sorted(set(outliers))))
                    return f"{cluster_str} (one {outlier_str} outlier)"
                else:
                    return f"{cluster_str} cluster"
        else:
            return "mixed clusters"

    def _send_reply(self, message: dict[str, Any], content: str) -> None:
        """Send a reply to a message.

        Args:
            message: Original message to reply to
            content: Reply content
        """
        try:
            response = self._send_message_with_retry(
                {
                    "type": "private",
                    "to": [message["sender_email"]],
                    "content": content,
                }
            )

            if response.get("result") == "success":
                logger.debug("Sent private message reply", recipient=message["sender_email"])
            else:
                logger.error(
                    "Failed to send private message reply - API error",
                    recipient=message["sender_email"],
                    response=response,
                )
        except Exception as e:
            logger.error("Failed to send reply", error=str(e))

    def stop(self) -> None:
        """Stop the bot and cleanup resources."""
        logger.info("Stopping Zulip Refinement Bot")
        self._deadline_checker_running = False
        if hasattr(self, "_deadline_checker_thread"):
            self._deadline_checker_thread.join(timeout=5.0)

    def run(self) -> None:
        """Run the bot (blocking call)."""
        logger.info("Starting Zulip Refinement Bot")

        try:

            def message_handler(message: dict[str, Any]) -> None:
                """Handle incoming messages."""
                self.handle_message(message)

            # Register message handler and start listening
            self.zulip_client.call_on_each_message(message_handler)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()

    def _send_message_with_retry(
        self, message_data: dict[str, Any], max_retries: int = 3
    ) -> ZulipResponse:
        """Send a message with automatic retry on rate limits.

        Args:
            message_data: The message data to send
            max_retries: Maximum number of retry attempts

        Returns:
            The API response

        Raises:
            Exception: If all retries are exhausted or non-rate-limit error occurs
        """
        for attempt in range(max_retries + 1):
            try:
                response = self.zulip_client.send_message(message_data)

                # Check if we hit a rate limit
                if response.get("result") == "error" and response.get("code") == "RATE_LIMIT_HIT":
                    retry_after = response.get("retry-after", 1.0)

                    if attempt < max_retries:
                        logger.warning(
                            "Rate limit hit, retrying after delay",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            retry_after=retry_after,
                        )
                        time.sleep(retry_after)
                        continue
                    else:
                        logger.error(
                            "Rate limit hit, max retries exhausted",
                            max_retries=max_retries,
                            response=response,
                        )
                        raise Exception(f"Rate limit exceeded after {max_retries} retries")

                return cast(ZulipResponse, response)

            except Exception as e:
                if attempt < max_retries and "rate limit" in str(e).lower():
                    logger.warning(
                        "Exception during message send, retrying",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    time.sleep(2**attempt)  # Exponential backoff
                    continue
                else:
                    raise

        # This should never be reached, but just in case
        raise Exception("Unexpected error in retry logic")
