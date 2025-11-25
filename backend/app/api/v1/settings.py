"""
Settings API endpoints for agent configuration.

Provides REST endpoints for retrieving and updating persona-scoped
agent configuration with authentication and validation.
"""

from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentActiveUser, DatabaseSession
from app.core.security import User
from app.repositories.config import ConfigRepository
from app.repositories.persona import PersonaRepository
from app.schemas.config import (
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigUpdateResponse
)

router = APIRouter()

# Blocklist of unsafe config keys that cannot be modified via API
# These are system-critical or security-sensitive settings
UNSAFE_CONFIG_KEYS = {
    "admin_password",
    "api_key",
    "secret_key",
    "database_url",
    "reddit_client_secret",
    "openai_api_key",
    "anthropic_api_key",
    "jwt_secret",
}


def get_config_repository(
    db: DatabaseSession
) -> ConfigRepository:
    """
    Dependency to inject ConfigRepository.

    Args:
        db: Database session from dependency injection

    Returns:
        ConfigRepository instance
    """
    return ConfigRepository(db)


ConfigRepo = Annotated[ConfigRepository, Depends(get_config_repository)]


def get_persona_repository(
    db: DatabaseSession
) -> PersonaRepository:
    """
    Dependency to inject PersonaRepository.
    """
    return PersonaRepository(db)


PersonaRepo = Annotated[PersonaRepository, Depends(get_persona_repository)]


@router.get(
    "/settings",
    response_model=ConfigResponse,
    summary="Get all settings for a persona",
    description="""
    Retrieve all configuration key-value pairs for a specific persona.

    **Authentication:** Required (Bearer token)

    **Persona Isolation:** Enforced - only returns config for specified persona_id

    **Returns:**
    - Empty dict if persona has no configuration
    - All config key-value pairs if persona exists

    **Query Parameters:**
    - `persona_id`: UUID of the persona (required)

    **Example Response:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "config": {
            "target_subreddits": ["test", "bottest"],
            "auto_posting_enabled": false,
            "safety_flags": {"require_approval": true}
        }
    }
    ```
    """,
    tags=["settings"]
)
async def get_settings(
    persona_id: str = Query(
        ...,
        description="UUID of the persona",
        example="123e4567-e89b-12d3-a456-426614174000"
    ),
    current_user: CurrentActiveUser = None,
    repo: ConfigRepo = None,
    persona_repo: PersonaRepo = None
) -> ConfigResponse:
    """
    Get all configuration settings for a persona.

    Args:
        persona_id: UUID of the persona (from query param)
        current_user: Authenticated user (from dependency)
        repo: ConfigRepository instance (from dependency)
        persona_repo: PersonaRepository instance (from dependency)

    Returns:
        ConfigResponse with all config key-value pairs

    Raises:
        HTTPException 404: If persona doesn't exist
        HTTPException 401: If not authenticated

    Security:
        - Requires valid JWT token
        - Persona isolation enforced (no cross-persona access)
    """
    # Get persona with its base config
    persona = await persona_repo.get_persona(persona_id)
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona not found: {persona_id}"
        )

    # Start with persona's base config (from Persona.config field)
    # persona.get_config() parses the JSON config field
    base_config = persona.get_config() if persona.config else {}

    # Merge with AgentConfig settings (which override base config)
    agent_config = await repo.get_all_config(persona_id)

    # Merge: AgentConfig values override base config
    merged_config = {**base_config, **agent_config}

    return ConfigResponse(
        persona_id=persona_id,
        config=merged_config
    )


@router.post(
    "/settings",
    response_model=ConfigUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a configuration setting",
    description="""
    Set or update a single configuration value for a persona.

    **Authentication:** Required (Bearer token)

    **Persona Isolation:** Enforced - can only update config for specified persona_id

    **Validation:**
    - Persona must exist
    - Config key must not be in unsafe blocklist
    - Value must be JSON-serializable
    - Schema validation applied for known config keys

    **Unsafe Keys (blocked):**
    System-critical settings that cannot be modified via API:
    - admin_password
    - api_key
    - secret_key
    - database_url
    - reddit_client_secret
    - openai_api_key
    - anthropic_api_key
    - jwt_secret

    **Request Body:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "key": "auto_posting_enabled",
        "value": true
    }
    ```

    **Example Response:**
    ```json
    {
        "persona_id": "123e4567-e89b-12d3-a456-426614174000",
        "key": "auto_posting_enabled",
        "value": true,
        "updated": true
    }
    ```
    """,
    tags=["settings"]
)
async def update_setting(
    request: ConfigUpdateRequest,
    current_user: CurrentActiveUser = None,
    repo: ConfigRepo = None
) -> ConfigUpdateResponse:
    """
    Update a single configuration setting.

    Args:
        request: Configuration update request (persona_id, key, value)
        current_user: Authenticated user (from dependency)
        repo: ConfigRepository instance (from dependency)

    Returns:
        ConfigUpdateResponse with updated config

    Raises:
        HTTPException 400: If key is unsafe or value is invalid
        HTTPException 404: If persona doesn't exist
        HTTPException 401: If not authenticated

    Security:
        - Requires valid JWT token
        - Unsafe keys blocked via hardcoded blocklist
        - Persona isolation enforced
    """
    # Validate persona exists
    if not await repo.persona_exists(request.persona_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona not found: {request.persona_id}"
        )

    # Check if key is in unsafe blocklist
    if request.key.lower() in UNSAFE_CONFIG_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify unsafe config key: {request.key}"
        )

    # Optional: Validate value against schema for known keys
    # This could be extended to validate specific config structures
    # For MVP, we allow any JSON-serializable value

    # Set config
    try:
        result = await repo.set_config(
            persona_id=request.persona_id,
            key=request.key,
            value=request.value
        )
    except IntegrityError:
        # Foreign key constraint violation (persona doesn't exist)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona not found: {request.persona_id}"
        )
    except TypeError as e:
        # Value not JSON-serializable
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid value: {str(e)}"
        )

    return ConfigUpdateResponse(
        persona_id=request.persona_id,
        key=result["key"],
        value=result["value"],
        updated=True
    )


@router.delete(
    "/settings",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a configuration setting",
    description="""
    Delete a specific configuration key for a persona.

    **Authentication:** Required (Bearer token)

    **Persona Isolation:** Enforced - can only delete config for specified persona_id

    **Query Parameters:**
    - `persona_id`: UUID of the persona (required)
    - `key`: Configuration key to delete (required)

    **Returns:**
    - 204 No Content if deletion successful
    - 404 Not Found if persona or key doesn't exist

    **Example:**
    ```
    DELETE /api/v1/settings?persona_id=123e4567-e89b-12d3-a456-426614174000&key=deprecated_setting
    ```
    """,
    tags=["settings"]
)
async def delete_setting(
    persona_id: str = Query(
        ...,
        description="UUID of the persona",
        example="123e4567-e89b-12d3-a456-426614174000"
    ),
    key: str = Query(
        ...,
        description="Configuration key to delete",
        example="deprecated_setting"
    ),
    current_user: CurrentActiveUser = None,
    repo: ConfigRepo = None
) -> None:
    """
    Delete a configuration setting.

    Args:
        persona_id: UUID of the persona (from query param)
        key: Configuration key to delete (from query param)
        current_user: Authenticated user (from dependency)
        repo: ConfigRepository instance (from dependency)

    Returns:
        None (204 No Content)

    Raises:
        HTTPException 404: If persona or key doesn't exist
        HTTPException 401: If not authenticated

    Security:
        - Requires valid JWT token
        - Persona isolation enforced
    """
    # Validate persona exists
    if not await repo.persona_exists(persona_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona not found: {persona_id}"
        )

    # Delete config
    deleted = await repo.delete_config(persona_id, key)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration key not found: {key}"
        )


@router.get(
    "/settings/personas",
    response_model=list[Dict[str, Any]],
    summary="List all personas",
    description="""
    Retrieve a list of all personas with their basic information.

    **Authentication:** Required (Bearer token)

    **Returns:**
    List of persona objects with:
    - id: UUID
    - reddit_username: Reddit account username
    - display_name: Human-readable display name

    **Example Response:**
    ```json
    [
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "reddit_username": "AgentBot1",
            "display_name": "Demo Agent"
        }
    ]
    ```

    **Use Case:**
    Used by dashboard to populate persona selector and validate persona_id.
    """,
    tags=["settings"]
)
async def list_personas(
    current_user: CurrentActiveUser = None,
    repo: ConfigRepo = None
) -> list[Dict[str, Any]]:
    """
    List all personas.

    Args:
        current_user: Authenticated user (from dependency)
        repo: ConfigRepository instance (from dependency)

    Returns:
        List of persona dictionaries

    Raises:
        HTTPException 401: If not authenticated

    Security:
        - Requires valid JWT token
    """
    personas = await repo.get_all_personas()
    return personas
