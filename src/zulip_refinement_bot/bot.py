"""Refactored main bot implementation for the Zulip Refinement Bot."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from .config import Config
from .container import Container
from .exceptions import RefinementBotError
from .models import MessageData

logger = structlog.get_logger(__name__)


class RefinementBot:
    """Main bot handler for the refinement bot with improved architecture."""

    def __init__(self, config: Config) -> None:
        """Initialize the refinement bot.

        Args:
            config: Bot configuration
        """
        self.config = config
        self.container = Container(config)

        # Get dependencies from container
        self.zulip_client = self.container.get_zulip_client()
        self.message_handler = self.container.get_message_handler()
        self.batch_service = self.container.get_batch_service()

        # Start deadline checker thread
        self._deadline_checker_running = True
        self._deadline_checker_thread = threading.Thread(
            target=self._deadline_checker_loop, daemon=True
        )
        self._deadline_checker_thread.start()

        logger.info("Refinement bot initialized", config=config.dict(exclude={"zulip_api_key"}))

    def usage(self) -> str:
        """Return usage instructions for the bot."""
        return f"""**Zulip Story Point Estimation Bot**

**Commands (DM only):**
• `start batch` - Create new estimation batch
• `status` - Show active batch info
• `cancel` - Cancel active batch (facilitator only)
• `complete` - Complete active batch and show results (facilitator only)
• `list voters` - Show voters for active batch
• `add voter Name` - Add voter to active batch (supports @**username** format)
• `remove voter Name` - Remove voter from active batch (supports @**username** format)

**Batch format (GitHub URLs only):**
Send `start batch` followed by GitHub issue URLs, one per line:
```
start batch
https://github.com/conda/conda/issues/15169
https://github.com/conda/conda/issues/15168
https://github.com/conda/conda/issues/15167
```

**Voting format:**
Submit estimates for all issues in the format:
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
• Batch completes automatically when all voters submit or when deadline expires"""

    def handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming messages.

        Args:
            message: Zulip message data
        """
        try:
            msg_data = MessageData(**message)

            # Skip messages from the bot itself
            if msg_data.sender_email == self.config.zulip_email:
                return

            # Only handle private messages
            if msg_data.type != "private":
                return

            content = msg_data.content.strip()

            # Handle help/usage requests
            if not content or content.lower() in ["help", "usage"]:
                self._send_reply(message, self.usage())
                return

            # Route to appropriate handler
            self._route_message(message, content)

        except Exception as e:
            logger.error("Error handling message", error=str(e), message=message)
            self._send_reply(
                message, "❌ An error occurred processing your message. Please try again."
            )

    def _route_message(self, message: dict[str, Any], content: str) -> None:
        """Route message to appropriate handler.

        Args:
            message: Zulip message data
            content: Message content
        """
        try:
            if content.lower().startswith("start batch"):
                self.message_handler.handle_start_batch(message, content)
            elif content.lower() == "status":
                self.message_handler.handle_status(message)
            elif content.lower() == "cancel":
                self.message_handler.handle_cancel(message)
            elif content.lower() == "complete":
                self.message_handler.handle_complete(message)
            elif content.lower() == "list voters":
                self.message_handler.handle_list_voters(message)
            elif content.lower().startswith("add voter"):
                self.message_handler.handle_add_voter(message, content)
            elif content.lower().startswith("remove voter"):
                self.message_handler.handle_remove_voter(message, content)
            elif content.lower().startswith("discussion complete"):
                self.message_handler.handle_discussion_complete(message, content)
            else:
                # Check if it's a vote format
                if self.message_handler.is_vote_format(content):
                    self.message_handler.handle_vote_submission(message, content)
                else:
                    self._send_reply(
                        message, "❌ Unknown command. Send 'help' for usage instructions."
                    )

        except RefinementBotError as e:
            # These are expected business logic errors
            self._send_reply(message, f"❌ {e.message}")
        except Exception as e:
            # Unexpected errors
            logger.error("Unexpected error in message routing", error=str(e))
            self._send_reply(message, "❌ An unexpected error occurred. Please try again.")

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
        active_batch = self.batch_service.get_active_batch()
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
            # Complete the batch automatically
            try:
                self.batch_service.complete_batch(active_batch.id, active_batch.facilitator)
                # The message handler will process the completion and post results
                self.message_handler._process_batch_completion(active_batch, auto_completed=False)
            except Exception as e:
                logger.error(
                    "Error processing expired batch", batch_id=active_batch.id, error=str(e)
                )

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
