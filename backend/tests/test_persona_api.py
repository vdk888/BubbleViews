"""
Integration tests for Persona API endpoints.

Tests POST /api/v1/personas endpoint with various scenarios.
Follows 0_dev.md quality standards: AAA pattern, >80% coverage.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.security import create_access_token, get_password_hash
from app.repositories.persona import PersonaRepository
from app.models.user import Admin


@pytest.fixture
async def test_admin(async_session: AsyncSession):
    """
    Create test admin user in database.

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
async def auth_token(test_admin: Admin):
    """
    Create a valid JWT token for testing.

    Args:
        test_admin: Admin user fixture (ensures user exists in DB)

    Returns:
        str: Bearer token for Authorization header
    """
    token = create_access_token(data={"sub": test_admin.username})
    return f"Bearer {token}"


class TestPersonaAPICreate:
    """
    Test suite for POST /api/v1/personas endpoint.

    Tests creation with valid data, validation errors, conflicts, and auth.
    """

    @pytest.mark.anyio
    async def test_create_persona_success(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test successful persona creation with full config.

        Arrange: Prepare valid request data and auth token
        Act: POST to /api/v1/personas
        Assert: Returns 201 with persona data, persona saved to DB
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "TestAPIBot",
                "display_name": "Test API Agent",
                "config": {
                    "tone": "friendly",
                    "style": "concise",
                    "core_values": ["honesty"],
                    "target_subreddits": ["test"]
                }
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data,
                headers={"Authorization": auth_token}
            )

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["reddit_username"] == "TestAPIBot"
            assert data["display_name"] == "Test API Agent"
            assert data["config"]["tone"] == "friendly"
            assert "id" in data
            assert "created_at" in data

            # Verify persona was saved to database
            repo = PersonaRepository(async_session)
            saved_persona = await repo.get_persona(data["id"])
            assert saved_persona is not None
            assert saved_persona.reddit_username == "TestAPIBot"

    @pytest.mark.anyio
    async def test_create_persona_minimal(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test persona creation with minimal required fields.

        Arrange: Prepare request with only username
        Act: POST to /api/v1/personas
        Assert: Returns 201 with defaults for optional fields
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "MinimalAPIBot"
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data,
                headers={"Authorization": auth_token}
            )

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["reddit_username"] == "MinimalAPIBot"
            assert data["display_name"] is None
            assert isinstance(data["config"], dict)

    @pytest.mark.anyio
    async def test_create_persona_duplicate_username(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test persona creation fails with duplicate username.

        Arrange: Create first persona, prepare duplicate request
        Act: POST same username again
        Assert: Returns 409 Conflict
        """
        # Arrange
        repo = PersonaRepository(async_session)
        await repo.create_persona(reddit_username="DuplicateAPIBot")
        await async_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "DuplicateAPIBot"
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data,
                headers={"Authorization": auth_token}
            )

            # Assert
            assert response.status_code == 409
            assert "already exists" in response.json()["detail"].lower()

    @pytest.mark.anyio
    async def test_create_persona_invalid_username_short(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test persona creation fails with username too short.

        Arrange: Prepare request with 2-char username (min is 3)
        Act: POST to /api/v1/personas
        Assert: Returns 422 Validation Error
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "ab"  # Too short (min 3)
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data,
                headers={"Authorization": auth_token}
            )

            # Assert
            assert response.status_code == 422
            errors = response.json()["detail"]
            assert any(
                "reddit_username" in str(error).lower()
                for error in errors
            )

    @pytest.mark.anyio
    async def test_create_persona_invalid_username_spaces(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test persona creation fails with spaces in username.

        Arrange: Prepare request with username containing spaces
        Act: POST to /api/v1/personas
        Assert: Returns 422 Validation Error
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "Invalid Bot"  # Has space
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data,
                headers={"Authorization": auth_token}
            )

            # Assert
            assert response.status_code == 422

    @pytest.mark.anyio
    async def test_create_persona_invalid_username_special_chars(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test persona creation fails with invalid special characters.

        Arrange: Prepare request with username containing @#$
        Act: POST to /api/v1/personas
        Assert: Returns 422 Validation Error
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "Invalid@Bot#"
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data,
                headers={"Authorization": auth_token}
            )

            # Assert
            assert response.status_code == 422

    @pytest.mark.anyio
    async def test_create_persona_unauthorized(
        self,
        async_session: AsyncSession
    ):
        """
        Test persona creation fails without authentication.

        Arrange: Prepare valid request without auth token
        Act: POST to /api/v1/personas
        Assert: Returns 403 Forbidden
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "UnauthorizedBot"
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data
                # No Authorization header
            )

            # Assert
            assert response.status_code == 403

    @pytest.mark.anyio
    async def test_create_persona_invalid_token(
        self,
        async_session: AsyncSession
    ):
        """
        Test persona creation fails with invalid token.

        Arrange: Prepare request with invalid/malformed token
        Act: POST to /api/v1/personas
        Assert: Returns 401 Unauthorized (credentials provided but invalid)
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "InvalidTokenBot"
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data,
                headers={"Authorization": "Bearer invalid_token_here"}
            )

            # Assert
            assert response.status_code == 401

    @pytest.mark.anyio
    async def test_create_persona_with_config(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test persona creation with custom config values.

        Arrange: Prepare request with full config object
        Act: POST to /api/v1/personas
        Assert: Returns 201 with config correctly stored
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            request_data = {
                "reddit_username": "ConfigBot",
                "config": {
                    "tone": "analytical",
                    "style": "detailed",
                    "core_values": [
                        "accuracy",
                        "clarity",
                        "evidence-based reasoning"
                    ],
                    "target_subreddits": ["science", "technology"]
                }
            }

            # Act
            response = await client.post(
                "/api/v1/personas",
                json=request_data,
                headers={"Authorization": auth_token}
            )

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["config"]["tone"] == "analytical"
            assert data["config"]["style"] == "detailed"
            assert len(data["config"]["core_values"]) == 3
            assert "accuracy" in data["config"]["core_values"]
            assert len(data["config"]["target_subreddits"]) == 2

    @pytest.mark.anyio
    async def test_create_persona_appears_in_list(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test newly created persona appears in persona list.

        Arrange: Create persona via API
        Act: GET /api/v1/personas to list all personas
        Assert: New persona appears in list
        """
        # Arrange & Act (Create)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post(
                "/api/v1/personas",
                json={"reddit_username": "ListTestBot"},
                headers={"Authorization": auth_token}
            )
            created_id = create_response.json()["id"]

            # Act (List)
            list_response = await client.get(
                "/api/v1/personas",
                headers={"Authorization": auth_token}
            )

            # Assert
            assert list_response.status_code == 200
            personas = list_response.json()
            assert any(p["id"] == created_id for p in personas)
            found_persona = next(p for p in personas if p["id"] == created_id)
            assert found_persona["reddit_username"] == "ListTestBot"


class TestPersonaAPIList:
    """
    Test suite for GET /api/v1/personas endpoint.

    Tests listing personas with authentication.
    """

    @pytest.mark.anyio
    async def test_list_personas_empty(
        self,
        async_session: AsyncSession,
        auth_token: str
    ):
        """
        Test listing personas when none exist.

        Arrange: Empty database
        Act: GET /api/v1/personas
        Assert: Returns empty list
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get(
                "/api/v1/personas",
                headers={"Authorization": auth_token}
            )

            # Assert
            assert response.status_code == 200
            assert response.json() == []

    @pytest.mark.anyio
    async def test_list_personas_unauthorized(
        self,
        async_session: AsyncSession
    ):
        """
        Test listing personas fails without authentication.

        Arrange: No auth token
        Act: GET /api/v1/personas
        Assert: Returns 403 Forbidden
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/personas")

            # Assert
            assert response.status_code == 403
