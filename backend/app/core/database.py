"""
Database configuration and session management.

Provides SQLAlchemy async engine setup, session factory, and dependency
injection for database sessions in FastAPI routes.
"""

import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models.base import Base


def get_async_engine() -> AsyncEngine:
    """
    Create and configure the async SQLAlchemy engine.

    For SQLite:
    - Uses StaticPool for connection pooling (single file database)
    - Enables check_same_thread=False for async compatibility
    - Sets WAL mode for better concurrency

    Returns:
        Configured AsyncEngine instance

    Note:
        Engine is created once at application startup and reused.
        Connection pool configuration is optimized for SQLite MVP.
    """
    is_sqlite = "sqlite" in settings.database_url

    # SQLite-specific connection arguments (noop for other drivers)
    connect_args: dict = {"check_same_thread": False} if is_sqlite else {}

    engine_kwargs = {
        "echo": False,  # Set to True for SQL query logging (debug only)
        "future": True,  # Use SQLAlchemy 2.0 style
        "connect_args": connect_args,
    }

    # SQLite works best with StaticPool; let other drivers use defaults
    if is_sqlite:
        engine_kwargs["poolclass"] = StaticPool

    # Create async engine
    engine = create_async_engine(
        settings.database_url,
        **engine_kwargs,
    )

    # SQLite connection pragmas for FK enforcement and WAL support.
    if "sqlite" in settings.database_url:
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


# Global async engine instance
# Created once at application startup
engine = get_async_engine()


# Async session factory
# Use this to create new sessions
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """
    Initialize the database.

    For production, run Alembic migrations instead of create_all().
    To allow create_all for local/dev, set ENABLE_DB_CREATE_ALL=1.

    Example:
        @app.on_event("startup")
        async def startup():
            await init_db()
    """
    # Import models to ensure metadata is populated before create_all()
    # Avoiding circular imports by importing inside the function.
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        # Only allow create_all when explicitly enabled
        if os.getenv("ENABLE_DB_CREATE_ALL", "").lower() in {"1", "true", "yes"}:
            await conn.run_sync(Base.metadata.create_all)

        # SQLite-specific pragmas for integrity and concurrency.
        if "sqlite" in settings.database_url:
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA journal_mode=WAL")


async def close_db() -> None:
    """
    Close the database connection.

    Should be called at application shutdown to cleanly close
    all database connections.

    Example:
        @app.on_event("shutdown")
        async def shutdown():
            await close_db()
    """
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get database session.

    Provides a database session for FastAPI route handlers.
    Automatically handles session lifecycle (commit/rollback/close).

    Yields:
        AsyncSession instance for database operations

    Example:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()

    Note:
        - Session is automatically closed after request
        - Exceptions trigger automatic rollback
        - Use async with db.begin() for explicit transactions
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Alternative session generator for use outside FastAPI dependencies.

    Similar to get_db() but with manual commit control.
    Useful for scripts, background tasks, and non-FastAPI contexts.

    Yields:
        AsyncSession instance for database operations

    Example:
        async for session in get_session():
            result = await session.execute(select(User))
            users = result.scalars().all()
            await session.commit()

    Note:
        - Caller must explicitly commit or rollback
        - Session is automatically closed after use
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db_context() -> AsyncSession:
    """
    Get database session for use outside of FastAPI dependencies.

    Useful for background tasks, CLI scripts, or testing.

    Returns:
        AsyncSession instance

    Example:
        async with get_db_context() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()

    Note:
        Caller is responsible for committing and closing the session.
    """
    return async_session_maker()


class DatabaseHealthCheck:
    """
    Database health check utilities.

    Provides methods to verify database connectivity and readiness.
    """

    @staticmethod
    async def check_connection() -> bool:
        """
        Check if database connection is healthy.

        Returns:
            True if database is reachable, False otherwise

        Example:
            is_healthy = await DatabaseHealthCheck.check_connection()
            if not is_healthy:
                raise Exception("Database unavailable")
        """
        try:
            async with async_session_maker() as session:
                await session.execute("SELECT 1")
                return True
        except Exception:
            return False

    @staticmethod
    async def get_database_info() -> dict:
        """
        Get database information for monitoring.

        Returns:
            Dictionary with database metadata

        Example:
            info = await DatabaseHealthCheck.get_database_info()
            print(f"Database: {info['url']}")
        """
        return {
            "url": settings.database_url,
            "dialect": "sqlite" if "sqlite" in settings.database_url else "postgresql",
            "async": True,
        }
