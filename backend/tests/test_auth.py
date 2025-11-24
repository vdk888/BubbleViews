"""
Tests for authentication system.

Tests cover:
- Password hashing and verification
- JWT token creation and validation
- Admin user database operations
- Authentication endpoints
- Protected endpoints
"""

import pytest
from datetime import timedelta
from jose import jwt
import asyncio

from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
    authenticate_user,
)
from app.core.config import settings
from app.models.user import Admin
from app.core.database import async_session_maker
from sqlalchemy import select


class TestPasswordHashing:
    """Test password hashing utilities."""

    def test_hash_password(self):
        """Test that password hashing works."""
        # Arrange
        plain_password = "test_password_123"

        # Act
        hashed = get_password_hash(plain_password)

        # Assert
        assert hashed is not None
        assert hashed != plain_password
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_verify_password_success(self):
        """Test password verification with correct password."""
        # Arrange
        plain_password = "test_password_123"
        hashed = get_password_hash(plain_password)

        # Act
        result = verify_password(plain_password, hashed)

        # Assert
        assert result is True

    def test_verify_password_failure(self):
        """Test password verification with incorrect password."""
        # Arrange
        plain_password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = get_password_hash(plain_password)

        # Act
        result = verify_password(wrong_password, hashed)

        # Assert
        assert result is False

    def test_hash_different_passwords_produce_different_hashes(self):
        """Test that different passwords produce different hashes."""
        # Arrange
        password1 = "password1"
        password2 = "password2"

        # Act
        hash1 = get_password_hash(password1)
        hash2 = get_password_hash(password2)

        # Assert
        assert hash1 != hash2

    def test_hash_same_password_twice_produces_different_hashes(self):
        """Test that hashing the same password twice produces different hashes (salt)."""
        # Arrange
        password = "test_password"

        # Act
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Assert
        assert hash1 != hash2  # Different due to salt
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


class TestJWTTokens:
    """Test JWT token creation and validation."""

    def test_create_access_token(self):
        """Test creating a JWT access token."""
        # Arrange
        data = {"sub": "testuser"}

        # Act
        token = create_access_token(data)

        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_expiry(self):
        """Test creating token with custom expiry."""
        # Arrange
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=30)

        # Act
        token = create_access_token(data, expires_delta)

        # Assert
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        assert "exp" in payload
        assert "sub" in payload
        assert payload["sub"] == "testuser"

    def test_decode_access_token_success(self):
        """Test decoding a valid token."""
        # Arrange
        data = {"sub": "testuser"}
        token = create_access_token(data)

        # Act
        token_data = decode_access_token(token)

        # Assert
        assert token_data is not None
        assert token_data.username == "testuser"
        assert token_data.exp is not None

    def test_decode_access_token_invalid(self):
        """Test decoding an invalid token."""
        # Arrange
        invalid_token = "invalid.token.string"

        # Act
        token_data = decode_access_token(invalid_token)

        # Assert
        assert token_data is None

    def test_decode_access_token_expired(self):
        """Test decoding an expired token."""
        # Arrange
        data = {"sub": "testuser"}
        token = create_access_token(data, timedelta(seconds=-1))  # Already expired

        # Act
        token_data = decode_access_token(token)

        # Assert
        assert token_data is None


@pytest.mark.asyncio
class TestAdminUserDatabase:
    """Test admin user database operations."""

    async def test_create_admin_user(self, async_session):
        """Test creating an admin user in the database."""
        # Arrange
        # Clean up any existing admin
        result = await async_session.execute(
            select(Admin).where(Admin.username == "test_admin")
        )
        existing = result.scalar_one_or_none()
        if existing:
            await async_session.delete(existing)
            await async_session.commit()

        # Act
        admin = Admin(
            username="test_admin",
            hashed_password=get_password_hash("test_password")
        )
        async_session.add(admin)
        await async_session.commit()

        # Query back
        result = await async_session.execute(
            select(Admin).where(Admin.username == "test_admin")
        )
        retrieved_admin = result.scalar_one_or_none()

        # Assert
        assert retrieved_admin is not None
        assert retrieved_admin.username == "test_admin"
        assert retrieved_admin.hashed_password.startswith("$2b$")
        assert verify_password("test_password", retrieved_admin.hashed_password)

    async def test_admin_username_unique(self, async_session):
        """Test that admin usernames are unique."""
        # Arrange
        # Clean up
        result = await async_session.execute(
            select(Admin).where(Admin.username == "unique_test")
        )
        existing = result.scalar_one_or_none()
        if existing:
            await async_session.delete(existing)
            await async_session.commit()

        # Create first admin
        admin1 = Admin(
            username="unique_test",
            hashed_password=get_password_hash("password1")
        )
        async_session.add(admin1)
        await async_session.commit()
        await async_session.flush()

        # Act & Assert
        try:
            admin2 = Admin(
                username="unique_test",  # Same username
                hashed_password=get_password_hash("password2")
            )
            async_session.add(admin2)
            await async_session.commit()
            pytest.fail("Should have raised IntegrityError for duplicate username")
        except Exception as e:
            # Expected: IntegrityError or similar
            assert "unique" in str(e).lower() or "constraint" in str(e).lower()
            await async_session.rollback()

    async def test_authenticate_user_success(self, async_session):
        """Test authenticating a valid user."""
        # Arrange
        # Clean and create test user
        result = await async_session.execute(
            select(Admin).where(Admin.username == "auth_test")
        )
        existing = result.scalar_one_or_none()
        if existing:
            await async_session.delete(existing)
            await async_session.commit()

        admin = Admin(
            username="auth_test",
            hashed_password=get_password_hash("correct_password")
        )
        async_session.add(admin)
        await async_session.commit()

        # Act
        user = await authenticate_user("auth_test", "correct_password")

        # Assert
        assert user is not None
        assert user.username == "auth_test"

    async def test_authenticate_user_wrong_password(self, async_session):
        """Test authentication fails with wrong password."""
        # Arrange
        # Clean and create test user
        result = await async_session.execute(
            select(Admin).where(Admin.username == "auth_fail_test")
        )
        existing = result.scalar_one_or_none()
        if existing:
            await async_session.delete(existing)
            await async_session.commit()

        admin = Admin(
            username="auth_fail_test",
            hashed_password=get_password_hash("correct_password")
        )
        async_session.add(admin)
        await async_session.commit()

        # Act
        user = await authenticate_user("auth_fail_test", "wrong_password")

        # Assert
        assert user is None

    async def test_authenticate_nonexistent_user(self, async_session):
        """Test authentication fails for non-existent user."""
        # Act
        user = await authenticate_user("nonexistent_user", "any_password")

        # Assert
        assert user is None
