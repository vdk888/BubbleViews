"""
FastAPI dependency functions.

Provides reusable dependency injection functions for FastAPI routes,
including authentication, database sessions, and request validation.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token, get_user, User


# HTTP Bearer token scheme
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.

    Extracts and validates the JWT token from the Authorization header,
    then returns the authenticated user. This dependency should be used
    on all protected routes that require authentication.

    Args:
        credentials: HTTP Bearer credentials from Authorization header

    Returns:
        User object for the authenticated user

    Raises:
        HTTPException 401: If token is missing, invalid, expired, or user not found

    Example:
        @router.get("/protected")
        async def protected_route(
            current_user: Annotated[User, Depends(get_current_user)]
        ):
            return {"message": f"Hello {current_user.username}"}

    Security:
        - Validates JWT signature using SECRET_KEY
        - Checks token expiration
        - Verifies user exists in database
        - Returns 401 with WWW-Authenticate header on any failure

    Note:
        The token should be sent in the Authorization header as:
        Authorization: Bearer <token>
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Extract token from credentials
    token = credentials.credentials

    # Decode and validate token
    token_data = decode_access_token(token)

    if token_data is None or token_data.username is None:
        raise credentials_exception

    # Get user from database
    user = await get_user(username=token_data.username)

    if user is None:
        raise credentials_exception

    # Return User object (without password hash)
    return User(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled
    )


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Dependency to get the current active (non-disabled) user.

    Extends get_current_user to also check if the user account is active.
    Use this dependency for routes that should be inaccessible to disabled users.

    Args:
        current_user: Current authenticated user (from get_current_user)

    Returns:
        User object if account is active

    Raises:
        HTTPException 400: If user account is disabled

    Example:
        @router.delete("/admin/delete-data")
        async def delete_data(
            current_user: Annotated[User, Depends(get_current_active_user)]
        ):
            # Only active users can access this
            ...

    Note:
        For MVP, all admin users are active. This dependency is included
        for future extensibility (e.g., temporary account suspension).
    """
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )

    return current_user


# Type alias for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
