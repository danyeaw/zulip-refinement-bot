"""Flask application for receiving Zulip outgoing webhooks."""

from __future__ import annotations

from typing import Any, cast

import structlog
from flask import Flask, request
from werkzeug.exceptions import BadRequest

from .bot import RefinementBot
from .config import Config

logger = structlog.get_logger(__name__)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["bot_instance"] = None
    app.config["config"] = None

    logger.info("Flask app initializing")
    app.config["config"] = Config()
    app.config["bot_instance"] = RefinementBot(app.config["config"])
    logger.info("Bot instance created for Flask")

    @app.teardown_appcontext  # type: ignore[misc]
    def cleanup(error: Exception | None = None) -> None:
        if error:
            logger.error("App context teardown with error", error=str(error))

    @app.route("/")  # type: ignore[misc]
    def root() -> dict[str, str]:
        return {"message": "Zulip Refinement Bot is running", "status": "healthy"}

    @app.route("/health")  # type: ignore[misc]
    def health_check() -> dict[str, str]:
        return {"status": "healthy", "service": "zulip-refinement-bot"}

    @app.route("/webhook", methods=["POST"])  # type: ignore[misc]
    def zulip_webhook() -> tuple[dict[str, str], int]:
        """Handle incoming Zulip outgoing webhooks."""
        try:
            payload = request.get_json()
            if payload is None:
                logger.warning("No JSON payload received")
                return {"error": "Invalid JSON payload"}, 400

            logger.debug("Received webhook payload", payload=payload)

            bot = get_bot_instance()
            config = cast(Config, app.config["config"])

            if not _verify_webhook_token(payload, config):
                logger.warning("Invalid webhook token", payload=payload)
                return {"error": "Invalid webhook token"}, 401

            message_data = _convert_webhook_to_message(payload)
            if not message_data:
                logger.warning("Invalid webhook payload", payload=payload)
                return {"error": "Invalid webhook payload"}, 400

            bot.handle_message(message_data)

            return {"status": "success"}, 200

        except BadRequest as e:
            logger.warning("Invalid JSON in webhook request", error=str(e))
            return {"error": "Invalid JSON payload"}, 400
        except Exception as e:
            logger.error("Error processing webhook", error=str(e), exc_info=True)
            return {"error": f"Error processing webhook: {str(e)}"}, 500

    return app


def get_bot_instance() -> RefinementBot:
    """Get or create the bot instance from app config."""
    app = cast(Flask, request.current_app)
    if app.config["bot_instance"] is None:
        app.config["config"] = Config()
        app.config["bot_instance"] = RefinementBot(app.config["config"])
        logger.info("Bot instance created for Flask")
    return cast(RefinementBot, app.config["bot_instance"])


def _verify_webhook_token(payload: dict[str, Any], config: Config) -> bool:
    """Verify the webhook token from Zulip."""
    try:
        expected_token = config.zulip_token

        received_token = payload.get("token")
        if not received_token:
            logger.warning("No token found in webhook payload")
            return False

        if received_token != expected_token:
            logger.warning("Token mismatch in webhook payload")
            return False

        return True
    except Exception as e:
        logger.error("Error verifying webhook token", error=str(e))
        return False


def _convert_webhook_to_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Convert Zulip webhook payload to MessageData format."""
    try:
        if "message" not in payload:
            logger.warning("No 'message' field in webhook payload")
            return None

        message = payload["message"]
        message_data = {
            "type": message.get("type", "private"),
            "content": message.get("content", ""),
            "sender_email": message.get("sender_email", ""),
            "sender_full_name": message.get("sender_full_name", ""),
            "sender_id": message.get("sender_id", 0),
        }

        if not all(
            [
                message_data["sender_email"],
                message_data["sender_full_name"],
                message_data["sender_id"],
            ]
        ):
            logger.warning("Missing required fields in message", message_data=message_data)
            return None

        content = message_data["content"]
        if content.startswith("@**"):
            parts = content.split("**", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
                message_data["content"] = content

        logger.debug("Converted webhook to message", message_data=message_data)
        return message_data

    except Exception as e:
        logger.error("Error converting webhook payload", error=str(e), payload=payload)
        return None


app = create_app()


def main() -> None:
    """Main entry point for the Flask server."""
    import logging
    import sys

    logging.basicConfig(level=logging.INFO)

    host = "127.0.0.1"
    port = 8000
    debug = False

    if len(sys.argv) > 1:
        if "--debug" in sys.argv:
            debug = True
        for i, arg in enumerate(sys.argv):
            if arg == "--host" and i + 1 < len(sys.argv):
                host = sys.argv[i + 1]
            elif arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
