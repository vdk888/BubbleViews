"""
Database configuration and session management.

Provides SQLAlchemy async engine setup, session factory, and dependency
injection for database sessions in FastAPI routes.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool

from app.core.config import settings


# SQLAlchemy declarative base for ORM models
Base = declarative_base()


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
    # SQLite-specific connection arguments
    connect_args = {
        "check_same_thread": False,  # Required for async SQLite
    }

    # Create async engine
    engine = create_async_engine(
        settings.database_url,
        echo=False,  # Set to True for SQL query logging (debug only)
        future=True,  # Use SQLAlchemy 2.0 style
        poolclass=StaticPool,  # SQLite works best with StaticPool
        connect_args=connect_args,
    )

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

    Creates all tables defined by SQLAlchemy models.
    Should be called once at application startup.

    Note:
        In production, use Alembic migrations instead of create_all().
        This function is useful for testing and development.

    Example:
        @app.on_event("startup")
        async def startup():
            await init_db()
    """
    async with engine.begin() as conn:
        # Import all models here to ensure they're registered
        # This is necessary for Base.metadata.create_all() to work
        # from app.models import belief, interaction, pending_post

        await conn.run_sync(Base.metadata.create_all)

        # Enable WAL mode for better concurrency (SQLite specific)
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
