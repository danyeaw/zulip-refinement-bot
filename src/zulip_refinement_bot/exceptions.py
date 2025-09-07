"""Custom exceptions for the Zulip Refinement Bot."""

from __future__ import annotations


class RefinementBotError(Exception):
    """Base exception for all refinement bot errors."""

    def __init__(self, message: str, details: dict[str, str] | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message
            details: Optional additional error details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(RefinementBotError):
    """Raised when there's a configuration issue."""


class ValidationError(RefinementBotError):
    """Raised when input validation fails."""


class BatchError(RefinementBotError):
    """Raised when batch operations fail."""


class VotingError(RefinementBotError):
    """Raised when voting operations fail."""


class GitHubAPIError(RefinementBotError):
    """Raised when GitHub API operations fail."""


class DatabaseError(RefinementBotError):
    """Raised when database operations fail."""


class ZulipAPIError(RefinementBotError):
    """Raised when Zulip API operations fail."""


class AuthorizationError(RefinementBotError):
    """Raised when user is not authorized for an operation."""
