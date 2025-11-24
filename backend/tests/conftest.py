"""
Pytest configuration and shared fixtures.

This module provides:
- Environment variable setup for tests
- Shared test fixtures
- Mock configurations
"""

import os
import sys
from pathlib import Path

import pytest


# Set test environment variables BEFORE any imports
# This must happen first to ensure settings load with test values
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDDIT_CLIENT_ID"] = "test_client_id"
os.environ["REDDIT_CLIENT_SECRET"] = "test_client_secret"
os.environ["REDDIT_USER_AGENT"] = "test_user_agent"
os.environ["REDDIT_USERNAME"] = "test_username"
os.environ["REDDIT_PASSWORD"] = "test_password"
os.environ["OPENROUTER_API_KEY"] = "test_api_key"
os.environ["OPENROUTER_BASE_URL"] = "https://openrouter.ai/api/v1"
os.environ["SECRET_KEY"] = "test_secret_key_at_least_32_characters_long_for_jwt"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["TARGET_SUBREDDITS"] = '["test", "bottest"]'
os.environ["AUTO_POSTING_ENABLED"] = "false"

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


@pytest.fixture
def anyio_backend():
    """
    Configure anyio backend for async tests.

    Returns:
        str: Backend name ("asyncio")
    """
    return "asyncio"


@pytest.fixture(scope="function")
async def db_session():
    """
    Provide a database session for tests.

    Creates tables before test and cleans up after.
    """
    from app.core.database import engine, async_session_maker
    from app.models.base import Base
    from app.models import Admin  # noqa: F401 - Import to register model

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Provide session
    async with async_session_maker() as session:
        yield session

    # Drop all tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
