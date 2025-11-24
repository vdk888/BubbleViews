"""
Integration tests for authentication flow.

Tests the complete authentication system end-to-end:
- Token issuance with valid credentials
- Token rejection with invalid credentials
- Protected endpoint access with valid token
- Protected endpoint rejection without token
- Protected endpoint rejection with expired token
- Token refresh (documented as not implemented)

Tests follow AAA (Arrange, Act, Assert) pattern.
"""

import pytest
from datetime import timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.base import Base
from app.models.user import Admin
from app.core.security import get_password_hash, create_access_token
from app.core.database import get_db


@pytest.fixture
async def async_session():
    """
    Create an in-memory database session for testing.

    Yields:
        AsyncSession for testing
    """
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
async def app_with_db(async_session: AsyncSession):
    """
    Override database dependency in app.

    Args:
        async_session: Database session fixture

    Returns:
        FastAPI app with overridden dependencies
    """
    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestTokenIssuance:
    """Integration tests for JWT token issuance."""

    async def test_valid_credentials_returns_token(self, app_with_db, test_admin):
        """
        Test that valid credentials return a JWT token.

        Arrange: Create test admin user
        Act: POST /auth/token with valid credentials
        Assert: Status 200, token returned with correct type
        """
        # Arrange - test_admin fixture creates user
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": "testadmin",
                    "password": "testpass123"
                }
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0

    async def test_invalid_username_returns_401(self, app_with_db, test_admin):
        """
        Test that invalid username returns 401.

        Arrange: Create test admin user
        Act: POST /auth/token with invalid username
        Assert: Status 401, error message returned
        """
        # Arrange - test_admin fixture creates user
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": "wronguser",
                    "password": "testpass123"
                }
            )

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Incorrect username or password"

    async def test_invalid_password_returns_401(self, app_with_db, test_admin):
        """
        Test that invalid password returns 401.

        Arrange: Create test admin user
        Act: POST /auth/token with invalid password
        Assert: Status 401, error message returned
        """
        # Arrange - test_admin fixture creates user
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": "testadmin",
                    "password": "wrongpassword"
                }
            )

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Incorrect username or password"

    async def test_missing_credentials_returns_422(self, app_with_db):
        """
        Test that missing credentials return 422 validation error.

        Arrange: None needed
        Act: POST /auth/token without credentials
        Assert: Status 422 (validation error)
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={}
            )

        # Assert
        assert response.status_code == 422  # Validation error

    async def test_token_has_correct_claims(self, app_with_db, test_admin):
        """
        Test that token has correct claims (username in sub).

        Arrange: Create test admin user
        Act: POST /auth/token with valid credentials
        Assert: Token can be decoded and has correct username in sub claim
        """
        # Arrange - test_admin fixture creates user
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": "testadmin",
                    "password": "testpass123"
                }
            )

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Decode token manually to verify claims
        from jose import jwt
        from app.core.config import settings

        token_data = jwt.decode(
            data["access_token"],
            settings.secret_key,
            algorithms=["HS256"]
        )
        assert token_data["sub"] == "testadmin"
        assert "exp" in token_data
        assert "iat" in token_data


@pytest.mark.asyncio
class TestProtectedEndpoints:
    """Integration tests for protected endpoint access."""

    async def test_protected_endpoint_with_valid_token(self, app_with_db, test_admin):
        """
        Test that protected endpoint allows access with valid token.

        Arrange: Create test admin user, get valid token
        Act: GET /protected/test with valid token
        Assert: Status 200, response contains username
        """
        # Arrange - Get valid token
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": "testadmin",
                    "password": "testpass123"
                }
            )
            token = token_response.json()["access_token"]

            # Act
            response = await client.get(
                "/api/v1/protected/test",
                headers={"Authorization": f"Bearer {token}"}
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "testadmin" in data["message"]

    async def test_protected_endpoint_without_token(self, app_with_db):
        """
        Test that protected endpoint rejects requests without token.

        Arrange: None needed
        Act: GET /protected/test without token
        Assert: Status 401 (Unauthorized)
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/protected/test")

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_protected_endpoint_with_invalid_token(self, app_with_db):
        """
        Test that protected endpoint rejects requests with invalid token.

        Arrange: None needed
        Act: GET /protected/test with malformed token
        Assert: Status 401 (Unauthorized)
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.get(
                "/api/v1/protected/test",
                headers={"Authorization": "Bearer invalid_token_here"}
            )

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_protected_endpoint_with_expired_token(self, app_with_db, test_admin):
        """
        Test that protected endpoint rejects expired token.

        Arrange: Create test admin user, create expired token
        Act: GET /protected/test with expired token
        Assert: Status 401 (Unauthorized)
        """
        # Arrange - Create expired token (expiry in the past)
        expired_token = create_access_token(
            data={"sub": "testadmin"},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )

        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.get(
                "/api/v1/protected/test",
                headers={"Authorization": f"Bearer {expired_token}"}
            )

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    async def test_protected_endpoint_with_wrong_scheme(self, app_with_db, test_admin):
        """
        Test that protected endpoint rejects token with wrong auth scheme.

        Arrange: Create test admin user, get valid token
        Act: GET /protected/test with token using wrong scheme (not Bearer)
        Assert: Status 401 (Unauthorized)
        """
        # Arrange - Get valid token
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": "testadmin",
                    "password": "testpass123"
                }
            )
            token = token_response.json()["access_token"]

            # Act - Use wrong auth scheme
            response = await client.get(
                "/api/v1/protected/test",
                headers={"Authorization": f"Basic {token}"}
            )

        # Assert
        assert response.status_code == 401


@pytest.mark.asyncio
class TestTokenRefresh:
    """Tests for token refresh functionality (not yet implemented)."""

    async def test_token_refresh_not_implemented(self, app_with_db):
        """
        Test that token refresh is not yet implemented.

        This test documents that token refresh functionality is planned
        but not yet implemented in the MVP. Currently, users must
        re-authenticate when their token expires.

        Future implementation should:
        - Add POST /api/v1/auth/refresh endpoint
        - Accept refresh token in request body
        - Return new access token with extended expiry
        - Implement refresh token rotation for security

        Arrange: None needed
        Act: POST /api/v1/auth/refresh (endpoint doesn't exist yet)
        Assert: Status 404 (Not Found)
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "placeholder"}
            )

        # Assert
        assert response.status_code == 404  # Endpoint not yet implemented


@pytest.mark.asyncio
class TestCurrentUser:
    """Integration tests for current user endpoint."""

    async def test_get_current_user_with_valid_token(self, app_with_db, test_admin):
        """
        Test that /auth/me returns current user info with valid token.

        Arrange: Create test admin user, get valid token
        Act: GET /auth/me with valid token
        Assert: Status 200, returns username and full_name
        """
        # Arrange - Get valid token
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": "testadmin",
                    "password": "testpass123"
                }
            )
            token = token_response.json()["access_token"]

            # Act
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testadmin"
        assert "full_name" in data

    async def test_get_current_user_without_token(self, app_with_db):
        """
        Test that /auth/me rejects requests without token.

        Arrange: None needed
        Act: GET /auth/me without token
        Assert: Status 401 (Unauthorized)
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/auth/me")

        # Assert
        assert response.status_code == 401
