"""Message handlers for the Zulip Refinement Bot."""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime
from typing import Any

import structlog

from .business_hours import BusinessHoursCalculator
from .config import Config
from .exceptions import AuthorizationError, BatchError, ValidationError, VotingError
from .interfaces import MessageHandlerInterface, ZulipClientInterface
from .models import BatchData, FinalEstimate, IssueData
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

    def _parse_voter_name(self, text: str) -> str:
        """Parse voter name from text, handling Zulip mention format.

        Args:
            text: Raw text that may contain @**username** format

        Returns:
            Clean username without Zulip mention formatting
        """
        # Strip whitespace first
        text = text.strip()

        # Handle Zulip mention format: @**username**
        if text.startswith("@**") and text.endswith("**"):
            return text[3:-2]  # Remove @** and **

        # Return as-is for plain text names
        return text

    def _parse_voter_names(self, text: str) -> list[str]:
        """Parse multiple voter names from text, handling various formats.

        Supports formats like:
        - "John Doe, Jane Smith, Bob Wilson"
        - "@**jdoe**, @**jsmith**, Bob Wilson"
        - "John Doe and Jane Smith"
        - "John Doe, @**jsmith** and Bob Wilson"

        Args:
            text: Raw text containing one or more voter names

        Returns:
            List of clean usernames without Zulip mention formatting
        """
        import re

        # Replace "and" with commas for consistent parsing
        text = re.sub(r"\s+and\s+", ", ", text, flags=re.IGNORECASE)

        # Split by commas and clean up each name
        voter_names = []
        for name_part in text.split(","):
            name_part = name_part.strip()
            if name_part:  # Skip empty parts
                clean_name = self._parse_voter_name(name_part)
                if clean_name and clean_name not in voter_names:  # Avoid duplicates
                    voter_names.append(clean_name)

        return voter_names

    def handle_list_voters(self, message: dict[str, Any]) -> None:
        """Handle list voters command."""
        try:
            active_batch = self.batch_service.get_active_batch()
            if not active_batch or not active_batch.id:
                self._send_reply(message, "❌ No active batch found.")
                return

            voters = self.batch_service.database.get_batch_voters(active_batch.id)

            if not voters:
                self._send_reply(message, f"📋 No voters found for batch {active_batch.id}")
                return

            voter_list = "\n".join([f"• {voter}" for voter in voters])
            response = f"""📋 **Voters for Active Batch {active_batch.id}**

{voter_list}

**Total**: {len(voters)} voters"""

            self._send_reply(message, response)

        except Exception as e:
            logger.error("Error listing voters", error=str(e))
            self._send_reply(message, "❌ Error listing voters. Please try again.")

    def handle_add_voter(self, message: dict[str, Any], content: str) -> None:
        """Handle add voter command with support for multiple voters."""
        try:
            parts = content.split(maxsplit=1)
            if len(parts) < 2:
                self._send_reply(
                    message,
                    "❌ Please specify voter name(s). Format:\n"
                    "• `add John Doe`\n"
                    "• `add @**username**`\n"
                    "• `add John Doe, Jane Smith, @**bob**`\n"
                    "• `add Alice and Bob`",
                )
                return

            voter_names = self._parse_voter_names(parts[1])
            if not voter_names:
                self._send_reply(message, "❌ No valid voter names found.")
                return

            active_batch = self.batch_service.get_active_batch()
            if not active_batch or not active_batch.id:
                self._send_reply(message, "❌ No active batch found.")
                return

            # Process each voter
            added_voters = []
            already_present = []

            for voter_name in voter_names:
                was_added = self.batch_service.database.add_voter_to_batch(
                    active_batch.id, voter_name
                )
                if was_added:
                    added_voters.append(voter_name)
                else:
                    already_present.append(voter_name)

            # Build response message
            response_parts = []

            if added_voters:
                if len(added_voters) == 1:
                    response_parts.append(
                        f"✅ Added **{added_voters[0]}** to batch {active_batch.id}"
                    )
                else:
                    voter_list = ", ".join(f"**{name}**" for name in added_voters)
                    response_parts.append(f"✅ Added {voter_list} to batch {active_batch.id}")

                # Update batch message since voters were added
                self._update_batch_message(active_batch.id, active_batch)

            if already_present:
                if len(already_present) == 1:
                    response_parts.append(
                        f"ℹ️ **{already_present[0]}** was already in batch {active_batch.id}"
                    )
                else:
                    voter_list = ", ".join(f"**{name}**" for name in already_present)
                    response_parts.append(f"ℹ️ {voter_list} were already in batch {active_batch.id}")

            self._send_reply(message, "\n".join(response_parts))

        except Exception as e:
            logger.error("Error adding voter(s)", error=str(e))
            self._send_reply(message, "❌ Error adding voter(s). Please try again.")

    def handle_remove_voter(self, message: dict[str, Any], content: str) -> None:
        """Handle remove voter command with support for multiple voters."""
        try:
            parts = content.split(maxsplit=1)
            if len(parts) < 2:
                self._send_reply(
                    message,
                    "❌ Please specify voter name(s). Format:\n"
                    "• `remove John Doe`\n"
                    "• `remove @**username**`\n"
                    "• `remove John Doe, Jane Smith, @**bob**`\n"
                    "• `remove Alice and Bob`",
                )
                return

            voter_names = self._parse_voter_names(parts[1])
            if not voter_names:
                self._send_reply(message, "❌ No valid voter names found.")
                return

            active_batch = self.batch_service.get_active_batch()
            if not active_batch or not active_batch.id:
                self._send_reply(message, "❌ No active batch found.")
                return

            # Process each voter
            removed_voters = []
            not_present = []

            for voter_name in voter_names:
                was_removed = self.batch_service.database.remove_voter_from_batch(
                    active_batch.id, voter_name
                )
                if was_removed:
                    removed_voters.append(voter_name)
                else:
                    not_present.append(voter_name)

            # Build response message
            response_parts = []

            if removed_voters:
                if len(removed_voters) == 1:
                    response_parts.append(
                        f"✅ Removed **{removed_voters[0]}** from batch {active_batch.id}"
                    )
                else:
                    voter_list = ", ".join(f"**{name}**" for name in removed_voters)
                    response_parts.append(f"✅ Removed {voter_list} from batch {active_batch.id}")

                # Update batch message since voters were removed
                self._update_batch_message(active_batch.id, active_batch)

            if not_present:
                if len(not_present) == 1:
                    response_parts.append(
                        f"ℹ️ **{not_present[0]}** was not in batch {active_batch.id}"
                    )
                else:
                    voter_list = ", ".join(f"**{name}**" for name in not_present)
                    response_parts.append(f"ℹ️ {voter_list} were not in batch {active_batch.id}")

            self._send_reply(message, "\n".join(response_parts))

        except Exception as e:
            logger.error("Error removing voter(s)", error=str(e))
            self._send_reply(message, "❌ Error removing voter(s). Please try again.")

    def handle_finish(self, message: dict[str, Any], content: str) -> None:
        """Handle discussion complete command with final estimates.

        Expected format: discussion complete #issue1: points rationale, #issue2: points rationale
        """
        try:
            active_batch = self.batch_service.get_active_batch()
            if not active_batch or not active_batch.id:
                self._send_reply(message, "❌ No active batch found.")
                return

            if active_batch.status != "discussing":
                self._send_reply(
                    message,
                    f"❌ Batch is not in discussion phase (current: {active_batch.status}).",
                )
                return

            requester = message["sender_full_name"]

            # Parse the final estimates from the content
            final_estimates = self._parse_finish_input(content)

            if not final_estimates:
                self._send_reply(
                    message,
                    "❌ No valid final estimates found. Please use format:\n"
                    "`finish #1234: 5 rationale here, #1235: 8 another rationale`",
                )
                return

            # Complete the discussion phase
            completed_batch = self.batch_service.complete_discussion_phase(
                active_batch.id, requester, final_estimates
            )

            # Generate and post final results
            self._post_finish_results(completed_batch, final_estimates)

            self._send_reply(
                message,
                "✅ Discussion phase completed successfully. Final results posted to the stream.",
            )

        except (BatchError, AuthorizationError, ValidationError) as e:
            self._send_reply(message, f"❌ {e.message}")
        except Exception as e:
            logger.error("Error handling discussion complete", error=str(e))
            self._send_reply(message, "❌ Error completing discussion. Please try again.")

    def _parse_finish_input(self, content: str) -> dict[str, tuple[int, str]]:
        """Parse finish command input into final estimates.

        Args:
            content: Input like "finish #1234: 5 rationale, #1235: 8 rationale"

        Returns:
            Dict of issue_number -> (points, rationale)
        """
        import re

        # Remove the "finish" prefix
        content = content.replace("finish", "").strip()

        # Pattern to match #issue: points rationale
        pattern = r"#(\d+):\s*(\d+)\s*([^,#]*?)(?=,\s*#|\s*$)"
        matches = re.findall(pattern, content)

        final_estimates = {}
        valid_points = {1, 2, 3, 5, 8, 13, 21}

        for issue_num, points_str, rationale in matches:
            try:
                points = int(points_str)
                if points in valid_points:
                    final_estimates[issue_num] = (points, rationale.strip())
                else:
                    logger.warning(f"Invalid story points: {points} for issue {issue_num}")
            except ValueError:
                logger.warning(f"Could not parse points for issue {issue_num}: {points_str}")

        return final_estimates

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

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        confirmation = f"""✅ **Batch created: {len(issues)} issues**
📅 **Deadline**: {self.business_hours_calc.format_business_deadline(deadline)}
🎯 **Topic**: Refinement: {current_date} ({len(issues)} issues)

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

        batch_voters = self.batch_service.database.get_batch_voters(batch_id)
        voter_mentions = ", ".join([f"@**{voter}**" for voter in batch_voters])

        fibonacci_numbers = [1, 2, 3, 5, 8, 13, 21]
        example_parts = []
        for issue in issues:
            random_fib = random.choice(fibonacci_numbers)  # nosec B311
            example_parts.append(f"#{issue.issue_number}: {random_fib}")
        example_format = ", ".join(example_parts)

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

**Status**: ⏳ Collecting estimates (0/{len(batch_voters)} received)

*Will reveal results here once all votes are in*"""

        # Use current date for topic name (when refinement starts, not deadline)
        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        topic_name = f"Refinement: {current_date} ({len(issues)} issues)"

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

            batch_voters = self.batch_service.database.get_batch_voters(batch_id)
            voter_mentions = ", ".join([f"@**{voter}**" for voter in batch_voters])

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

            # Generate and post initial results
            results_content = self.results_service.generate_results_content(
                batch,
                votes,
                vote_count,
                total_voters,
                self.batch_service.database.get_batch_voters(batch.id),
            )

            # Check if there are discussion issues
            has_discussion_issues = "⚠️ **DISCUSSION NEEDED**" in results_content

            if has_discussion_issues:
                # Move to discussion phase instead of completing
                self.batch_service.start_discussion_phase(batch.id, batch.facilitator)

                # Update original message to show discussion phase
                self._update_batch_discussion_status(batch, vote_count, total_voters)

                # Post initial results with discussion items
                self._post_estimation_results(batch, votes, vote_count, total_voters)

                logger.info(
                    "Batch moved to discussion phase",
                    batch_id=batch.id,
                    vote_count=vote_count,
                    total_voters=total_voters,
                )
            else:
                consensus_estimates = self._extract_consensus_estimates(batch, votes)

                for issue_number, points in consensus_estimates.items():
                    self.batch_service.database.store_final_estimate(
                        batch.id, issue_number, points, "Consensus reached during initial voting"
                    )

                self.batch_service.complete_batch(batch.id, batch.facilitator)

                self._update_batch_completion_status(
                    batch, vote_count, total_voters, auto_completed
                )

                final_estimates = {
                    issue_number: (points, "Consensus reached during initial voting")
                    for issue_number, points in consensus_estimates.items()
                }

                batch.status = "completed"
                self._post_finish_results(batch, final_estimates)

                logger.info(
                    "Batch auto-completed with full consensus",
                    batch_id=batch.id,
                    vote_count=vote_count,
                    total_voters=total_voters,
                    auto_completed=auto_completed,
                    consensus_issues=len(consensus_estimates),
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

    def _update_batch_discussion_status(
        self, batch: BatchData, vote_count: int, total_voters: int
    ) -> None:
        """Update the original batch message to show discussion phase status.

        Args:
            batch: The batch data
            vote_count: Number of voters who submitted votes
            total_voters: Total number of expected voters
        """
        if not batch.message_id:
            logger.warning("Cannot update discussion status: no message ID", batch_id=batch.id)
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

            discussion_content = f"""**📦 BATCH REFINEMENT - DISCUSSION PHASE** 🗣️
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

**Status**: 🗣️ Discussion phase - some issues need clarification ({vote_count}/{total_voters} votes received)

*Initial results posted below - discussion needed for some items*"""

            edit_response = self.zulip_client.update_message(
                {
                    "message_id": batch.message_id,
                    "content": discussion_content,
                }
            )

            if edit_response.get("result") == "success":
                logger.info(
                    "Updated batch message with discussion status",
                    batch_id=batch.id,
                    message_id=batch.message_id,
                )
            else:
                logger.error(
                    "Failed to update batch discussion status",
                    batch_id=batch.id,
                    response=edit_response,
                )

        except Exception as e:
            logger.error("Error updating batch discussion status", batch_id=batch.id, error=str(e))

    def _post_finish_results(
        self, batch: BatchData, final_estimates_input: dict[str, tuple[int, str]]
    ) -> None:
        """Post final results after discussion is complete.

        Args:
            batch: Batch data
            final_estimates_input: Dict of issue_number -> (points, rationale)
        """
        try:
            if not batch.id:
                logger.error("Cannot post discussion results: batch ID is None")
                return

            # Get consensus estimates from original voting
            votes = self.voting_service.get_batch_votes(batch.id)

            # Analyze original votes to get consensus items
            consensus_estimates = self._extract_consensus_estimates(batch, votes)

            # Convert final estimates input to FinalEstimate objects
            final_estimates = [
                FinalEstimate(issue_number=issue_num, final_points=points, rationale=rationale)
                for issue_num, (points, rationale) in final_estimates_input.items()
            ]

            # Generate final results content
            results_content = self.results_service.generate_finish_results(
                batch, consensus_estimates, final_estimates
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
                    "Posted discussion complete results",
                    batch_id=batch.id,
                    topic=topic_name,
                )
            else:
                logger.error(
                    "Failed to post discussion complete results",
                    batch_id=batch.id,
                    response=response,
                )

        except Exception as e:
            logger.error(
                "Error posting discussion complete results", batch_id=batch.id, error=str(e)
            )

    def _extract_consensus_estimates(self, batch: BatchData, votes: list) -> dict[str, int]:
        """Extract consensus estimates from original votes.

        Args:
            batch: Batch data
            votes: All votes for the batch

        Returns:
            Dict of issue_number -> consensus_points for issues that had consensus
        """
        from collections import Counter

        # Group votes by issue
        votes_by_issue: dict[str, list] = {}
        for vote in votes:
            if vote.issue_number not in votes_by_issue:
                votes_by_issue[vote.issue_number] = []
            votes_by_issue[vote.issue_number].append(vote)

        consensus_estimates = {}

        # Process each issue to find consensus
        for issue in batch.issues:
            issue_votes = votes_by_issue.get(issue.issue_number, [])
            if not issue_votes:
                continue

            estimates = [vote.points for vote in issue_votes]
            estimates.sort()

            # Analyze consensus
            estimate_counts = Counter(estimates)
            most_common = estimate_counts.most_common()

            # Determine if there was consensus
            if len(most_common) == 1:
                # Perfect consensus
                consensus_estimates[issue.issue_number] = most_common[0][0]
            elif len(estimates) >= 3:
                # Check for clustering
                clusters = self.results_service._find_clusters(sorted(estimates))

                if len(clusters) == 1 and len(clusters[0]) >= len(estimates) * 0.6:
                    # Strong cluster consensus
                    cluster = clusters[0]
                    consensus_estimates[issue.issue_number] = max(
                        cluster
                    )  # Take highest in cluster for safety

        return consensus_estimates

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
            batch_voters = (
                self.batch_service.database.get_batch_voters(batch.id) if batch.id else []
            )
            results_content = self.results_service.generate_results_content(
                batch, votes, vote_count, total_voters, batch_voters
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
