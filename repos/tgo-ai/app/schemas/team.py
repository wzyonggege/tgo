"""Team-related Pydantic schemas."""

import uuid
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema, IDMixin, TimestampMixin


class TeamBase(BaseSchema):
    """Base team schema with common fields."""

    name: str = Field(
        max_length=255,
        description="Team name",
        examples=["Customer Support Team"],
    )
    model: Optional[str] = Field(
        default=None,
        max_length=150,
        description="LLM model",
        examples=["claude-3-sonnet-20240229"],
    )
    instruction: Optional[str] = Field(
        default=None,
        description="Team system prompt/instructions",
        examples=["You are a customer support team focused on resolving user issues efficiently..."],
    )
    expected_output: Optional[str] = Field(
        default=None,
        description="Expected output format description",
        examples=["Provide clear, actionable solutions with step-by-step instructions"],
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Team session identifier",
        examples=["cs-team-session-2024"],
    )
    is_default: bool = Field(
        default=False,
        description="Whether this should be the default team (only one per project)",
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Team configuration (respond_directly, markdown, history runs, etc.)",
        examples=[{"respond_directly": False, "markdown": True, "num_history_runs": 5}],
    )





class TeamCreate(TeamBase):
    """Schema for creating a new team."""

    llm_provider_id: Optional[uuid.UUID] = Field(
        default=None,
        description="LLM provider (credentials) ID to use for this team",
    )


class TeamUpdate(BaseSchema):
    """Schema for updating an existing team."""

    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Updated team name",
    )
    model: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Updated LLM model",
    )
    instruction: Optional[str] = Field(
        default=None,
        description="Updated team instructions",
    )
    expected_output: Optional[str] = Field(
        default=None,
        description="Updated expected output format",
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Updated session identifier",
    )
    is_default: Optional[bool] = Field(
        default=None,
        description="Updated default status",
    )
    llm_provider_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Updated LLM provider (credentials) ID",
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated team configuration (respond_directly, markdown, etc.)",
    )





class TeamResponse(TeamBase, IDMixin, TimestampMixin):
    """Schema for team API responses."""

    llm_provider_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Associated LLM provider (credentials) ID",
    )


class TeamWithDetails(TeamResponse):
    """Schema for team response with additional details."""

    agents: List["AgentWithDetails"] = Field(
        default_factory=list,
        description="Agents belonging to this team with their tools and collections",
    )


# Forward reference resolution
from app.schemas.agent import AgentWithDetails  # noqa: E402

TeamWithDetails.model_rebuild()
