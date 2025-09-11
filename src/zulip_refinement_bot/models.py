"""Data models for the Zulip Refinement Bot."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class IssueData(BaseModel):
    """Represents a GitHub issue."""

    issue_number: str = Field(..., description="GitHub issue number")
    url: str = Field(..., description="GitHub issue URL")


class BatchData(BaseModel):
    """Represents a refinement batch."""

    id: int | None = Field(None, description="Database ID")
    date: str = Field(..., description="Batch date (YYYY-MM-DD)")
    deadline: str = Field(..., description="Deadline in ISO format")
    facilitator: str = Field(..., description="Batch facilitator name")
    status: str = Field(default="active", description="Batch status")
    message_id: int | None = Field(
        None, description="Zulip message ID of the batch refinement message"
    )
    results_message_id: int | None = Field(
        None, description="Zulip message ID of the estimation results message"
    )
    created_at: datetime | None = Field(None, description="Creation timestamp")
    issues: list[IssueData] = Field(default_factory=list, description="Issues in batch")


class MessageData(BaseModel):
    """Represents a Zulip message."""

    type: str = Field(..., description="Message type (private/stream)")
    content: str = Field(..., description="Message content")
    sender_email: str = Field(..., description="Sender email")
    sender_full_name: str = Field(..., description="Sender full name")
    sender_id: int = Field(..., description="Sender ID")


class ParseResult(BaseModel):
    """Result of parsing batch input."""

    success: bool = Field(..., description="Whether parsing was successful")
    issues: list[IssueData] = Field(default_factory=list, description="Parsed issues")
    error: str = Field(default="", description="Error message if parsing failed")


class EstimationVote(BaseModel):
    """Represents a story point estimation vote."""

    voter: str = Field(..., description="Voter name")
    issue_number: str = Field(..., description="Issue number")
    points: int = Field(..., description="Story points estimate")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Vote timestamp"
    )


class Abstention(BaseModel):
    """Represents an abstention from voting on an issue."""

    voter: str = Field(..., description="Voter name")
    issue_number: str = Field(..., description="Issue number")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Abstention timestamp"
    )


class FinalEstimate(BaseModel):
    """Represents a final estimate for an issue after discussion."""

    issue_number: str = Field(..., description="Issue number")
    final_points: int = Field(..., description="Final agreed story points")
    rationale: str = Field(default="", description="Brief rationale for the estimate")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When estimate was finalized"
    )


class BatchResults(BaseModel):
    """Results of a completed batch."""

    batch_id: int = Field(..., description="Batch ID")
    votes: list[EstimationVote] = Field(..., description="All votes")
    consensus: dict[str, int] = Field(..., description="Consensus estimates per issue")
    final_estimates: dict[str, int] = Field(
        default_factory=dict, description="Final estimates after discussion"
    )
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Completion timestamp"
    )
