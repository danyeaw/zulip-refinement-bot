"""Tests for proxy voting functionality."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from zulip_refinement_bot.exceptions import ValidationError
from zulip_refinement_bot.handlers import MessageHandler
from zulip_refinement_bot.models import BatchData, IssueData


@pytest.fixture
def mock_handler() -> MessageHandler:
    """Create a message handler with all dependencies mocked."""
    config = MagicMock()
    zulip_client = MagicMock()
    batch_service = MagicMock()
    voting_service = MagicMock()
    results_service = MagicMock()
    github_api = MagicMock()

    return MessageHandler(
        config,
        zulip_client,
        batch_service,
        voting_service,
        results_service,
        github_api,
    )


@pytest.fixture
def active_batch() -> BatchData:
    """Active batch with a specific facilitator."""
    return BatchData(
        id=1,
        date="2024-01-15",
        deadline=(datetime.now(UTC) + timedelta(hours=48)).isoformat(),
        facilitator="Alice Smith",
        status="active",
        message_id=12345,
        issues=[
            IssueData(issue_number="123", url="https://github.com/test/repo/issues/123"),
            IssueData(issue_number="124", url="https://github.com/test/repo/issues/124"),
        ],
    )


def test_is_proxy_vote_format_valid_cases(mock_handler: MessageHandler) -> None:
    """Test detection of valid proxy vote formats."""
    valid_cases = [
        "vote for @**john** #123: 5",
        "VOTE FOR Alice #123: 8",
        "Vote for Bob Smith #123: 3, #124: 5",
        "vote for @**jane.doe** #123: 13",
        "  vote for   user   #123: 2  ",
    ]

    for case in valid_cases:
        assert mock_handler.is_proxy_vote_format(case), f"Should detect: {case}"


def test_is_proxy_vote_format_invalid_cases(mock_handler: MessageHandler) -> None:
    """Test rejection of invalid proxy vote formats."""
    invalid_cases = [
        "#123: 5",  # Regular vote
        "add Alice",  # Different command
        "vote #123: 5",  # Missing 'for'
        "for user #123: 5",  # Missing 'vote'
        "vote for",  # Incomplete
        "start batch",  # Unrelated command
    ]

    for case in invalid_cases:
        assert not mock_handler.is_proxy_vote_format(case), f"Should reject: {case}"


def test_parse_proxy_vote_content_success_cases(mock_handler: MessageHandler) -> None:
    """Test successful parsing of proxy vote content."""
    test_cases = [
        (
            "vote for @**john** #123: 5, #124: 8",
            ("john", "#123: 5, #124: 8"),
        ),
        (
            "vote for Alice Smith #123: 3",
            ("Alice Smith", "#123: 3"),
        ),
        (
            "VOTE FOR Bob #123: 13, #124: 2, #125: 5",
            ("Bob", "#123: 13, #124: 2, #125: 5"),
        ),
        (
            "vote for @**jane.doe** #123: 21",
            ("jane.doe", "#123: 21"),
        ),
        # Backtick cases
        (
            "vote for @**john** `#123: 5, #124: 8`",
            ("john", "#123: 5, #124: 8"),
        ),
        (
            "vote for Alice Smith `#123: 3`",
            ("Alice Smith", "#123: 3"),
        ),
        (
            "VOTE FOR Bob `#123: 13, #124: 2, #125: 5`",
            ("Bob", "#123: 13, #124: 2, #125: 5"),
        ),
    ]

    for input_text, expected in test_cases:
        result = mock_handler._parse_proxy_vote_content(input_text)
        assert result == expected, f"Failed for: {input_text}"


def test_parse_proxy_vote_content_failure_cases(mock_handler: MessageHandler) -> None:
    """Test parsing failures for invalid proxy vote content."""
    invalid_cases = [
        "vote for",  # Missing everything
        "vote for Alice",  # Missing vote content
        "Alice #123: 5",  # Missing 'vote for'
        "vote #123: 5",  # Missing 'for' and user
        "",  # Empty string
    ]

    for case in invalid_cases:
        result = mock_handler._parse_proxy_vote_content(case)
        assert result == (None, None), f"Should fail for: {case}"


def test_handle_proxy_vote_success(mock_handler: MessageHandler, active_batch: BatchData) -> None:
    """Test successful proxy vote submission."""
    # Setup
    message = {
        "sender_full_name": "Alice Smith",  # Same as batch facilitator
        "sender_email": "alice@example.com",
    }
    content = "vote for @**bob** #123: 5, #124: 8"

    # Mock dependencies
    mock_handler.batch_service.get_active_batch.return_value = active_batch
    mock_handler.voting_service.submit_votes.return_value = (
        {"123": 5, "124": 8},  # estimates
        False,  # has_updates
        False,  # all_voters_complete
    )
    mock_handler.zulip_client.send_message.return_value = {"result": "success"}

    # Execute
    mock_handler.handle_proxy_vote(message, content)

    # Verify
    mock_handler.voting_service.submit_votes.assert_called_once_with(
        "#123: 5, #124: 8", "bob", active_batch
    )

    # Check the reply message
    call_args = mock_handler.zulip_client.send_message.call_args[0][0]
    assert "Proxy votes recorded successfully for bob" in call_args["content"]


def test_handle_proxy_vote_no_active_batch(mock_handler: MessageHandler) -> None:
    """Test proxy vote when no active batch exists."""
    # Setup
    message = {
        "sender_full_name": "Alice Smith",
        "sender_email": "alice@example.com",
    }
    content = "vote for @**bob** #123: 5"

    mock_handler.batch_service.get_active_batch.return_value = None
    mock_handler.zulip_client.send_message.return_value = {"result": "success"}

    # Execute
    mock_handler.handle_proxy_vote(message, content)

    # Verify
    call_args = mock_handler.zulip_client.send_message.call_args[0][0]
    assert "No active batch found" in call_args["content"]


def test_handle_proxy_vote_unauthorized_user(
    mock_handler: MessageHandler, active_batch: BatchData
) -> None:
    """Test proxy vote from non-facilitator user."""
    # Setup
    message = {
        "sender_full_name": "Bob Wilson",  # Different from batch facilitator
        "sender_email": "bob@example.com",
    }
    content = "vote for @**charlie** #123: 5"

    mock_handler.batch_service.get_active_batch.return_value = active_batch
    mock_handler.zulip_client.send_message.return_value = {"result": "success"}

    # Execute
    mock_handler.handle_proxy_vote(message, content)

    # Verify
    call_args = mock_handler.zulip_client.send_message.call_args[0][0]
    assert "Only the facilitator (Alice Smith) can submit votes" in call_args["content"]


def test_handle_proxy_vote_invalid_format(
    mock_handler: MessageHandler, active_batch: BatchData
) -> None:
    """Test proxy vote with invalid format."""
    # Setup
    message = {
        "sender_full_name": "Alice Smith",
        "sender_email": "alice@example.com",
    }
    content = "vote for"  # Invalid format

    mock_handler.batch_service.get_active_batch.return_value = active_batch
    mock_handler.zulip_client.send_message.return_value = {"result": "success"}

    # Execute
    mock_handler.handle_proxy_vote(message, content)

    # Verify
    call_args = mock_handler.zulip_client.send_message.call_args[0][0]
    assert "Invalid proxy vote format" in call_args["content"]


def test_handle_proxy_vote_validation_error(
    mock_handler: MessageHandler, active_batch: BatchData
) -> None:
    """Test proxy vote with validation error from voting service."""
    # Setup
    message = {
        "sender_full_name": "Alice Smith",
        "sender_email": "alice@example.com",
    }
    content = "vote for @**bob** #123: 4"  # Invalid story point

    mock_handler.batch_service.get_active_batch.return_value = active_batch
    mock_handler.voting_service.submit_votes.side_effect = ValidationError(
        "Invalid story point value"
    )
    mock_handler.zulip_client.send_message.return_value = {"result": "success"}

    # Execute
    mock_handler.handle_proxy_vote(message, content)

    # Verify
    call_args = mock_handler.zulip_client.send_message.call_args[0][0]
    assert "Invalid story point value" in call_args["content"]


def test_is_vote_format_valid_cases(mock_handler: MessageHandler) -> None:
    """Test that is_vote_format correctly identifies valid vote formats."""
    valid_cases = [
        "#123: 5",
        "#123: 5, #124: 8",
        "#123: 5, #124: 8, #125: 3",
        "  #123: 5  ",  # With spaces
        "#123:5",  # No space after colon
        "`#123: 5`",  # With backticks
        "`#123: 5, #124: 8`",  # Multiple votes with backticks
        "  `  #123: 5  `  ",  # Backticks with extra spaces
    ]

    for case in valid_cases:
        assert mock_handler.is_vote_format(case), f"Should accept: {case}"


def test_is_vote_format_invalid_cases(mock_handler: MessageHandler) -> None:
    """Test that is_vote_format correctly rejects invalid vote formats."""
    invalid_cases = [
        "",
        "start batch",
        "status",
        "cancel",
        "vote for alice #123: 5",  # proxy vote format
        "#123",  # Missing points
        "123: 5",  # Missing hash
        "#abc: 5",  # Non-numeric issue number
        "#123: abc",  # Non-numeric points
        "random text",
        "`",  # Just a backtick
        "`#123: 5",  # Unclosed backtick
        "#123: 5`",  # Only closing backtick
    ]

    for case in invalid_cases:
        assert not mock_handler.is_vote_format(case), f"Should reject: {case}"
