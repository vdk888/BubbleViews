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


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Import and include routers
from app.api.v1 import health

app.include_router(health.router, prefix=settings.api_v1_prefix, tags=["health"])


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
