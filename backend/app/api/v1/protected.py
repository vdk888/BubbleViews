"""
Protected endpoints for testing authentication.

Demonstrates how to use authentication dependencies on protected routes.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, CurrentUser
from app.core.security import User


# Create router for protected test endpoints
router = APIRouter()


@router.get("/test")
async def protected_test(
    current_user: CurrentUser,
) -> dict:
    """
    Protected test endpoint requiring authentication.

    This endpoint demonstrates authentication dependency injection.
    It requires a valid JWT token in the Authorization header.

    Args:
        current_user: Authenticated user (injected via dependency)

    Returns:
        Dictionary with welcome message and user info

    Example:
        GET /api/v1/protected/test
        Authorization: Bearer eyJ...

        Response:
        {
            "message": "Hello admin",
            "username": "admin",
            "authenticated": true
        }

    Security:
        - Requires valid JWT token
        - Returns 401 if token is missing, invalid, or expired
        - Token must be sent in Authorization header as: Bearer <token>

    Note:
        This is a demonstration endpoint. In production, protected endpoints
        would perform actual business logic (e.g., managing personas,
        updating beliefs, moderating posts).
    """
    return {
        "message": f"Hello {current_user.username}",
        "username": current_user.username,
        "authenticated": True,
    }


@router.get("/user-info")
async def get_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Get detailed information about the authenticated user.

    Returns comprehensive user information for the currently authenticated user.
    Demonstrates accessing user attributes from the dependency.

    Args:
        current_user: Authenticated user (injected via dependency)

    Returns:
        Dictionary with detailed user information

    Example:
        GET /api/v1/protected/user-info
        Authorization: Bearer eyJ...

        Response:
        {
            "username": "admin",
            "full_name": "Admin User",
            "disabled": false,
            "account_type": "admin"
        }

    Security:
        - Requires valid JWT token
        - Only returns information for the authenticated user
        - Password hash is never exposed
    """
    return {
        "username": current_user.username,
        "full_name": current_user.full_name,
        "disabled": current_user.disabled,
        "account_type": "admin",  # For MVP, all users are admins
    }
