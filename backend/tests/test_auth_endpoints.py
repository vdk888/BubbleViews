"""
Integration tests for authentication endpoints.

Tests cover:
- POST /api/v1/auth/token (login)
- GET /api/v1/auth/me (current user)
- GET /api/v1/protected/test (protected endpoint)
- GET /api/v1/protected/user-info (detailed user info)
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.core.security import get_password_hash
from app.models.user import Admin


@pytest.fixture
async def test_admin():
    """Create a test admin user for authentication tests."""
    async with async_session_maker() as session:
        # Clean up any existing test admin
        result = await session.execute(
            select(Admin).where(Admin.username == "testadmin")
        )
        existing = result.scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()

        # Create test admin
        admin = Admin(
            username="testadmin",
            hashed_password=get_password_hash("testpassword123")
        )
        session.add(admin)
        await session.commit()

        # Refresh to get the created admin with ID
        await session.refresh(admin)
        admin_data = {
            "username": admin.username,
            "password": "testpassword123"
        }

    yield admin_data

    # Cleanup
    async with async_session_maker() as session:
        result = await session.execute(
            select(Admin).where(Admin.username == "testadmin")
        )
        admin = result.scalar_one_or_none()
        if admin:
            await session.delete(admin)
            await session.commit()


@pytest.fixture
async def auth_token(test_admin):
    """Get an authentication token for tests."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/token",
            data={
                "username": test_admin["username"],
                "password": test_admin["password"]
            }
        )
        assert response.status_code == 200
        token_data = response.json()
        return token_data["access_token"]


@pytest.mark.asyncio
class TestAuthEndpoints:
    """Test authentication endpoints."""

    async def test_login_success(self, test_admin):
        """Test successful login returns JWT token."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": test_admin["username"],
                    "password": test_admin["password"]
                }
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    async def test_login_wrong_password(self, test_admin):
        """Test login with wrong password returns 401."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": test_admin["username"],
                    "password": "wrong_password"
                }
            )

        # Assert
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "username or password" in data["detail"].lower()

    async def test_login_nonexistent_user(self):
        """Test login with non-existent user returns 401."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": "nonexistent",
                    "password": "any_password"
                }
            )

        # Assert
        assert response.status_code == 401

    async def test_login_missing_username(self):
        """Test login without username returns 422."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={"password": "test"}
            )

        # Assert
        assert response.status_code == 422  # Validation error

    async def test_login_missing_password(self):
        """Test login without password returns 422."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.post(
                "/api/v1/auth/token",
                data={"username": "test"}
            )

        # Assert
        assert response.status_code == 422  # Validation error

    async def test_get_current_user_me(self, auth_token):
        """Test /auth/me endpoint returns current user."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {auth_token}"}
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "username" in data
        assert data["username"] == "testadmin"
        assert "full_name" in data

    async def test_get_current_user_me_no_token(self):
        """Test /auth/me without token returns 403."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/auth/me")

        # Assert
        assert response.status_code == 403  # Forbidden (no token)

    async def test_get_current_user_me_invalid_token(self):
        """Test /auth/me with invalid token returns 401."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid_token"}
            )

        # Assert
        assert response.status_code == 401


@pytest.mark.asyncio
class TestProtectedEndpoints:
    """Test protected endpoints requiring authentication."""

    async def test_protected_test_endpoint_with_token(self, auth_token):
        """Test protected endpoint with valid token."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.get(
                "/api/v1/protected/test",
                headers={"Authorization": f"Bearer {auth_token}"}
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "testadmin" in data["message"]
        assert "username" in data
        assert data["username"] == "testadmin"
        assert data["authenticated"] is True

    async def test_protected_test_endpoint_without_token(self):
        """Test protected endpoint without token returns 403."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/protected/test")

        # Assert
        assert response.status_code == 403

    async def test_protected_test_endpoint_invalid_token(self):
        """Test protected endpoint with invalid token returns 401."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.get(
                "/api/v1/protected/test",
                headers={"Authorization": "Bearer invalid_token"}
            )

        # Assert
        assert response.status_code == 401

    async def test_protected_user_info_endpoint(self, auth_token):
        """Test /protected/user-info endpoint."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act
            response = await client.get(
                "/api/v1/protected/user-info",
                headers={"Authorization": f"Bearer {auth_token}"}
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testadmin"
        assert "full_name" in data
        assert "disabled" in data
        assert data["disabled"] is False
        assert data["account_type"] == "admin"

    async def test_token_in_different_formats(self, auth_token):
        """Test that only Bearer token format is accepted."""
        # Arrange
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Act - without "Bearer" prefix
            response = await client.get(
                "/api/v1/protected/test",
                headers={"Authorization": auth_token}
            )

        # Assert
        # Should fail because HTTPBearer expects "Bearer " prefix
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
class TestAuthenticationFlow:
    """Test complete authentication flow."""

    async def test_complete_auth_flow(self, test_admin):
        """Test complete authentication flow: login -> access protected endpoint."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Step 1: Login
            login_response = await client.post(
                "/api/v1/auth/token",
                data={
                    "username": test_admin["username"],
                    "password": test_admin["password"]
                }
            )
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]

            # Step 2: Access /auth/me
            me_response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert me_response.status_code == 200
            assert me_response.json()["username"] == test_admin["username"]

            # Step 3: Access protected endpoint
            protected_response = await client.get(
                "/api/v1/protected/test",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert protected_response.status_code == 200
            assert protected_response.json()["authenticated"] is True

            # Step 4: Access user info
            info_response = await client.get(
                "/api/v1/protected/user-info",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert info_response.status_code == 200
            assert info_response.json()["username"] == test_admin["username"]
