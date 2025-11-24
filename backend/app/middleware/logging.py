"""
Logging middleware for request/response tracking.

This middleware logs every HTTP request and response with:
- Request details (method, path, query params)
- Response status code
- Request latency in milliseconds
- Request correlation ID
- Exception details (if request failed)

Must be registered AFTER RequestIDMiddleware to access request_id.
"""

import time
import traceback
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging_config import get_logger


logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all HTTP requests and responses.

    Logs include:
    - Request start: method, path, query params
    - Request end: status code, latency, request ID
    - Exceptions: full traceback and error details

    This middleware should be registered after RequestIDMiddleware
    so that request.state.request_id is available.

    Example:
        app.add_middleware(RequestIDMiddleware)  # First
        app.add_middleware(LoggingMiddleware)    # Second (runs after RequestID)

    Log output (JSON):
        {
            "timestamp": "2025-11-24T10:30:00.123456",
            "level": "INFO",
            "message": "Request completed",
            "method": "GET",
            "path": "/api/v1/health",
            "status_code": 200,
            "latency_ms": 12.5,
            "request_id": "abc-123"
        }
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request and log details.

        Args:
            request: Incoming FastAPI request
            call_next: Next middleware/route handler in chain

        Returns:
            Response from route handler
        """
        # Extract request details
        method = request.method
        path = request.url.path
        query_params = str(request.query_params) if request.query_params else None

        # Get request ID (set by RequestIDMiddleware)
        request_id = getattr(request.state, "request_id", None)

        # Log request start
        logger.info(
            "Request started",
            extra={
                "method": method,
                "path": path,
                "query_params": query_params,
                "request_id": request_id,
            }
        )

        # Record start time
        start_time = time.time()

        # Process request
        try:
            response = await call_next(request)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Log request completion
            logger.info(
                "Request completed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                    "request_id": request_id,
                }
            )

            return response

        except Exception as exc:
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Log exception with full traceback
            logger.error(
                f"Request failed: {str(exc)}",
                extra={
                    "method": method,
                    "path": path,
                    "latency_ms": round(latency_ms, 2),
                    "request_id": request_id,
                    "exception_type": type(exc).__name__,
                },
                exc_info=True  # Include full traceback
            )

            # Re-raise exception to be handled by FastAPI
            raise
