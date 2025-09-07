"""Message handlers for the Zulip Refinement Bot."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import structlog

from .business_hours import BusinessHoursCalculator
from .config import Config
from .exceptions import AuthorizationError, BatchError, ValidationError, VotingError
from .interfaces import MessageHandlerInterface, ZulipClientInterface
from .models import BatchData, IssueData
from .services import BatchService, ResultsService, VotingService

logger = structlog.get_logger(__name__)


class MessageHandler(MessageHandlerInterface):
    """Handles incoming Zulip messages and routes them to appropriate services."""

    def __init__(
        self,
        config: Config,
        zulip_client: ZulipClientInterface,
        batch_service: BatchService,
        voting_service: VotingService,
        results_service: ResultsService,
    ) -> None:
        """Initialize message handler.

        Args:
            config: Bot configuration
            zulip_client: Zulip client interface
            batch_service: Batch management service
            voting_service: Voting service
            results_service: Results service
        """
        self.config = config
        self.zulip_client = zulip_client
        self.batch_service = batch_service
        self.voting_service = voting_service
        self.results_service = results_service
        self.business_hours_calc = BusinessHoursCalculator(config)

    def handle_start_batch(self, message: dict[str, Any], content: str) -> None:
        """Handle batch creation request.

        Args:
            message: Zulip message data
            content: Message content
        """
        try:
            facilitator = message["sender_full_name"]
            batch_id, issues, deadline = self.batch_service.create_batch(content, facilitator)

            # Send confirmation to user
            self._send_batch_confirmation(message, issues, deadline, batch_id)

            # Create batch topic in stream
            self._create_batch_topic(batch_id, issues, deadline, facilitator)

        except (BatchError, ValidationError) as e:
            self._send_reply(message, f"❌ {e.message}")
        except Exception as e:
            logger.error("Unexpected error creating batch", error=str(e))
            self._send_reply(message, "❌ An unexpected error occurred. Please try again.")

    def handle_status(self, message: dict[str, Any]) -> None:
        """Handle status request.

        Args:
            message: Zulip message data
        """
        try:
            active_batch = self.batch_service.get_active_batch()
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
**Deadline**: {self.business_hours_calc.format_business_deadline(deadline)}
**Issues** ({len(active_batch.issues)}):
{issue_list}

**Topic**: Refinement: {active_batch.date} ({len(active_batch.issues)} issues)
**Stream**: #{self.config.stream_name}"""

            self._send_reply(message, status_msg)

        except Exception as e:
            logger.error("Error handling status request", error=str(e))
            self._send_reply(message, "❌ Error retrieving status. Please try again.")

    def handle_cancel(self, message: dict[str, Any]) -> None:
        """Handle batch cancellation request.

        Args:
            message: Zulip message data
        """
        try:
            active_batch = self.batch_service.get_active_batch()
            if not active_batch or active_batch.id is None:
                self._send_reply(message, "✅ No active batch to cancel.")
                return

            requester = message["sender_full_name"]
            self.batch_service.cancel_batch(active_batch.id, requester)
            self._send_reply(message, "✅ Batch cancelled successfully.")

        except (BatchError, AuthorizationError) as e:
            self._send_reply(message, f"❌ {e.message}")
        except Exception as e:
            logger.error("Error handling cancel request", error=str(e))
            self._send_reply(message, "❌ Error cancelling batch. Please try again.")

    def handle_complete(self, message: dict[str, Any]) -> None:
        """Handle batch completion request.

        Args:
            message: Zulip message data
        """
        try:
            active_batch = self.batch_service.get_active_batch()
            if not active_batch or active_batch.id is None:
                self._send_reply(message, "✅ No active batch to complete.")
                return

            requester = message["sender_full_name"]
            completed_batch = self.batch_service.complete_batch(active_batch.id, requester)

            # Process completion and generate results
            self._process_batch_completion(completed_batch, auto_completed=False)
            self._send_reply(
                message, "✅ Batch completed successfully. Results posted to the stream."
            )

        except (BatchError, AuthorizationError) as e:
            self._send_reply(message, f"❌ {e.message}")
        except Exception as e:
            logger.error("Error handling complete request", error=str(e))
            self._send_reply(message, "❌ Error completing batch. Please try again.")

    def handle_vote_submission(self, message: dict[str, Any], content: str) -> None:
        """Handle vote submission from a user.

        Args:
            message: Zulip message data
            content: Vote content
        """
        try:
            voter = message["sender_full_name"]
            active_batch = self.batch_service.get_active_batch()

            if not active_batch:
                self._send_reply(message, "❌ No active batch found. Cannot submit votes.")
                return

            # Submit votes
            estimates, has_updates, all_voters_complete = self.voting_service.submit_votes(
                content, voter, active_batch
            )

            # Send success message
            vote_summary = ", ".join([f"#{issue}: {points}" for issue, points in estimates.items()])

            if has_updates:
                action_msg = "**Votes updated successfully!**"
            else:
                action_msg = "**Votes recorded successfully!**"

            self._send_reply(
                message,
                f"✅ {action_msg}\n\n"
                f"Your estimates: {vote_summary}\n\n"
                f"Thank you for participating in the refinement process.",
            )

            # Update batch message with current vote count
            if active_batch.id:
                self._update_batch_message(active_batch.id, active_batch)

                # Check if all voters have completed
                if all_voters_complete:
                    self._process_batch_completion(active_batch, auto_completed=True)

        except (AuthorizationError, ValidationError, VotingError) as e:
            self._send_reply(message, f"❌ {e.message}")
        except Exception as e:
            logger.error("Error handling vote submission", error=str(e))
            self._send_reply(message, "❌ Error processing votes. Please try again.")

    def is_vote_format(self, content: str) -> bool:
        """Check if content looks like a vote submission.

        Args:
            content: Message content to check

        Returns:
            True if content appears to be in vote format
        """
        vote_pattern = re.compile(r"#\d+:\s*\d+")
        return bool(vote_pattern.search(content))

    def _send_reply(self, message: dict[str, Any], content: str) -> None:
        """Send a reply to a message.

        Args:
            message: Original message to reply to
            content: Reply content
        """
        try:
            response = self.zulip_client.send_message(
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
                    "Failed to send private message reply",
                    recipient=message["sender_email"],
                    response=response,
                )
        except Exception as e:
            logger.error("Failed to send reply", error=str(e))

    def _send_batch_confirmation(
        self, message: dict[str, Any], issues: list[IssueData], deadline: datetime, batch_id: int
    ) -> None:
        """Send confirmation message to user who created the batch.

        Args:
            message: Original message
            issues: List of issues in the batch
            deadline: Batch deadline
            batch_id: Database batch ID
        """
        issue_list = "\n".join(
            [
                f"• #{issue.issue_number}: {issue.title}"
                + (f" ([link]({issue.url}))" if issue.url else "")
                for issue in issues
            ]
        )

        date_str = deadline.strftime("%Y-%m-%d")
        confirmation = f"""✅ **Batch created: {len(issues)} issues**
📅 **Deadline**: {self.business_hours_calc.format_business_deadline(deadline)}
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
    ) -> None:
        """Create the batch topic in the stream.

        Args:
            batch_id: Database batch ID
            issues: List of issues
            deadline: Batch deadline
            facilitator: Facilitator name
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

        # Create example format string
        example_issues = [
            issues[0].issue_number,
            issues[1].issue_number if len(issues) > 1 else issues[0].issue_number,
            issues[2].issue_number if len(issues) > 2 else issues[0].issue_number,
        ]
        example_format = (
            f"#{example_issues[0]}: 5, #{example_issues[1]}: 8, #{example_issues[2]}: 3"
        )

        deadline_str = self.business_hours_calc.format_business_deadline(deadline)
        hours_text = f"({self.config.default_deadline_hours} hours from now)"

        topic_content = f"""**📦 BATCH REFINEMENT**
**Stories**:
{issue_list}

**Deadline**: {deadline_str} {hours_text}
**Facilitator**: @**{facilitator}**

**How to estimate**:
1. Review issues in GitHub
2. Consider complexity, unknowns, dependencies for each
3. DM @**Refinement Bot** your story point estimates in this format:
   `{example_format}`
4. Use scale: 1, 2, 3, 5, 8, 13, 21

**Voters needed**: {voter_mentions}

**Status**: ⏳ Collecting estimates (0/{len(self.config.voter_list)} received)

*Will reveal results here once all votes are in*"""

        date_str = deadline.strftime("%Y-%m-%d")
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

            if response.get("result") == "success" and "id" in response:
                message_id = response["id"]
                self.batch_service.database.update_batch_message_id(batch_id, message_id)
                logger.info(
                    "Created batch topic",
                    batch_id=batch_id,
                    topic=topic_name,
                    message_id=message_id,
                )
            else:
                logger.error(
                    "Failed to create batch topic",
                    batch_id=batch_id,
                    response=response,
                )

        except Exception as e:
            logger.error("Failed to create batch topic", batch_id=batch_id, error=str(e))

    def _update_batch_message(self, batch_id: int, active_batch: BatchData) -> None:
        """Update the batch refinement message with current vote count.

        Args:
            batch_id: ID of the batch to update
            active_batch: Batch data
        """
        try:
            if not active_batch.message_id:
                logger.warning("Cannot update batch message: no message ID", batch_id=batch_id)
                return

            # Get vote count
            vote_count, total_voters, _ = self.voting_service.check_completion_status(batch_id)

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

            # Create example format string
            example_issues = [
                active_batch.issues[0].issue_number,
                (
                    active_batch.issues[1].issue_number
                    if len(active_batch.issues) > 1
                    else active_batch.issues[0].issue_number
                ),
                (
                    active_batch.issues[2].issue_number
                    if len(active_batch.issues) > 2
                    else active_batch.issues[0].issue_number
                ),
            ]
            example_format = (
                f"#{example_issues[0]}: 5, #{example_issues[1]}: 8, #{example_issues[2]}: 3"
            )

            deadline_str = self.business_hours_calc.format_business_deadline(deadline)
            hours_text = f"({self.config.default_deadline_hours} hours from now)"

            topic_content = f"""**📦 BATCH REFINEMENT**
**Stories**:
{issue_list}

**Deadline**: {deadline_str} {hours_text}
**Facilitator**: @**{active_batch.facilitator}**

**How to estimate**:
1. Review issues in GitHub
2. Consider complexity, unknowns, dependencies for each
3. DM @**Refinement Bot** your story point estimates in this format:
   `{example_format}`
4. Use scale: 1, 2, 3, 5, 8, 13, 21

**Voters needed**: {voter_mentions}

**Status**: ⏳ Collecting estimates ({vote_count}/{total_voters} received)

*Will reveal results here once all votes are in*"""

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
                    "Failed to update batch message",
                    batch_id=batch_id,
                    response=edit_response,
                )

        except Exception as e:
            logger.error("Failed to update batch message", batch_id=batch_id, error=str(e))

    def _process_batch_completion(self, batch: BatchData, auto_completed: bool = False) -> None:
        """Process completion of a batch.

        Args:
            batch: The batch to complete
            auto_completed: True if completed automatically due to all votes received
        """
        if batch.id is None:
            logger.error("Cannot process batch completion: batch ID is None")
            return

        try:
            # Get all votes for this batch
            votes = self.voting_service.get_batch_votes(batch.id)
            vote_count, total_voters, _ = self.voting_service.check_completion_status(batch.id)

            # Update original message status
            self._update_batch_completion_status(batch, vote_count, total_voters, auto_completed)

            # Generate and post results
            self._post_estimation_results(batch, votes, vote_count, total_voters)

            logger.info(
                "Batch completion processed successfully",
                batch_id=batch.id,
                vote_count=vote_count,
                total_voters=total_voters,
                auto_completed=auto_completed,
            )

        except Exception as e:
            logger.error("Error processing batch completion", batch_id=batch.id, error=str(e))

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

            # Create example format string
            example_issues = [
                batch.issues[0].issue_number,
                (
                    batch.issues[1].issue_number
                    if len(batch.issues) > 1
                    else batch.issues[0].issue_number
                ),
                (
                    batch.issues[2].issue_number
                    if len(batch.issues) > 2
                    else batch.issues[0].issue_number
                ),
            ]
            example_format = (
                f"#{example_issues[0]}: 5, #{example_issues[1]}: 8, #{example_issues[2]}: 3"
            )

            deadline_str = self.business_hours_calc.format_business_deadline(deadline)
            hours_text = f"({self.config.default_deadline_hours} hours from now)"

            completed_content = f"""**📦 BATCH REFINEMENT - COMPLETED** ({completion_reason})
**Stories**:
{issue_list}

**Deadline**: {deadline_str} {hours_text}
**Facilitator**: @**{batch.facilitator}**

**How to estimate**:
1. Review issues in GitHub
2. Consider complexity, unknowns, dependencies for each
3. DM @**Refinement Bot** your story point estimates in this format:
   `{example_format}`
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
        self, batch: BatchData, votes: list, vote_count: int, total_voters: int
    ) -> None:
        """Post detailed estimation results to the stream.

        Args:
            batch: Batch data
            votes: All votes for the batch
            vote_count: Number of voters who submitted votes
            total_voters: Total number of expected voters
        """
        try:
            # Generate results content
            results_content = self.results_service.generate_results_content(
                batch, votes, vote_count, total_voters
            )

            # Post to the same topic
            topic_name = f"Refinement: {batch.date} ({len(batch.issues)} issues)"

            response = self.zulip_client.send_message(
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
