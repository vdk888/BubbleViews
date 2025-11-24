"""
Pydantic schemas for health check endpoints.

Defines request/response models for health, readiness, and agent status checks.
"""

from datetime import datetime
from typing import Dict, Optional, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Response model for basic health check.

    Attributes:
        status: Health status ("ok" if service is running)
        timestamp: Current UTC timestamp
    """
    status: Literal["ok"] = Field(
        description="Health status indicator"
    )
    timestamp: datetime = Field(
        description="Current UTC timestamp"
    )


class HealthCheckDetail(BaseModel):
    """
    Individual health check result.

    Attributes:
        healthy: Whether this specific check passed
        latency_ms: Time taken to perform the check (optional)
        error: Error message if check failed (optional)
    """
    healthy: bool = Field(
        description="Whether the check passed"
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Check execution time in milliseconds"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if check failed"
    )


class ReadinessResponse(BaseModel):
    """
    Response model for readiness probe.

    Includes detailed checks for all dependencies.

    Attributes:
        status: Overall readiness status ("ready" if all checks pass)
        checks: Dictionary of individual check results
        timestamp: Current UTC timestamp
    """
    status: Literal["ready", "not_ready"] = Field(
        description="Overall readiness status"
    )
    checks: Dict[str, HealthCheckDetail] = Field(
        description="Individual dependency checks (db, openrouter, etc.)"
    )
    timestamp: datetime = Field(
        description="Current UTC timestamp"
    )


class AgentStatusResponse(BaseModel):
    """
    Response model for agent status endpoint.

    This is a stub for Week 4 implementation.

    Attributes:
        status: Agent status ("not_started" until Week 4)
        last_activity: Timestamp of last agent activity (null for stub)
    """
    status: Literal["not_started", "running", "stopped", "error"] = Field(
        description="Agent loop status"
    )
    last_activity: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last agent activity"
    )
