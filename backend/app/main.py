"""
Reddit AI Agent - FastAPI Application Entry Point

This module initializes the FastAPI application with all middleware,
routes, and lifecycle event handlers.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logging_config import setup_logging
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.logging import LoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.

    Handles startup and shutdown events for the FastAPI application.

    Startup:
        - Initialize database (create tables)
        - Set up logging
        - Initialize services

    Shutdown:
        - Close database connections
        - Clean up resources
    """
    # Startup
    # Initialize structured JSON logging
    setup_logging(level="INFO", json_format=True)

    # Initialize database
    await init_db()

    yield

    # Shutdown
    await close_db()


# Create FastAPI application instance
app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    description="Autonomous Reddit AI Agent with Belief Graph and Memory System",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# Configure middleware
# Note: Middleware is executed in reverse order of registration
# (last registered = first executed)

# Security headers middleware (runs last, adds headers to response)
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting middleware (protects all endpoints)
app.add_middleware(
    RateLimitMiddleware,
    auth_limit=10,  # 10 requests/minute for auth endpoints
    default_limit=60  # 60 requests/minute for other endpoints
)

# Logging middleware (runs after RequestID to access request_id)
app.add_middleware(LoggingMiddleware)

# Request ID middleware (first to run - sets correlation ID)
app.add_middleware(RequestIDMiddleware)

# CORS middleware - configured from environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Import and include routers
from app.api.v1 import (
    health,
    auth,
    protected,
    settings as settings_router,
    personas,
    activity,
    beliefs,
    moderation,
    stats,
    stream,
    governor,
    costs,
    agent,
)

app.include_router(health.router, prefix=settings.api_v1_prefix, tags=["health"])
app.include_router(auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"])
app.include_router(protected.router, prefix=f"{settings.api_v1_prefix}/protected", tags=["protected"])
app.include_router(settings_router.router, prefix=settings.api_v1_prefix, tags=["settings"])
app.include_router(personas.router, prefix=settings.api_v1_prefix, tags=["personas"])
app.include_router(activity.router, prefix=settings.api_v1_prefix, tags=["activity"])
app.include_router(beliefs.router, prefix=settings.api_v1_prefix, tags=["beliefs"])
app.include_router(moderation.router, prefix=settings.api_v1_prefix, tags=["moderation"])
app.include_router(stats.router, prefix=settings.api_v1_prefix, tags=["stats"])
app.include_router(stream.router, prefix=settings.api_v1_prefix, tags=["stream"])
app.include_router(governor.router, prefix=settings.api_v1_prefix, tags=["governor"])
app.include_router(costs.router, prefix=settings.api_v1_prefix, tags=["costs"])
app.include_router(agent.router, prefix=settings.api_v1_prefix, tags=["agent"])


@app.get("/")
async def root():
    """
    Root endpoint.

    Returns basic API information.
    """
    return {
        "message": "Reddit AI Agent API",
        "version": "0.1.0",
        "docs": "/docs",
    }


