"""FastAPI application for receiving Zulip outgoing webhooks."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .bot import RefinementBot
from .config import Config

logger = structlog.get_logger(__name__)

# Global bot instance
_bot_instance: RefinementBot | None = None


def get_bot_instance() -> RefinementBot:
    """Get or create the bot instance."""
    global _bot_instance
    if _bot_instance is None:
        config = Config()
        _bot_instance = RefinementBot(config)
        logger.info("Bot instance created for FastAPI")
    return _bot_instance


# Create FastAPI app
app = FastAPI(
    title="Zulip Refinement Bot",
    description="FastAPI webhook handler for Zulip Refinement Bot",
    version="1.0.0",
)


@app.on_event("shutdown")  # type: ignore[misc]
async def shutdown_event() -> None:
    """Clean up on shutdown."""
    global _bot_instance
    if _bot_instance:
        _bot_instance.stop()
        _bot_instance = None
    logger.info("FastAPI app shut down")


@app.get("/")  # type: ignore[misc]
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {"message": "Zulip Refinement Bot is running", "status": "healthy"}


@app.get("/health")  # type: ignore[misc]
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "zulip-refinement-bot"}


@app.post("/webhook")  # type: ignore[misc]
async def zulip_webhook(request: Request) -> JSONResponse:
    """Handle incoming Zulip outgoing webhooks."""
    try:
        payload = await request.json()
        logger.debug("Received webhook payload", payload=payload)

        # Verify webhook token FIRST before any other processing
        if not _verify_webhook_token(payload):
            logger.warning("Invalid webhook token", payload=payload)
            raise HTTPException(status_code=401, detail="Invalid webhook token")

        message_data = _convert_webhook_to_message(payload)
        if not message_data:
            logger.warning("Invalid webhook payload", payload=payload)
            raise HTTPException(status_code=400, detail="Invalid webhook payload")

        bot = get_bot_instance()
        bot.handle_message(message_data)

        return JSONResponse(content={"status": "success"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing webhook", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing webhook: {str(e)}") from e


def _verify_webhook_token(payload: dict[str, Any]) -> bool:
    """Verify the webhook token from Zulip."""
    try:
        config = Config()
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

        # Remove bot mention from content
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


def main() -> None:
    """Main entry point for the FastAPI server."""
    import logging
    import sys

    import uvicorn

    logging.basicConfig(level=logging.INFO)

    host = "127.0.0.1"
    port = 8000
    reload = False

    if len(sys.argv) > 1:
        if "--reload" in sys.argv:
            reload = True
        for i, arg in enumerate(sys.argv):
            if arg == "--host" and i + 1 < len(sys.argv):
                host = sys.argv[i + 1]
            elif arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])

    uvicorn.run(
        "zulip_refinement_bot.fastapi_app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
