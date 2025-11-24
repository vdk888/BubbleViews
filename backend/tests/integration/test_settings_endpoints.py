"""
Integration tests for settings API endpoints.

Tests the complete request/response cycle with authentication and validation.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
import json

from app.main import app
from app.models.base import Base
from app.models.persona import Persona
from app.models.user import Admin
from app.models.agent_config import AgentConfig
from app.core.security import get_password_hash, create_access_token
from app.core.database import get_db


@pytest.fixture
async def async_session():
    """
    Create an in-memory database session for testing.

    Yields:
        AsyncSession for testing
    """
    # Import all models to ensure they're registered with Base.metadata
    from app.models import persona, user, agent_config

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def test_admin(async_session: AsyncSession):
    """
    Create test admin user.

    Args:
        async_session: Database session fixture

    Returns:
        Admin instance
    """
    admin = Admin(
        username="testadmin",
        hashed_password=get_password_hash("testpass123")
    )
    async_session.add(admin)
    await async_session.commit()
    await async_session.refresh(admin)
    return admin


@pytest.fixture
def auth_token(test_admin: Admin) -> str:
    """
    Create JWT token for test admin.

    Args:
        test_admin: Admin user fixture

    Returns:
        JWT access token string
    """
    return create_access_token(data={"sub": test_admin.username})


@pytest.fixture
async def test_persona(async_session: AsyncSession):
    """
    Create test persona.

    Args:
        async_session: Database session fixture

    Returns:
        Persona instance
    """
    persona = Persona(
        reddit_username="TestBot",
        display_name="Test Agent",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()
    await async_session.refresh(persona)
    return persona


@pytest.fixture
async def client(async_session: AsyncSession):
    """
    Create async HTTP client with database override.

    Args:
        async_session: Database session fixture

    Yields:
        AsyncClient for making requests
    """
    from httpx import ASGITransport

    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestGetSettings:
    """Test suite for GET /api/v1/settings endpoint."""

    async def test_get_settings_empty(
        self,
        client: AsyncClient,
        test_persona: Persona,
        auth_token: str
    ):
        """
        Test retrieving settings when none exist.

        Arrange: Persona with no config
        Act: GET /api/v1/settings
        Assert: Empty config dict returned
        """
        # Act
        response = await client.get(
            "/api/v1/settings",
            params={"persona_id": test_persona.id},
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["persona_id"] == test_persona.id
        assert data["config"] == {}

    async def test_get_settings_with_config(
        self,
        client: AsyncClient,
        test_persona: Persona,
        auth_token: str,
        async_session: AsyncSession
    ):
        """
        Test retrieving existing settings.

        Arrange: Persona with config entries
        Act: GET /api/v1/settings
        Assert: All config entries returned
        """
        # Arrange
        configs = [
            AgentConfig(
                persona_id=test_persona.id,
                config_key="target_subreddits",
                config_value=json.dumps(["test", "bottest"])
            ),
            AgentConfig(
                persona_id=test_persona.id,
                config_key="auto_posting_enabled",
                config_value=json.dumps(False)
            ),
        ]
        for config in configs:
            async_session.add(config)
        await async_session.commit()

        # Act
        response = await client.get(
            "/api/v1/settings",
            params={"persona_id": test_persona.id},
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["persona_id"] == test_persona.id
        assert data["config"]["target_subreddits"] == ["test", "bottest"]
        assert data["config"]["auto_posting_enabled"] is False

    async def test_get_settings_nonexistent_persona(
        self,
        client: AsyncClient,
        auth_token: str
    ):
        """
        Test retrieving settings for non-existent persona.

        Arrange: Invalid persona_id
        Act: GET /api/v1/settings
        Assert: 404 Not Found
        """
        # Act
        response = await client.get(
            "/api/v1/settings",
            params={"persona_id": "nonexistent-id"},
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_settings_no_auth(
        self,
        client: AsyncClient,
        test_persona: Persona
    ):
        """
        Test retrieving settings without authentication.

        Arrange: No auth token
        Act: GET /api/v1/settings
        Assert: 401 Unauthorized (from dependency, may be 403)
        """
        # Act
        response = await client.get(
            "/api/v1/settings",
            params={"persona_id": test_persona.id}
        )

        # Assert
        assert response.status_code in [401, 403]


class TestUpdateSetting:
    """Test suite for POST /api/v1/settings endpoint."""

    async def test_update_setting_new(
        self,
        client: AsyncClient,
        test_persona: Persona,
        auth_token: str
    ):
        """
        Test creating a new setting.

        Arrange: Persona with no config
        Act: POST /api/v1/settings
        Assert: Setting is created successfully
        """
        # Act
        response = await client.post(
            "/api/v1/settings",
            json={
                "persona_id": test_persona.id,
                "key": "auto_posting_enabled",
                "value": True
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["persona_id"] == test_persona.id
        assert data["key"] == "auto_posting_enabled"
        assert data["value"] is True
        assert data["updated"] is True

    async def test_update_setting_existing(
        self,
        client: AsyncClient,
        test_persona: Persona,
        auth_token: str,
        async_session: AsyncSession
    ):
        """
        Test updating an existing setting.

        Arrange: Persona with existing config
        Act: POST /api/v1/settings with new value
        Assert: Setting is updated successfully
        """
        # Arrange
        config = AgentConfig(
            persona_id=test_persona.id,
            config_key="test_key",
            config_value=json.dumps("old_value")
        )
        async_session.add(config)
        await async_session.commit()

        # Act
        response = await client.post(
            "/api/v1/settings",
            json={
                "persona_id": test_persona.id,
                "key": "test_key",
                "value": "new_value"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == "new_value"

    async def test_update_setting_unsafe_key(
        self,
        client: AsyncClient,
        test_persona: Persona,
        auth_token: str
    ):
        """
        Test blocking unsafe config keys.

        Arrange: Try to update unsafe key
        Act: POST /api/v1/settings
        Assert: 400 Bad Request
        """
        unsafe_keys = [
            "admin_password",
            "api_key",
            "secret_key",
            "database_url",
            "reddit_client_secret",
        ]

        for unsafe_key in unsafe_keys:
            # Act
            response = await client.post(
                "/api/v1/settings",
                json={
                    "persona_id": test_persona.id,
                    "key": unsafe_key,
                    "value": "malicious_value"
                },
                headers={"Authorization": f"Bearer {auth_token}"}
            )

            # Assert
            assert response.status_code == 400
            assert "unsafe" in response.json()["detail"].lower()

    async def test_update_setting_nonexistent_persona(
        self,
        client: AsyncClient,
        auth_token: str
    ):
        """
        Test updating setting for non-existent persona.

        Arrange: Invalid persona_id
        Act: POST /api/v1/settings
        Assert: 404 Not Found
        """
        # Act
        response = await client.post(
            "/api/v1/settings",
            json={
                "persona_id": "nonexistent-id",
                "key": "test_key",
                "value": "test_value"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 404

    async def test_update_setting_complex_value(
        self,
        client: AsyncClient,
        test_persona: Persona,
        auth_token: str
    ):
        """
        Test updating setting with complex nested value.

        Arrange: Complex nested dict/list value
        Act: POST /api/v1/settings
        Assert: Value is serialized and stored correctly
        """
        # Arrange
        complex_value = {
            "nested": {
                "deep": ["list", "of", "values"],
                "number": 42,
                "bool": True
            }
        }

        # Act
        response = await client.post(
            "/api/v1/settings",
            json={
                "persona_id": test_persona.id,
                "key": "complex_key",
                "value": complex_value
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == complex_value

    async def test_update_setting_no_auth(
        self,
        client: AsyncClient,
        test_persona: Persona
    ):
        """
        Test updating setting without authentication.

        Arrange: No auth token
        Act: POST /api/v1/settings
        Assert: 401 Unauthorized (or 403)
        """
        # Act
        response = await client.post(
            "/api/v1/settings",
            json={
                "persona_id": test_persona.id,
                "key": "test_key",
                "value": "test_value"
            }
        )

        # Assert
        assert response.status_code in [401, 403]


class TestDeleteSetting:
    """Test suite for DELETE /api/v1/settings endpoint."""

    async def test_delete_setting_existing(
        self,
        client: AsyncClient,
        test_persona: Persona,
        auth_token: str,
        async_session: AsyncSession
    ):
        """
        Test deleting an existing setting.

        Arrange: Persona with config entry
        Act: DELETE /api/v1/settings
        Assert: Setting is deleted successfully
        """
        # Arrange
        config = AgentConfig(
            persona_id=test_persona.id,
            config_key="delete_key",
            config_value=json.dumps("value")
        )
        async_session.add(config)
        await async_session.commit()

        # Act
        response = await client.delete(
            "/api/v1/settings",
            params={
                "persona_id": test_persona.id,
                "key": "delete_key"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 204

    async def test_delete_setting_nonexistent(
        self,
        client: AsyncClient,
        test_persona: Persona,
        auth_token: str
    ):
        """
        Test deleting a non-existent setting.

        Arrange: Persona with no such config
        Act: DELETE /api/v1/settings
        Assert: 404 Not Found
        """
        # Act
        response = await client.delete(
            "/api/v1/settings",
            params={
                "persona_id": test_persona.id,
                "key": "nonexistent_key"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 404


class TestListPersonas:
    """Test suite for GET /api/v1/settings/personas endpoint."""

    async def test_list_personas_empty(
        self,
        client: AsyncClient,
        auth_token: str
    ):
        """
        Test listing personas when none exist.

        Arrange: No personas
        Act: GET /api/v1/settings/personas
        Assert: Empty list returned
        """
        # Act
        response = await client.get(
            "/api/v1/settings/personas",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_list_personas_multiple(
        self,
        client: AsyncClient,
        auth_token: str,
        async_session: AsyncSession
    ):
        """
        Test listing multiple personas.

        Arrange: Multiple personas
        Act: GET /api/v1/settings/personas
        Assert: All personas returned
        """
        # Arrange
        personas = [
            Persona(reddit_username="Bot1", display_name="Agent 1", config="{}"),
            Persona(reddit_username="Bot2", display_name="Agent 2", config="{}"),
            Persona(reddit_username="Bot3", display_name="Agent 3", config="{}"),
        ]
        for persona in personas:
            async_session.add(persona)
        await async_session.commit()

        # Act
        response = await client.get(
            "/api/v1/settings/personas",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        usernames = [p["reddit_username"] for p in data]
        assert "Bot1" in usernames
        assert "Bot2" in usernames
        assert "Bot3" in usernames


class TestPersonaIsolation:
    """Test suite for persona isolation enforcement."""

    async def test_persona_isolation_config_separation(
        self,
        client: AsyncClient,
        auth_token: str,
        async_session: AsyncSession
    ):
        """
        Test that configs are properly isolated between personas.

        Arrange: Two personas with different configs
        Act: Retrieve config for each
        Assert: Each gets only their own config
        """
        # Arrange
        persona1 = Persona(reddit_username="Bot1", display_name="Bot 1", config="{}")
        persona2 = Persona(reddit_username="Bot2", display_name="Bot 2", config="{}")
        async_session.add_all([persona1, persona2])
        await async_session.commit()

        # Set different configs for each
        await client.post(
            "/api/v1/settings",
            json={
                "persona_id": persona1.id,
                "key": "shared_key",
                "value": "persona1_value"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        await client.post(
            "/api/v1/settings",
            json={
                "persona_id": persona2.id,
                "key": "shared_key",
                "value": "persona2_value"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Act
        response1 = await client.get(
            "/api/v1/settings",
            params={"persona_id": persona1.id},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        response2 = await client.get(
            "/api/v1/settings",
            params={"persona_id": persona2.id},
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Assert
        assert response1.json()["config"]["shared_key"] == "persona1_value"
        assert response2.json()["config"]["shared_key"] == "persona2_value"
