"""
Health probe functions for dependency checks.

This module provides reusable probe functions for:
- Database connectivity (SQLite/PostgreSQL)
- OpenRouter API availability
- Other external dependencies

Each probe function:
- Returns bool (True = healthy, False = unhealthy)
- Handles exceptions gracefully
- Includes appropriate timeouts
- Can be used as FastAPI dependencies
"""

import asyncio
from typing import Optional

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session_maker


async def check_database(timeout_seconds: float = 2.0) -> bool:
    """
    Check database connectivity.

    Executes a simple SELECT 1 query to verify the database is reachable
    and responding. Includes timeout to prevent hanging on unreachable DB.

    Args:
        timeout_seconds: Maximum time to wait for response (default: 2.0)

    Returns:
        True if database is reachable and healthy, False otherwise

    Example:
        >>> is_healthy = await check_database()
        >>> if not is_healthy:
        ...     raise Exception("Database unavailable")
    """
    try:
        # Run the database query with timeout
        async with asyncio.timeout(timeout_seconds):
            async with async_session_maker() as session:
                # Execute simple query to verify connectivity
                result = await session.execute(text("SELECT 1"))
                result.scalar()
                return True

    except asyncio.TimeoutError:
        # Timeout waiting for database
        return False
    except Exception:
        # Any other error (connection failed, query error, etc.)
        return False


async def check_openrouter(timeout_seconds: float = 3.0) -> bool:
    """
    Check OpenRouter API availability.

    Sends a HEAD request to OpenRouter's models endpoint to verify
    the API is reachable and responding. Uses configured base URL
    from settings.

    Args:
        timeout_seconds: Maximum time to wait for response (default: 3.0)

    Returns:
        True if OpenRouter API is reachable (200-299 status), False otherwise

    Example:
        >>> is_healthy = await check_openrouter()
        >>> if not is_healthy:
        ...     print("OpenRouter API unavailable")
    """
    try:
        # Create HTTP client with timeout
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            # Send HEAD request to models endpoint
            # HEAD is lightweight - doesn't fetch full response body
            response = await client.head(
                f"{settings.openrouter_base_url}/models",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "HTTP-Referer": "https://github.com/bubbleviews/reddit-agent",
                    "X-Title": "Reddit AI Agent",
                }
            )

            # Consider 2xx status codes as healthy
            return 200 <= response.status_code < 300

    except httpx.TimeoutException:
        # Request timed out
        return False
    except httpx.RequestError:
        # Network error, DNS failure, etc.
        return False
    except Exception:
        # Any other unexpected error
        return False


async def get_probe_dependency(
    probe_name: str,
    probe_func: callable,
    timeout: Optional[float] = None
) -> bool:
    """
    Wrapper to use probe functions as FastAPI dependencies.

    This allows probe functions to be injected into route handlers
    for cleaner separation of concerns.

    Args:
        probe_name: Name of the probe (for logging/debugging)
        probe_func: Async function that returns bool
        timeout: Optional timeout override

    Returns:
        Result of probe function

    Example:
        >>> async def db_probe(
        ...     healthy: bool = Depends(
        ...         lambda: get_probe_dependency("db", check_database)
        ...     )
        ... ):
        ...     return {"db_healthy": healthy}
    """
    if timeout is not None:
        return await probe_func(timeout)
    return await probe_func()
