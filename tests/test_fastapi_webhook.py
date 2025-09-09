"""Tests for FastAPI webhook functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi.testclient import TestClient

from zulip_refinement_bot.config import Config
from zulip_refinement_bot.fastapi_app import _convert_webhook_to_message, _verify_webhook_token, app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def valid_webhook_payload() -> dict[str, object]:
    """Create a valid webhook payload for testing."""
    return {
        "token": "test_webhook_token",
        "message": {
            "type": "private",
            "content": "help",
            "sender_email": "user@example.com",
            "sender_full_name": "Test User",
            "sender_id": 123,
        },
    }


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock config for testing."""
    config = MagicMock(spec=Config)
    config.zulip_token = "test_webhook_token"
    config.zulip_email = "bot@example.com"
    return config


class TestWebhookTokenVerification:
    """Test webhook token verification functionality."""

    def test_verify_webhook_token_valid(
        self, valid_webhook_payload: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test token verification with valid token."""
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        config = Config()
        result = _verify_webhook_token(valid_webhook_payload, config)
        assert result is True

    def test_verify_webhook_token_invalid(
        self, valid_webhook_payload: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test token verification with invalid token."""
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        payload = valid_webhook_payload.copy()
        payload["token"] = "wrong_token"

        config = Config()
        result = _verify_webhook_token(payload, config)
        assert result is False

    def test_verify_webhook_token_missing(
        self, valid_webhook_payload: dict[str, object], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test token verification with missing token."""
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        payload = valid_webhook_payload.copy()
        del payload["token"]

        config = Config()
        result = _verify_webhook_token(payload, config)
        assert result is False

    def test_verify_webhook_token_config_error(
        self, valid_webhook_payload: dict[str, object]
    ) -> None:
        """Test token verification when config loading fails."""
        mock_config = MagicMock()
        mock_config.zulip_token = PropertyMock(side_effect=Exception("Config error"))

        result = _verify_webhook_token(valid_webhook_payload, mock_config)
        assert result is False


class TestWebhookPayloadConversion:
    """Test webhook payload conversion functionality."""

    def test_convert_webhook_to_message_valid(
        self, valid_webhook_payload: dict[str, object]
    ) -> None:
        """Test converting valid webhook payload to message data."""
        result = _convert_webhook_to_message(valid_webhook_payload)

        assert result is not None
        assert result["type"] == "private"
        assert result["content"] == "help"
        assert result["sender_email"] == "user@example.com"
        assert result["sender_full_name"] == "Test User"
        assert result["sender_id"] == 123

    def test_convert_webhook_to_message_missing_message_field(
        self, valid_webhook_payload: dict[str, object]
    ) -> None:
        """Test conversion with missing message field."""
        payload = valid_webhook_payload.copy()
        del payload["message"]

        result = _convert_webhook_to_message(payload)
        assert result is None

    def test_convert_webhook_to_message_missing_required_fields(
        self, valid_webhook_payload: dict[str, object]
    ) -> None:
        """Test conversion with missing required fields."""
        payload = valid_webhook_payload.copy()
        message = payload["message"]
        assert isinstance(message, dict)
        del message["sender_email"]

        result = _convert_webhook_to_message(payload)
        assert result is None

    def test_convert_webhook_to_message_bot_mention_removal(
        self, valid_webhook_payload: dict[str, object]
    ) -> None:
        """Test bot mention removal from content."""
        payload = valid_webhook_payload.copy()
        message = payload["message"]
        assert isinstance(message, dict)
        message["content"] = "@**Bot Name** help"

        result = _convert_webhook_to_message(payload)

        assert result is not None
        assert result["content"] == "help"

    def test_convert_webhook_to_message_exception_handling(
        self, valid_webhook_payload: dict[str, object]
    ) -> None:
        """Test exception handling during conversion."""
        # Create invalid payload that will cause KeyError
        payload = {"invalid": "data"}

        result = _convert_webhook_to_message(payload)
        assert result is None


class TestWebhookEndpoint:
    """Test the main webhook endpoint."""

    @patch("zulip_refinement_bot.fastapi_app.get_bot_instance")
    def test_webhook_endpoint_success(
        self,
        mock_get_bot: MagicMock,
        client: TestClient,
        valid_webhook_payload: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test successful webhook processing."""
        # Set all required environment variables for Config
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        mock_bot = MagicMock()
        mock_get_bot.return_value = mock_bot

        response = client.post("/webhook", json=valid_webhook_payload)

        assert response.status_code == 200
        assert response.json() == {"status": "success"}
        mock_bot.handle_message.assert_called_once()

    def test_webhook_endpoint_invalid_token(
        self,
        client: TestClient,
        valid_webhook_payload: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test webhook with invalid token."""
        # Set all required environment variables for Config
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "correct_token")

        payload = valid_webhook_payload.copy()
        payload["token"] = "wrong_token"

        response = client.post("/webhook", json=payload)

        assert response.status_code == 401
        assert "Invalid webhook token" in response.json()["detail"]

    def test_webhook_endpoint_missing_token(
        self,
        client: TestClient,
        valid_webhook_payload: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test webhook with missing token."""
        # Set all required environment variables for Config
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        payload = valid_webhook_payload.copy()
        del payload["token"]

        response = client.post("/webhook", json=payload)

        assert response.status_code == 401
        assert "Invalid webhook token" in response.json()["detail"]

    @patch("zulip_refinement_bot.fastapi_app.get_bot_instance")
    def test_webhook_endpoint_invalid_payload(
        self,
        mock_get_bot: MagicMock,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test webhook with invalid payload."""
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        # Valid token but invalid message structure
        payload = {"token": "test_webhook_token", "invalid": "payload"}

        response = client.post("/webhook", json=payload)

        assert response.status_code == 400
        assert "Invalid webhook payload" in response.json()["detail"]

    @patch("zulip_refinement_bot.fastapi_app.get_bot_instance")
    def test_webhook_endpoint_bot_error(
        self,
        mock_get_bot: MagicMock,
        client: TestClient,
        valid_webhook_payload: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test webhook when bot processing raises an error."""
        # Set all required environment variables for Config
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        mock_bot = MagicMock()
        mock_bot.handle_message.side_effect = Exception("Bot processing error")
        mock_get_bot.return_value = mock_bot

        response = client.post("/webhook", json=valid_webhook_payload)

        assert response.status_code == 500
        assert "Error processing webhook" in response.json()["detail"]

    def test_webhook_endpoint_invalid_json(self, client: TestClient) -> None:
        """Test webhook with invalid JSON."""
        response = client.post(
            "/webhook", content="invalid json", headers={"content-type": "application/json"}
        )

        assert response.status_code == 500  # JSON parsing error in our handler


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_endpoint(self, client: TestClient) -> None:
        """Test root health check endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "Zulip Refinement Bot" in data["message"]

    def test_health_endpoint(self, client: TestClient) -> None:
        """Test dedicated health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "zulip-refinement-bot"


class TestBotIntegration:
    """Integration tests with the bot instance."""

    @patch("zulip_refinement_bot.fastapi_app.get_bot_instance")
    def test_webhook_bot_message_handling(
        self,
        mock_get_bot: MagicMock,
        client: TestClient,
        valid_webhook_payload: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that webhook correctly passes message data to bot."""
        # Set all required environment variables for Config
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        mock_bot = MagicMock()
        mock_get_bot.return_value = mock_bot

        response = client.post("/webhook", json=valid_webhook_payload)

        assert response.status_code == 200

        # Verify bot was called with correct message data
        mock_bot.handle_message.assert_called_once()
        call_args = mock_bot.handle_message.call_args[0][0]

        assert call_args["type"] == "private"
        assert call_args["content"] == "help"
        assert call_args["sender_email"] == "user@example.com"
        assert call_args["sender_full_name"] == "Test User"
        assert call_args["sender_id"] == 123

    @patch("zulip_refinement_bot.fastapi_app.get_bot_instance")
    def test_webhook_complex_message_content(
        self,
        mock_get_bot: MagicMock,
        client: TestClient,
        valid_webhook_payload: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test webhook with complex message content."""
        # Set all required environment variables for Config
        monkeypatch.setenv("ZULIP_EMAIL", "test@example.com")
        monkeypatch.setenv("ZULIP_API_KEY", "test_key")
        monkeypatch.setenv("ZULIP_SITE", "https://test.zulipchat.com")
        monkeypatch.setenv("ZULIP_TOKEN", "test_webhook_token")

        mock_bot = MagicMock()
        mock_get_bot.return_value = mock_bot

        # Test with voting content
        payload = valid_webhook_payload.copy()
        message = payload["message"]
        assert isinstance(message, dict)
        message["content"] = "#123: 5, #124: 8, #125: 3"

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200

        # Verify bot received the voting content
        call_args = mock_bot.handle_message.call_args[0][0]
        assert call_args["content"] == "#123: 5, #124: 8, #125: 3"


def test_webhook_proxy_vote_message(client: TestClient) -> None:
    """Test webhook handling of proxy vote message."""
    payload = {
        "type": "private",
        "sender_email": "facilitator@example.com",
        "sender_full_name": "Test Facilitator",
        "content": "vote for @**bob** #123: 5, #124: 8",
        "timestamp": 1642678800,
    }

    with patch("zulip_refinement_bot.fastapi_app.bot") as mock_bot:
        mock_bot.handle_message.return_value = {"status": "success", "action": "proxy_vote"}

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200

        # Verify bot received the proxy vote content
        call_args = mock_bot.handle_message.call_args[0][0]
        assert call_args["content"] == "vote for @**bob** #123: 5, #124: 8"
