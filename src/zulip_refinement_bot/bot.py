"""Main bot implementation for the Zulip Refinement Bot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
import zulip

from .config import Config
from .database import DatabaseManager
from .github_api import GitHubAPI
from .models import IssueData, MessageData
from .parser import InputParser

logger = structlog.get_logger(__name__)


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

        # Initialize Zulip client
        self.zulip_client = zulip.Client(
            email=config.zulip_email,
            api_key=config.zulip_api_key,
            site=config.zulip_site,
        )

        logger.info("Refinement bot initialized", config=config.dict(exclude={"zulip_api_key"}))

    def usage(self) -> str:
        """Return usage instructions for the bot."""
        return f"""
        **Zulip Story Point Estimation Bot - Phase 1**

        **Commands (DM only):**
        • `start batch` - Create new estimation batch
        • `status` - Show active batch info
        • `cancel` - Cancel active batch (facilitator only)

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
        • One vote per voter per batch
        """

    def handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming messages.

        Args:
            message: Zulip message data
        """
        try:
            msg_data = MessageData(**message)

            # Only respond to direct messages for commands
            if msg_data.type != "private":
                return

            content = msg_data.content.strip()

            if not content or content.lower() in ["help", "usage"]:
                self._send_reply(message, self.usage())
                return

            # Parse command
            if content.lower().startswith("start batch"):
                self._handle_start_batch(message, content)
            elif content.lower() == "status":
                self._handle_status(message)
            elif content.lower() == "cancel":
                self._handle_cancel(message)
            else:
                # Check if this might be a vote submission
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
        # Check for existing active batch
        active_batch = self.db_manager.get_active_batch()
        if active_batch:
            self._send_reply(
                message, "❌ Active batch already running. Use 'status' to check progress."
            )
            return

        # Parse input
        parse_result = self.parser.parse_batch_input(content)
        if not parse_result.success:
            self._send_reply(message, parse_result.error)
            return

        # Create batch
        facilitator = message["sender_full_name"]
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")
        deadline = now + timedelta(hours=self.config.default_deadline_hours)
        deadline_str = deadline.isoformat()

        try:
            batch_id = self.db_manager.create_batch(date_str, deadline_str, facilitator)
            self.db_manager.add_issues_to_batch(batch_id, parse_result.issues)

            # Send confirmation DM
            self._send_batch_confirmation(message, parse_result.issues, deadline, date_str)

            # Create topic in stream
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

        # Check if user is the facilitator
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
            response = self.zulip_client.send_message(
                {
                    "type": "stream",
                    "to": self.config.stream_name,
                    "topic": topic_name,
                    "content": topic_content,
                }
            )

            # Store the message ID for future updates
            if response.get("result") == "success" and "id" in response:
                message_id = response["id"]
                self.db_manager.update_batch_message_id(batch_id, message_id)
                logger.info(
                    "Created batch topic",
                    batch_id=batch_id,
                    topic=topic_name,
                    message_id=message_id,
                )
            else:
                logger.warning("Message sent but no ID returned", response=response)

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

        # Look for pattern like "#1234: 5" anywhere in the content
        vote_pattern = re.compile(r"#\d+:\s*\d+")
        return bool(vote_pattern.search(content))

    def _handle_vote_submission(self, message: dict[str, Any], content: str) -> None:
        """Handle vote submission from a user.

        Args:
            message: Zulip message data
            content: Vote content
        """
        voter_name = message["sender_full_name"]

        # Check if voter is authorized
        if voter_name not in self.config.voter_list:
            self._send_reply(
                message,
                f"❌ You are not authorized to vote. Authorized voters: {', '.join(self.config.voter_list)}",
            )
            return

        # Check if there's an active batch
        active_batch = self.db_manager.get_active_batch()
        if not active_batch or active_batch.id is None:
            self._send_reply(message, "❌ No active batch found. Cannot submit votes.")
            return

        # Check if voter has already voted
        if self.db_manager.has_voter_voted(active_batch.id, voter_name):
            self._send_reply(
                message,
                "❌ You have already submitted votes for this batch. Each voter can only vote once per batch.",
            )
            return

        # Parse the votes
        estimates = self.parser.parse_estimation_input(content)
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

        # Store all votes
        stored_count = 0
        for issue_number, points in estimates.items():
            if self.db_manager.store_vote(active_batch.id, voter_name, issue_number, points):
                stored_count += 1

        if stored_count == len(estimates):
            # All votes stored successfully
            vote_summary = ", ".join([f"#{issue}: {points}" for issue, points in estimates.items()])
            self._send_reply(
                message,
                f"✅ **Votes recorded successfully!**\n\n"
                f"Your estimates: {vote_summary}\n\n"
                f"Thank you for participating in the refinement process.",
            )

            # Update the batch message with new vote count
            self._update_batch_message(active_batch.id)
        else:
            self._send_reply(
                message,
                f"⚠️ Only {stored_count} out of {len(estimates)} votes were stored. "
                "Some votes may have been duplicates.",
            )

    def _update_batch_message(self, batch_id: int) -> None:
        """Update the batch refinement message with current vote count.

        Args:
            batch_id: ID of the batch to update
        """
        try:
            # Get current batch data
            active_batch = self.db_manager.get_active_batch()
            if not active_batch or active_batch.id != batch_id:
                logger.warning(
                    "Cannot update batch message: batch not found or not active", batch_id=batch_id
                )
                return

            # Get vote count
            vote_count = self.db_manager.get_vote_count_by_voter(batch_id)
            total_voters = len(self.config.voter_list)

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
                        logger.warning(
                            "Failed to update batch message",
                            batch_id=batch_id,
                            message_id=active_batch.message_id,
                            response=edit_response,
                        )
                except Exception as edit_error:
                    logger.error(
                        "Error updating batch message",
                        batch_id=batch_id,
                        message_id=active_batch.message_id,
                        error=str(edit_error),
                    )
            else:
                logger.warning(
                    "Cannot update batch message: no message ID stored", batch_id=batch_id
                )

        except Exception as e:
            logger.error("Failed to update batch message", batch_id=batch_id, error=str(e))

    def _send_reply(self, message: dict[str, Any], content: str) -> None:
        """Send a reply to a message.

        Args:
            message: Original message to reply to
            content: Reply content
        """
        try:
            self.zulip_client.send_message(
                {
                    "type": "private",
                    "to": [message["sender_email"]],
                    "content": content,
                }
            )
        except Exception as e:
            logger.error("Failed to send reply", error=str(e))

    def run(self) -> None:
        """Run the bot (blocking call)."""
        logger.info("Starting Zulip Refinement Bot")

        def message_handler(message: dict[str, Any]) -> None:
            """Handle incoming messages."""
            self.handle_message(message)

        # Register message handler and start listening
        self.zulip_client.call_on_each_message(message_handler)
