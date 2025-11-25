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
class AgentStartRequest(BaseModel):
    """Request to start an agent loop."""
    persona_id: str = Field(..., description="UUID of the persona to start agent for")
    interval_seconds: int = Field(60, ge=10, le=600, description="Seconds between perception cycles (10-600)")
    max_posts_per_cycle: int = Field(5, ge=1, le=20, description="Max posts to process per cycle (1-20)")
    response_probability: float = Field(0.3, ge=0.0, le=1.0, description="Probability of responding to eligible posts (0.0-1.0)")

    class Config:
        json_schema_extra = {
            "example": {
                "persona_id": "123e4567-e89b-12d3-a456-426614174000",
                "interval_seconds": 60,
                "max_posts_per_cycle": 5,
                "response_probability": 0.3
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
    - `interval_seconds`: How often to check for new posts (10-600 seconds, default: 60)
    - `max_posts_per_cycle`: Max posts to process per cycle (1-20, default: 5)
    - `response_probability`: Random sampling rate for eligible posts (0.0-1.0, default: 0.3)

    **Request Body:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "interval_seconds": 60,
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
        result = await agent_manager.start_agent(
            persona_id=request.persona_id,
            interval_seconds=request.interval_seconds,
            max_posts_per_cycle=request.max_posts_per_cycle,
            response_probability=request.response_probability
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
