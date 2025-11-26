"""
Gateway Authentication Middleware

Validates that requests come from authorized origins.
Uses Origin/Referer header checking against allowed Vercel deployment URLs.

This provides an additional layer of security beyond CORS.
"""

import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class GatewayAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates requests come from authorized sources.

    Checks Origin/Referer headers against allowed origins.
    """

    # Endpoints that don't require gateway authentication
    EXCLUDED_PATHS = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/openapi.json",
        "/api/v1/health",
        "/",
    ]

    def __init__(self, app, allowed_origins: list | None = None):
        super().__init__(app)

        # Get allowed origins from environment or use defaults
        env_origins = os.getenv("ALLOWED_GATEWAY_ORIGINS", "")
        if env_origins:
            self.allowed_origins = [o.strip() for o in env_origins.split(",")]
        elif allowed_origins:
            self.allowed_origins = allowed_origins
        else:
            # Default: allow all Vercel preview deployments for this project
            self.allowed_origins = []

        # Always allow localhost for development
        self.allowed_origins.extend([
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ])

    def _extract_origin(self, request: Request) -> str:
        """Extract origin from request headers."""
        origin = request.headers.get("Origin") or request.headers.get("Referer", "")

        if not origin:
            return ""

        # Skip invalid origins
        if not origin.startswith("http"):
            return ""

        # Extract just the origin from full URL
        # e.g., https://example.com/path -> https://example.com
        try:
            parts = origin.split("/")
            if len(parts) >= 3:
                return "/".join(parts[:3])
        except Exception:
            pass

        return origin

    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is in the allowed list or matches Vercel pattern."""
        if not origin:
            return False

        # Check exact match
        if origin in self.allowed_origins:
            return True

        # Check prefix match
        for allowed in self.allowed_origins:
            if origin.startswith(allowed):
                return True

        # Allow any Vercel deployment for this project
        # Pattern: https://frontend-*-joris-projects-4fa71758.vercel.app
        if "joris-projects-4fa71758.vercel.app" in origin:
            return True

        return False

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip authentication for excluded paths
        for excluded in self.EXCLUDED_PATHS:
            if path == excluded or path.startswith(excluded):
                return await call_next(request)

        # Check if gateway auth is enabled
        if os.getenv("DISABLE_GATEWAY_AUTH", "").lower() == "true":
            return await call_next(request)

        origin = self._extract_origin(request)

        if not self._is_origin_allowed(origin):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Request not authorized",
                    "hint": "Request must come from an authorized origin"
                }
            )

        return await call_next(request)
