"""
Authentication endpoints for admin login.

Provides JWT token issuance for admin dashboard access.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    authenticate_user,
    create_access_token,
    Token,
    User,
)

# Create router for authentication endpoints
router = APIRouter()


@router.post("/token", response_model=Token, status_code=status.HTTP_200_OK)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    OAuth2 compatible token login endpoint.

    Authenticates admin user with username and password, returns JWT access token.

    Args:
        form_data: OAuth2 form with username and password
        db: Database session (injected)

    Returns:
        Token with access_token and token_type

    Raises:
        HTTPException 401: If credentials are invalid

    Example:
        POST /api/v1/auth/token
        Content-Type: application/x-www-form-urlencoded

        username=admin&password=changeme123

        Response:
        {
            "access_token": "eyJ...",
            "token_type": "bearer"
        }

    Security:
        - Credentials are validated against database (bcrypt hash comparison)
        - Generic error message on failure (don't reveal if username exists)
        - Rate limiting should be applied to this endpoint (Task 4.1)
        - Consider adding login attempt tracking and account lockout

    Note:
        This endpoint uses OAuth2PasswordRequestForm for compatibility with
        OpenAPI docs and standard OAuth2 clients. The form fields are:
        - username: Admin username
        - password: Admin password (plaintext, validated against bcrypt hash)
    """
    # Authenticate user
    user = await authenticate_user(form_data.username, form_data.password)

    if not user:
        # Generic error message - don't reveal if username exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )

    return Token(access_token=access_token, token_type="bearer")


@router.get("/me")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)]
) -> dict:
    """
    Get current authenticated user information.

    Protected endpoint that returns the current user's details.
    Requires valid JWT token in Authorization header.

    Args:
        current_user: Current user (injected from JWT token)

    Returns:
        Dictionary with user information

    Example:
        GET /api/v1/auth/me
        Authorization: Bearer eyJ...

        Response:
        {
            "username": "admin",
            "full_name": "Admin User"
        }

    Security:
        - Requires valid JWT token
        - Returns 401 if token is missing, expired, or invalid
    """
    return {
        "username": current_user.username,
        "full_name": current_user.full_name,
    }
