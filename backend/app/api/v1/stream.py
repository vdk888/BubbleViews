"""
Server-Sent Events (SSE) streaming endpoint for real-time updates.

This module provides a streaming endpoint that pushes real-time events
to connected clients for live dashboard updates.

Endpoint: GET /api/v1/stream?persona_id={id}

Events pushed:
- new_interaction: Agent posted/commented on Reddit
- pending_post_added: New item added to moderation queue
- belief_updated: Belief confidence or stance changed
- agent_status_changed: Agent started/stopped/errored
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from sse_starlette import EventSourceResponse

from app.services.event_publisher import event_publisher, Event

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/stream",
    summary="SSE event stream",
    description="Server-Sent Events stream for real-time dashboard updates",
    response_class=EventSourceResponse,
)
async def event_stream(
    request: Request,
    persona_id: str = Query(
        ...,
        description="Persona ID to subscribe to events for",
        example="550e8400-e29b-41d4-a716-446655440000"
    )
) -> EventSourceResponse:
    """
    Server-Sent Events endpoint for real-time updates.

    Opens a persistent connection and streams events as they occur.
    Automatically reconnects on disconnect with browser's built-in
    EventSource retry logic.

    **Event Types:**
    - `new_interaction`: Agent posted new content to Reddit
    - `pending_post_added`: New post queued for moderation review
    - `belief_updated`: Belief confidence or stance was modified
    - `agent_status_changed`: Agent loop status changed

    **Connection Management:**
    - Sends keepalive comments every 30 seconds
    - Automatically cleans up on client disconnect
    - Client should reconnect on connection loss

    **Example Event:**
    ```
    event: new_interaction
    data: {
        "type": "new_interaction",
        "persona_id": "550e8400-e29b-41d4-a716-446655440000",
        "data": {
            "id": "abc123",
            "content": "Great discussion!",
            "interaction_type": "comment",
            "subreddit": "test"
        },
        "timestamp": "2025-11-24T10:30:00.123456"
    }
    ```

    Args:
        request: FastAPI request object (for disconnect detection)
        persona_id: Persona ID to stream events for

    Returns:
        EventSourceResponse with streaming events
    """
    logger.info(f"SSE client connected for persona_id={persona_id}")

    async def event_generator():
        """
        Async generator that yields SSE-formatted events.

        Subscribes to the event publisher and formats events
        according to the SSE specification.
        """
        try:
            # Subscribe to events for this persona
            async for event in event_publisher.subscribe(persona_id):
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected (detected via request), "
                               f"persona_id={persona_id}")
                    break

                # Format event for SSE transmission
                # SSE format: "event: <type>\ndata: <json>\n\n"
                yield event.to_sse_format()

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for persona_id={persona_id}")
            raise
        except Exception as e:
            logger.error(
                f"Error in SSE stream for persona_id={persona_id}: {e}",
                exc_info=True
            )
            raise
        finally:
            logger.info(f"SSE stream ended for persona_id={persona_id}")

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
        ping=30,  # Send keepalive ping every 30 seconds
    )


@router.get(
    "/stream/status",
    summary="Stream connection status",
    description="Get current SSE connection statistics",
)
async def stream_status(
    persona_id: Optional[str] = Query(
        None,
        description="Persona ID to check (if None, returns global stats)"
    )
) -> dict:
    """
    Get SSE connection statistics.

    Useful for monitoring and debugging streaming connections.

    Args:
        persona_id: Optional persona ID to filter stats

    Returns:
        Dict with connection counts and status

    Example response (global):
        {
            "total_subscribers": 3,
            "personas": {
                "persona_123": 2,
                "persona_456": 1
            }
        }

    Example response (specific persona):
        {
            "persona_id": "persona_123",
            "subscriber_count": 2
        }
    """
    if persona_id:
        count = event_publisher.get_subscriber_count(persona_id)
        return {
            "persona_id": persona_id,
            "subscriber_count": count
        }

    # Global stats
    total = event_publisher.get_subscriber_count()
    # Get per-persona counts
    personas = {}
    for pid in event_publisher._subscribers.keys():
        personas[pid] = event_publisher.get_subscriber_count(pid)

    return {
        "total_subscribers": total,
        "personas": personas
    }
