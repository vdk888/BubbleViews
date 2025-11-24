"""
Security module for authentication and authorization.

Provides JWT token handling, password hashing, and authentication utilities
using industry-standard libraries (passlib, python-jose).
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.core.config import settings

# HTTP Bearer token scheme for FastAPI
security = HTTPBearer()

# JWT Algorithm
ALGORITHM = "HS256"


class TokenData(BaseModel):
    """
    JWT token payload data model.

    Contains the claims stored in the JWT token.
    """
    username: str
    exp: Optional[datetime] = None


class User(BaseModel):
    """
    Simple user model for admin authentication.

    For MVP, we use a single admin user. In production, this would
    be stored in the database with proper user management.
    """
    username: str
    full_name: Optional[str] = None
    disabled: bool = False


class UserInDB(User):
    """
    User model with hashed password for storage.

    Never expose this model through the API - use User instead.
    """
    hashed_password: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: The plain text password to verify
        hashed_password: The hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    # Encode the password to bytes
    password_bytes = plain_password.encode('utf-8')
    # Truncate to 72 bytes if needed (bcrypt limit)
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]

    # Encode the hash to bytes if it's a string
    if isinstance(hashed_password, str):
        hashed_bytes = hashed_password.encode('utf-8')
    else:
        hashed_bytes = hashed_password

    return bcrypt.checkpw(password_bytes, hashed_bytes)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string

    Note:
        Bcrypt has a 72-byte password limit. Passwords are automatically
        truncated if necessary (unlikely for typical passwords).
    """
    # Encode the password to bytes
    password_bytes = password.encode('utf-8')
    # Truncate to 72 bytes if needed (bcrypt limit)
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]

    # Generate salt and hash
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)

    # Return as string for storage
    return hashed.decode('utf-8')


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary of claims to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token({"sub": "admin"})
        >>> # Use token in Authorization header: Bearer <token>
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=ALGORITHM
    )

    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT access token.

    Args:
        token: JWT token string to decode

    Returns:
        TokenData if valid, None if invalid or expired

    Raises:
        JWTError: If token is malformed or signature is invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM]
        )
        username: str = payload.get("sub")

        if username is None:
            return None

        return TokenData(username=username, exp=payload.get("exp"))

    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency function to get the current authenticated user.

    Validates the JWT token from the Authorization header and returns
    the authenticated user. Use this as a dependency in protected routes.

    Args:
        credentials: HTTP Bearer credentials from request header

    Returns:
        Authenticated User object

    Raises:
        HTTPException: 401 if token is invalid or user not found

    Example:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"message": f"Hello {user.username}"}
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    token_data = decode_access_token(token)

    if token_data is None or token_data.username is None:
        raise credentials_exception

    # For MVP, we use a simple hardcoded admin user
    # In production, fetch user from database
    user = await get_user(username=token_data.username)

    if user is None:
        raise credentials_exception

    return user


async def get_user(username: str) -> Optional[UserInDB]:
    """
    Retrieve user from database.

    Queries the Admin table to find the user by username.

    Args:
        username: Username to look up

    Returns:
        UserInDB if found, None otherwise
    """
    from sqlalchemy import select
    from app.core.database import get_session
    from app.models.user import Admin

    async for session in get_session():
        try:
            result = await session.execute(
                select(Admin).where(Admin.username == username)
            )
            admin = result.scalar_one_or_none()

            if admin:
                return UserInDB(
                    username=admin.username,
                    full_name="Admin User",
                    disabled=False,
                    hashed_password=admin.hashed_password
                )

            return None
        finally:
            await session.close()


async def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Authenticate a user with username and password.

    Args:
        username: Username to authenticate
        password: Plain text password

    Returns:
        User if authentication successful, None otherwise

    Example:
        user = await authenticate_user("admin", "password")
        if user:
            token = create_access_token({"sub": user.username})
    """
    user = await get_user(username)

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if user.disabled:
        return None

    # Return User without password hash
    return User(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled
    )


class Token(BaseModel):
    """
    Access token response model.

    Returned by the login endpoint after successful authentication.
    """
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")


class LoginRequest(BaseModel):
    """
    Login request model.

    Used for username/password authentication.
    """
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
