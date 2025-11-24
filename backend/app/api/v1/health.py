"""
Health check endpoints for monitoring and readiness probes.

This module provides endpoints for:
- Liveness probe: /health (basic "is the server running" check)
- Readiness probe: /health/ready (checks dependencies like DB, OpenRouter)
- Agent status: /health/agent (agent loop status - stub for Week 4)
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, status, Response

from app.schemas.health import (
    HealthResponse,
    ReadinessResponse,
    AgentStatusResponse,
    HealthCheckDetail,
)
from app.core.probes import check_database, check_openrouter


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


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Comprehensive readiness check including all dependencies",
)
async def readiness_check(response: Response) -> ReadinessResponse:
    """
    Readiness probe with dependency checks.

    Checks all critical dependencies in parallel:
    - Database connectivity (SQLite/PostgreSQL)
    - OpenRouter API availability

    Returns 200 if all checks pass, 503 if any check fails.
    Individual check results are included in the response.

    Args:
        response: FastAPI response object (for status code manipulation)

    Returns:
        ReadinessResponse with overall status and individual check details

    Example response (healthy):
        {
            "status": "ready",
            "checks": {
                "db": {"healthy": true, "latency_ms": 12.5},
                "openrouter": {"healthy": true, "latency_ms": 145.3}
            },
            "timestamp": "2025-11-24T10:30:00.123456"
        }

    Example response (unhealthy):
        {
            "status": "not_ready",
            "checks": {
                "db": {"healthy": true, "latency_ms": 10.2},
                "openrouter": {"healthy": false, "latency_ms": 3000.0, "error": "Timeout"}
            },
            "timestamp": "2025-11-24T10:30:00.123456"
        }
    """
    # Execute all probes in parallel using asyncio.gather()
    # This is more efficient than running them sequentially
    start_time = time.time()

    # Create tasks for parallel execution
    db_task = asyncio.create_task(check_database())
    openrouter_task = asyncio.create_task(check_openrouter())

    # Track individual probe timings
    db_start = time.time()
    db_healthy = await db_task
    db_latency = (time.time() - db_start) * 1000  # Convert to ms

    openrouter_start = time.time()
    openrouter_healthy = await openrouter_task
    openrouter_latency = (time.time() - openrouter_start) * 1000  # Convert to ms

    # Build check details
    checks: Dict[str, HealthCheckDetail] = {
        "db": HealthCheckDetail(
            healthy=db_healthy,
            latency_ms=round(db_latency, 2),
            error=None if db_healthy else "Database connection failed or timed out"
        ),
        "openrouter": HealthCheckDetail(
            healthy=openrouter_healthy,
            latency_ms=round(openrouter_latency, 2),
            error=None if openrouter_healthy else "OpenRouter API unreachable or timed out"
        ),
    }

    # Determine overall status
    all_healthy = all(check.healthy for check in checks.values())
    overall_status = "ready" if all_healthy else "not_ready"

    # Set HTTP status code
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status=overall_status,
        checks=checks,
        timestamp=datetime.utcnow()
    )


@router.get(
    "/health/agent",
    response_model=AgentStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Agent status",
    description="Agent loop status (stub - will be implemented in Week 4)",
)
async def agent_status() -> AgentStatusResponse:
    """
    Agent loop status endpoint.

    This is a stub implementation for Week 4.
    Currently returns "not_started" status.

    In Week 4, this will be expanded to:
    - Check if agent loop is running
    - Report last activity timestamp
    - Include agent metrics (posts, comments, belief updates)

    Returns:
        AgentStatusResponse with status and last_activity

    Example response:
        {
            "status": "not_started",
            "last_activity": null
        }
    """
    return AgentStatusResponse(
        status="not_started",
        last_activity=None
    )
