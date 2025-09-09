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
        return f"""Hi, I'm a friendly bot that helps with batch story point estimation.

**Commands (DM only):**
• `start` - Create new estimation batch
• `status` - Show active batch info
• `cancel` - Cancel active batch (facilitator only)
• `complete` - Complete active batch and show results (facilitator only)
• `list` - Show voters for active batch
• `add Name` - Add voter(s) to active batch (supports multiple formats)
• `remove Name` - Remove voter(s) from active batch (supports multiple formats)
• `finish #issue: points rationale` - Complete discussion phase (facilitator only)

**Batch format (GitHub URLs only):**
Send `start` followed by GitHub issue URLs, one per line:
```
start
https://github.com/conda/conda/issues/15169
https://github.com/conda/conda/issues/15168
https://github.com/conda/conda/issues/15167
```

**Voting format:**
Submit estimates for all issues in the format:
```
#15169: 5, #15168: 8, #15167: 3
```

**Multi-voter management:**
Add or remove multiple voters using various formats:
```
add John Doe
add Alice, Bob, @**charlie**
add Jane and Mike
remove John Smith
remove Alice and Bob
```

**Discussion phase:**
When consensus isn't reached, complete discussion with:
```
finish #15169: 5 After discussion we agreed it's medium complexity, #15168: 3 Simple fix
```

**Rules:**
• Maximum {self.config.max_issues_per_batch} issues per batch
• Only one active batch at a time
• {self.config.default_deadline_hours}-hour default deadline
• Valid story points: 1, 2, 3, 5, 8, 13, 21
• Must vote for all issues in the batch
• Can update votes by submitting new estimates (replaces previous votes)
• New voters automatically added when they submit votes
• Batch completes automatically when all voters submit or when deadline expires"""

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle incoming messages from webhook."""
        try:
            msg_data = MessageData(**message)

            if msg_data.sender_email == self.config.zulip_email:
                return {"status": "ignored", "reason": "self_message"}

            if msg_data.type != "private":
                return {"status": "ignored", "reason": "not_private"}

            content = msg_data.content.strip()

            if not content or content.lower() in ["help", "usage"]:
                self._send_reply(message, self.usage())
                return {"status": "success", "action": "help"}

            action = self._route_message(message, content)
            return {"status": "success", "action": action}

        except Exception as e:
            logger.error("Error handling message", error=str(e), message=message)
            self._send_reply(
                message, "❌ An error occurred processing your message. Please try again."
            )
            return {"status": "error", "error": str(e)}

    def _route_message(self, message: dict[str, Any], content: str) -> str:
        """Route message to appropriate handler."""
        try:
            if content.lower().startswith("start"):
                self.message_handler.handle_start_batch(message, content)
                return "start_batch"
            elif content.lower() == "status":
                self.message_handler.handle_status(message)
                return "status"
            elif content.lower() == "cancel":
                self.message_handler.handle_cancel(message)
                return "cancel"
            elif content.lower() == "complete":
                self.message_handler.handle_complete(message)
                return "complete"
            elif content.lower() == "list":
                self.message_handler.handle_list_voters(message)
                return "list_voters"
            elif content.lower().startswith("add "):
                self.message_handler.handle_add_voter(message, content)
                return "add_voter"
            elif content.lower().startswith("remove "):
                self.message_handler.handle_remove_voter(message, content)
                return "remove_voter"
            elif content.lower().startswith("finish"):
                self.message_handler.handle_finish(message, content)
                return "finish"
            else:
                if self.message_handler.is_vote_format(content):
                    self.message_handler.handle_vote_submission(message, content)
                    return "vote_submission"
                else:
                    self._send_reply(
                        message, "❌ Unknown command. Send 'help' for usage instructions."
                    )
                    return "unknown_command"

        except RefinementBotError as e:
            self._send_reply(message, f"❌ {e.message}")
            return f"error_{type(e).__name__}"
        except Exception as e:
            logger.error("Unexpected error in message routing", error=str(e))
            self._send_reply(message, "❌ An unexpected error occurred. Please try again.")
            return "unexpected_error"

    def _send_reply(self, message: dict[str, Any], content: str) -> None:
        """Send a reply to a message."""
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
            try:
                self.batch_service.complete_batch(active_batch.id, active_batch.facilitator)
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

        # Clean up container resources
        if hasattr(self, "container"):
            self.container.cleanup()
