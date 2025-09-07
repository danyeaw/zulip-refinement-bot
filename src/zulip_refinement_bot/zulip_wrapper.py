"""Zulip client wrapper implementing the ZulipClientInterface."""

from __future__ import annotations

import time
from typing import Any, TypedDict, cast

import structlog
import zulip

from .interfaces import ZulipClientInterface

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


class ZulipClientWrapper(ZulipClientInterface):
    """Wrapper for Zulip client that implements retry logic and error handling."""

    def __init__(self, email: str, api_key: str, site: str) -> None:
        """Initialize Zulip client wrapper.

        Args:
            email: Zulip bot email
            api_key: Zulip API key
            site: Zulip site URL
        """
        self.client = zulip.Client(
            email=email,
            api_key=api_key,
            site=site,
        )

    def send_message(self, message_data: dict[str, Any]) -> dict[str, Any]:
        """Send a message via Zulip API with retry logic.

        Args:
            message_data: The message data to send

        Returns:
            The API response
        """
        response = self._send_message_with_retry(message_data)
        return dict(response)

    def update_message(self, message_data: dict[str, Any]) -> dict[str, Any]:
        """Update a message via Zulip API.

        Args:
            message_data: The message data to update

        Returns:
            The API response
        """
        response = self.client.update_message(message_data)
        return dict(response) if response else {}

    def call_on_each_message(self, handler: Any) -> None:
        """Register message handler and start listening.

        Args:
            handler: Message handler function
        """
        self.client.call_on_each_message(handler)

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
                response = self.client.send_message(message_data)

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

        raise Exception("Unexpected error in retry logic")
