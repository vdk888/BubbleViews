"""
Agent Control API endpoints.

Provides REST endpoints for starting, stopping, and monitoring
agent loops per persona with authentication.
"""

from typing import Annotated, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.api.dependencies import CurrentActiveUser
from app.services.agent_manager import get_agent_manager, AgentManager

router = APIRouter()


# Request/Response models
class EngagementConfig(BaseModel):
    """Configuration for engagement-based post selection."""
    score_weight: float = Field(1.0, ge=0.0, le=10.0, description="Weight for post upvotes (default: 1.0)")
    comment_weight: float = Field(2.0, ge=0.0, le=10.0, description="Weight for comment count (default: 2.0)")
    min_probability: float = Field(0.1, ge=0.0, le=1.0, description="Min response probability for low-engagement posts (default: 0.1)")
    max_probability: float = Field(0.8, ge=0.0, le=1.0, description="Max response probability for high-engagement posts (default: 0.8)")
    probability_midpoint: float = Field(20.0, ge=1.0, le=1000.0, description="Engagement score at ~50% probability (default: 20.0)")


class AgentStartRequest(BaseModel):
    """Request to start an agent loop."""
    persona_id: str = Field(..., description="UUID of the persona to start agent for")
    interval_seconds: int | None = Field(None, ge=10, le=86400, description="Seconds between perception cycles (10-86400, optional - uses AGENT_INTERVAL_SECONDS env var or 14400 = 4 hours)")
    max_posts_per_cycle: int = Field(10, ge=1, le=20, description="Max posts to process per cycle (1-20)")
    response_probability: float = Field(0.3, ge=0.0, le=1.0, description="Legacy: base probability (superseded by engagement_config)")
    engagement_config: EngagementConfig | None = Field(None, description="Engagement-based post selection config (optional)")
    max_post_age_hours: int = Field(24, ge=1, le=168, description="Max age of posts to respond to in hours (1-168, default: 24)")

    class Config:
        json_schema_extra = {
            "example": {
                "persona_id": "123e4567-e89b-12d3-a456-426614174000",
                "interval_seconds": 14400,
                "max_posts_per_cycle": 10,
                "max_post_age_hours": 24,
                "engagement_config": {
                    "score_weight": 1.0,
                    "comment_weight": 2.0,
                    "min_probability": 0.1,
                    "max_probability": 0.8,
                    "probability_midpoint": 20.0
                }
            }
        }


class AgentStopRequest(BaseModel):
    """Request to stop an agent loop."""
    persona_id: str = Field(..., description="UUID of the persona to stop agent for")

    class Config:
        json_schema_extra = {
            "example": {
                "persona_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class AgentStatusResponse(BaseModel):
    """Response with agent status information."""
    persona_id: str
    status: str  # "running", "stopped", "error", "not_running"
    started_at: str | None
    last_activity: str | None
    error_message: str | None
    cycle_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "persona_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "running",
                "started_at": "2025-11-25T10:30:00",
                "last_activity": "2025-11-25T10:31:00",
                "error_message": None,
                "cycle_count": 5
            }
        }


class AgentActionResponse(BaseModel):
    """Response for start/stop actions."""
    persona_id: str
    status: str
    message: str
    started_at: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "persona_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "started",
                "message": "Agent started for u/DemoAgent",
                "started_at": "2025-11-25T10:30:00"
            }
        }


# Dependency for agent manager
AgentManagerDep = Annotated[AgentManager, Depends(get_agent_manager)]


@router.post(
    "/agent/start",
    response_model=AgentActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Start agent loop for a persona",
    description="""
    Start the autonomous agent loop for a specific persona.

    The agent will run in the background, monitoring Reddit for new posts
    and responding according to its configuration.

    **Authentication:** Required (Bearer token)

    **Behavior:**
    - If agent is already running, returns current status without starting a new task
    - Validates persona exists and has required configuration
    - Creates a background asyncio task that runs until stopped or crashes
    - Agent loop includes perception, decision, retrieval, generation, consistency check, moderation, and action phases

    **Configuration Parameters:**
    - `interval_seconds`: How often to check for new posts (10-86400 seconds, optional - defaults to AGENT_INTERVAL_SECONDS env var or 14400 = 4 hours)
    - `max_posts_per_cycle`: Max posts to process per cycle (1-20, default: 5)
    - `response_probability`: Random sampling rate for eligible posts (0.0-1.0, default: 0.3)

    **Request Body:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "max_posts_per_cycle": 5,
        "response_probability": 0.3
    }
    ```

    Or with optional interval override:
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "interval_seconds": 3600,
        "max_posts_per_cycle": 5,
        "response_probability": 0.3
    }
    ```

    **Example Response:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "status": "started",
        "message": "Agent started for u/DemoAgent",
        "started_at": "2025-11-25T10:30:00"
    }
    ```
    """,
    tags=["agent"]
)
async def start_agent(
    request: AgentStartRequest,
    current_user: CurrentActiveUser = None,
    agent_manager: AgentManagerDep = None
) -> AgentActionResponse:
    """
    Start agent loop for a persona.

    Args:
        request: Agent start request with persona_id and configuration
        current_user: Authenticated user (from dependency)
        agent_manager: AgentManager instance (from dependency)

    Returns:
        AgentActionResponse with status and message

    Raises:
        HTTPException 400: If persona not found or invalid configuration
        HTTPException 401: If not authenticated
        HTTPException 500: If services fail to initialize
    """
    try:
        # Convert engagement_config to dict if provided
        engagement_dict = None
        if request.engagement_config:
            engagement_dict = request.engagement_config.model_dump()

        result = await agent_manager.start_agent(
            persona_id=request.persona_id,
            interval_seconds=request.interval_seconds,
            max_posts_per_cycle=request.max_posts_per_cycle,
            response_probability=request.response_probability,
            engagement_config=engagement_dict,
            max_post_age_hours=request.max_post_age_hours
        )
        return AgentActionResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize agent services: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start agent: {str(e)}"
        )


@router.post(
    "/agent/stop",
    response_model=AgentActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Stop agent loop for a persona",
    description="""
    Stop the running agent loop for a specific persona.

    The agent will complete its current cycle and then exit gracefully.

    **Authentication:** Required (Bearer token)

    **Behavior:**
    - Signals the agent loop to stop gracefully
    - Waits up to 10 seconds for agent to complete current cycle
    - If timeout occurs, forcefully cancels the task
    - Updates status to "stopped"
    - If agent is not running, returns appropriate message

    **Request Body:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000"
    }
    ```

    **Example Response:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "status": "stopped",
        "message": "Agent stopped successfully"
    }
    ```
    """,
    tags=["agent"]
)
async def stop_agent(
    request: AgentStopRequest,
    current_user: CurrentActiveUser = None,
    agent_manager: AgentManagerDep = None
) -> AgentActionResponse:
    """
    Stop agent loop for a persona.

    Args:
        request: Agent stop request with persona_id
        current_user: Authenticated user (from dependency)
        agent_manager: AgentManager instance (from dependency)

    Returns:
        AgentActionResponse with status and message

    Raises:
        HTTPException 400: If persona not found
        HTTPException 401: If not authenticated
    """
    try:
        result = await agent_manager.stop_agent(persona_id=request.persona_id)
        return AgentActionResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop agent: {str(e)}"
        )


@router.get(
    "/agent/status",
    response_model=AgentStatusResponse,
    summary="Get agent status for a persona",
    description="""
    Retrieve the current status of the agent loop for a specific persona.

    **Authentication:** Required (Bearer token)

    **Status Values:**
    - `running`: Agent loop is actively running
    - `stopped`: Agent was running but has been stopped
    - `error`: Agent crashed with an error
    - `not_running`: Agent has never been started or status cleared

    **Query Parameters:**
    - `persona_id`: UUID of the persona (required)

    **Example Response:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "status": "running",
        "started_at": "2025-11-25T10:30:00",
        "last_activity": "2025-11-25T10:31:00",
        "error_message": null,
        "cycle_count": 5
    }
    ```

    **Use Case:**
    Used by dashboard to display agent status and enable/disable start/stop buttons.
    """,
    tags=["agent"]
)
async def get_agent_status(
    persona_id: str = Query(
        ...,
        description="UUID of the persona",
        example="123e4567-e89b-12d3-a456-426614174000"
    ),
    current_user: CurrentActiveUser = None,
    agent_manager: AgentManagerDep = None
) -> AgentStatusResponse:
    """
    Get agent status for a persona.

    Args:
        persona_id: UUID of the persona (from query param)
        current_user: Authenticated user (from dependency)
        agent_manager: AgentManager instance (from dependency)

    Returns:
        AgentStatusResponse with current status

    Raises:
        HTTPException 401: If not authenticated
    """
    try:
        status = await agent_manager.get_agent_status(persona_id=persona_id)
        return AgentStatusResponse(**status)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent status: {str(e)}"
        )


@router.get(
    "/agent/statuses",
    response_model=Dict[str, AgentStatusResponse],
    summary="Get status of all agents",
    description="""
    Retrieve the status of all known agent loops across all personas.

    **Authentication:** Required (Bearer token)

    **Returns:**
    Dict mapping persona_id to status information for all agents that
    have been started (running, stopped, or errored).

    **Example Response:**
    ```json
    {
        "123e4567-e89b-12d3-a456-426614174000": {
            "persona_id": "123e4567-e89b-12d3-a456-426614174000",
            "status": "running",
            "started_at": "2025-11-25T10:30:00",
            "last_activity": "2025-11-25T10:31:00",
            "error_message": null,
            "cycle_count": 5
        },
        "456e7890-e89b-12d3-a456-426614174001": {
            "persona_id": "456e7890-e89b-12d3-a456-426614174001",
            "status": "stopped",
            "started_at": "2025-11-25T09:00:00",
            "last_activity": "2025-11-25T09:30:00",
            "error_message": null,
            "cycle_count": 15
        }
    }
    ```

    **Use Case:**
    Used by admin dashboard to monitor all running agents.
    """,
    tags=["agent"]
)
async def get_all_agent_statuses(
    current_user: CurrentActiveUser = None,
    agent_manager: AgentManagerDep = None
) -> Dict[str, Dict[str, Any]]:
    """
    Get status of all agents.

    Args:
        current_user: Authenticated user (from dependency)
        agent_manager: AgentManager instance (from dependency)

    Returns:
        Dict mapping persona_id to status dict

    Raises:
        HTTPException 401: If not authenticated
    """
    try:
        statuses = await agent_manager.get_all_agent_statuses()
        return statuses
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent statuses: {str(e)}"
        )


# =============================================================================
# Systemd Service Control Endpoints (for persistent background agent)
# =============================================================================

import asyncio
import os

SYSTEMD_SERVICE_NAME = "bubbleviews-agent"
AGENT_ENV_FILE = "/root/BubbleViews/backend/.agent_persona"


class SystemdAgentRequest(BaseModel):
    """Request to start/stop the systemd agent service."""
    persona_id: str = Field(..., description="UUID of the persona to run")

    class Config:
        json_schema_extra = {
            "example": {
                "persona_id": "0f26b1c9-6370-46c2-8a9f-d866f43f963b"
            }
        }


class SystemdAgentStatusResponse(BaseModel):
    """Response with systemd agent service status."""
    active: bool
    status: str  # "running", "stopped", "failed", "unknown"
    persona_id: str | None
    persona_name: str | None
    message: str


async def run_systemctl(command: str) -> tuple[int, str, str]:
    """Run a systemctl command and return (returncode, stdout, stderr)."""
    # Use full path to systemctl to avoid PATH issues
    command = command.replace("systemctl", "/usr/bin/systemctl")
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()


@router.post(
    "/agent/systemd/start",
    response_model=SystemdAgentStatusResponse,
    summary="Start the persistent background agent (systemd)",
    description="""
    Start the systemd-managed agent service for a specific persona.

    This runs the agent as a background daemon that persists across API restarts.
    Only one persona can run at a time via systemd.

    **Authentication:** Required (Bearer token)
    """,
    tags=["agent-systemd"]
)
async def start_systemd_agent(
    request: SystemdAgentRequest,
    current_user: CurrentActiveUser
) -> SystemdAgentStatusResponse:
    """Start the systemd agent service for a persona."""
    try:
        # Verify persona exists and get name using direct DB access
        from app.core.database import async_session_maker
        from app.services.memory_store import SQLiteMemoryStore
        memory_store = SQLiteMemoryStore(async_session_maker)
        persona = await memory_store.get_persona(request.persona_id)
        if not persona:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Persona not found: {request.persona_id}"
            )

        persona_name = persona.get("display_name") or persona.get("reddit_username")

        # Write persona ID to env file
        with open(AGENT_ENV_FILE, "w") as f:
            f.write(f"AGENT_PERSONA_ID={request.persona_id}\n")

        # Reset failed state if any, then restart the systemd service
        await run_systemctl(f"systemctl reset-failed {SYSTEMD_SERVICE_NAME}")
        returncode, stdout, stderr = await run_systemctl(
            f"systemctl restart {SYSTEMD_SERVICE_NAME}"
        )

        if returncode != 0:
            return SystemdAgentStatusResponse(
                active=False,
                status="failed",
                persona_id=request.persona_id,
                persona_name=persona_name,
                message=f"Failed to start service: {stderr}"
            )

        # Wait a moment and check status
        await asyncio.sleep(2)
        returncode, stdout, stderr = await run_systemctl(
            f"systemctl is-active {SYSTEMD_SERVICE_NAME}"
        )

        is_active = stdout.strip() == "active"

        return SystemdAgentStatusResponse(
            active=is_active,
            status="running" if is_active else "failed",
            persona_id=request.persona_id,
            persona_name=persona_name,
            message=f"Agent started for {persona_name}" if is_active else f"Service not active: {stdout.strip()}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start systemd agent: {str(e)}"
        )


@router.post(
    "/agent/systemd/stop",
    response_model=SystemdAgentStatusResponse,
    summary="Stop the persistent background agent (systemd)",
    description="""
    Stop the systemd-managed agent service.

    **Authentication:** Required (Bearer token)
    """,
    tags=["agent-systemd"]
)
async def stop_systemd_agent(
    current_user: CurrentActiveUser
) -> SystemdAgentStatusResponse:
    """Stop the systemd agent service."""
    try:
        # Stop the service
        returncode, stdout, stderr = await run_systemctl(
            f"systemctl stop {SYSTEMD_SERVICE_NAME}"
        )

        if returncode != 0:
            return SystemdAgentStatusResponse(
                active=True,
                status="failed",
                persona_id=None,
                persona_name=None,
                message=f"Failed to stop service: {stderr}"
            )

        return SystemdAgentStatusResponse(
            active=False,
            status="stopped",
            persona_id=None,
            persona_name=None,
            message="Agent stopped"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop systemd agent: {str(e)}"
        )


@router.get(
    "/agent/systemd/status",
    response_model=SystemdAgentStatusResponse,
    summary="Get persistent background agent status (systemd)",
    description="""
    Get the status of the systemd-managed agent service.

    **Authentication:** Required (Bearer token)
    """,
    tags=["agent-systemd"]
)
async def get_systemd_agent_status(
    current_user: CurrentActiveUser
) -> SystemdAgentStatusResponse:
    """Get the systemd agent service status."""
    try:
        # Check if service is active
        returncode, stdout, stderr = await run_systemctl(
            f"systemctl is-active {SYSTEMD_SERVICE_NAME}"
        )
        is_active = stdout.strip() == "active"

        # Read current persona ID from env file
        persona_id = None
        persona_name = None
        if os.path.exists(AGENT_ENV_FILE):
            try:
                with open(AGENT_ENV_FILE, "r") as f:
                    for line in f:
                        if line.startswith("AGENT_PERSONA_ID="):
                            persona_id = line.strip().split("=", 1)[1]
                            break
            except Exception:
                pass

        # Get persona name if we have an ID
        if persona_id:
            try:
                from app.core.database import async_session_maker
                from app.services.memory_store import SQLiteMemoryStore
                memory_store = SQLiteMemoryStore(async_session_maker)
                persona = await memory_store.get_persona(persona_id)
                if persona:
                    persona_name = persona.get("display_name") or persona.get("reddit_username")
            except Exception:
                pass

        if is_active:
            status_str = "running"
            message = f"Agent running for {persona_name or 'unknown persona'}"
        else:
            # Check if it failed or just stopped
            returncode2, stdout2, _ = await run_systemctl(
                f"systemctl is-failed {SYSTEMD_SERVICE_NAME}"
            )
            if stdout2.strip() == "failed":
                status_str = "failed"
                message = "Agent service failed - check logs"
            else:
                status_str = "stopped"
                message = "Agent not running"

        return SystemdAgentStatusResponse(
            active=is_active,
            status=status_str,
            persona_id=persona_id,
            persona_name=persona_name,
            message=message
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get systemd agent status: {str(e)}"
        )
