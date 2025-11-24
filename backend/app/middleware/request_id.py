"""
Request ID middleware for correlation tracking.

This middleware ensures every request has a unique correlation ID:
- Reads X-Request-ID header from client (if provided)
- Generates UUID if header is missing
- Stores in request.state for access by other middleware/routes
- Includes in response headers for client-side correlation

This enables end-to-end request tracing across logs, services, and client apps.
"""

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request ID correlation to all requests.

    The request ID is used for:
    - Correlating log entries for a single request
    - Tracing requests across services
    - Debugging and troubleshooting
    - Linking frontend actions to backend processing

    Flow:
    1. Check for X-Request-ID header in incoming request
    2. If present, use it; otherwise generate new UUID
    3. Store in request.state.request_id
    4. Add to response headers as X-Request-ID

    Example:
        app.add_middleware(RequestIDMiddleware)

    Usage in routes:
        @app.get("/example")
        async def example(request: Request):
            request_id = request.state.request_id
            logger.info("Processing request", extra={"request_id": request_id})
            return {"request_id": request_id}
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request and add request ID.

        Args:
            request: Incoming FastAPI request
            call_next: Next middleware/route handler in chain

        Returns:
            Response with X-Request-ID header
        """
        # Check for existing request ID in headers
        request_id = request.headers.get("X-Request-ID")

        # Generate new UUID if not provided
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state for access by routes and other middleware
        request.state.request_id = request_id

        # Process request through remaining middleware/routes
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response
