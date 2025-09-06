"""Data models for the Zulip Refinement Bot."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class IssueData(BaseModel):
    """Represents a GitHub issue."""

    issue_number: str = Field(..., description="GitHub issue number")
    title: str = Field(..., description="Issue title")
    url: str = Field(default="", description="GitHub issue URL")


class BatchData(BaseModel):
    """Represents a refinement batch."""

    id: Optional[int] = Field(None, description="Database ID")
    date: str = Field(..., description="Batch date (YYYY-MM-DD)")
    deadline: str = Field(..., description="Deadline in ISO format")
    facilitator: str = Field(..., description="Batch facilitator name")
    status: str = Field(default="active", description="Batch status")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    issues: List[IssueData] = Field(default_factory=list, description="Issues in batch")


class MessageData(BaseModel):
    """Represents a Zulip message."""

    type: str = Field(..., description="Message type (private/stream)")
    content: str = Field(..., description="Message content")
    sender_email: str = Field(..., description="Sender email")
    sender_full_name: str = Field(..., description="Sender full name")
    sender_id: str = Field(..., description="Sender ID")


class ParseResult(BaseModel):
    """Result of parsing batch input."""

    success: bool = Field(..., description="Whether parsing was successful")
    issues: List[IssueData] = Field(default_factory=list, description="Parsed issues")
    error: str = Field(default="", description="Error message if parsing failed")


class EstimationVote(BaseModel):
    """Represents a story point estimation vote."""

    voter: str = Field(..., description="Voter name")
    issue_number: str = Field(..., description="Issue number")
    points: int = Field(..., description="Story points estimate")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Vote timestamp")


class BatchResults(BaseModel):
    """Results of a completed batch."""

    batch_id: int = Field(..., description="Batch ID")
    votes: List[EstimationVote] = Field(..., description="All votes")
    consensus: Dict[str, int] = Field(..., description="Consensus estimates per issue")
    completed_at: datetime = Field(
        default_factory=datetime.utcnow, description="Completion timestamp"
    )
