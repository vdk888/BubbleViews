"""
Health check endpoints for monitoring and readiness probes.

This module provides endpoints for:
- Liveness probe: /health (basic "is the server running" check)
- Readiness probe: /health/ready (checks dependencies like DB, OpenRouter)
- Agent status: /health/agent (agent loop status - stub for Week 4)
"""

from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, status, Depends

from app.schemas.health import HealthResponse, ReadinessResponse, AgentStatusResponse


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Basic health check to verify the service is running",
)
async def health_check() -> HealthResponse:
    """
    Basic liveness probe.

    Returns a simple "ok" status with timestamp.
    This endpoint should always return 200 if the application is running.

    Returns:
        HealthResponse with status and timestamp

    Example response:
        {
            "status": "ok",
            "timestamp": "2025-11-24T10:30:00.123456"
        }
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow()
    )
