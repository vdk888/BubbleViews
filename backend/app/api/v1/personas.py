"""
Persona endpoints.

Provides endpoints for persona management including listing and creation
to support dashboard persona selection and multi-persona operations.
"""

from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import CurrentActiveUser, DatabaseSession
from app.core.security import User
from app.repositories.persona import PersonaRepository
from app.models.persona import Persona
from app.schemas.persona import (
    PersonaSummary,
    PersonaCreateRequest,
    PersonaCreateResponse
)

router = APIRouter(tags=["personas"])


def get_persona_repository(
    db: DatabaseSession
) -> PersonaRepository:
    """
    Dependency to inject PersonaRepository.

    Args:
        db: Database session from dependency injection

    Returns:
        PersonaRepository instance
    """
    return PersonaRepository(db)


PersonaRepo = Annotated[PersonaRepository, Depends(get_persona_repository)]


@router.get(
    "/personas",
    response_model=List[PersonaSummary],
    summary="List personas",
    description="Returns basic persona information for dashboard selection.",
)
async def list_personas(
    db: DatabaseSession,
    current_user: CurrentActiveUser,
) -> List[PersonaSummary]:
    """
    List all personas.

    Args:
        db: Database session (from dependency)
        current_user: Authenticated user (from dependency)

    Returns:
        List of persona summaries

    Raises:
        HTTPException 401: If not authenticated

    Security:
        - Requires valid JWT token
    """
    stmt = select(Persona)
    result = await db.execute(stmt)
    personas = result.scalars().all()
    return [
        PersonaSummary(
            id=p.id,
            reddit_username=p.reddit_username,
            display_name=p.display_name,
        )
        for p in personas
    ]


@router.get(
    "/personas/{persona_id}",
    response_model=PersonaCreateResponse,
    summary="Get persona by ID",
    description="Returns full persona details including configuration.",
)
async def get_persona(
    persona_id: str,
    db: DatabaseSession,
    current_user: CurrentActiveUser,
) -> PersonaCreateResponse:
    """
    Get a single persona by ID.

    Args:
        persona_id: UUID of the persona to retrieve
        db: Database session (from dependency)
        current_user: Authenticated user (from dependency)

    Returns:
        PersonaCreateResponse with full persona details

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If persona not found

    Security:
        - Requires valid JWT token
    """
    # Query persona
    stmt = select(Persona).where(Persona.id == persona_id)
    result = await db.execute(stmt)
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona not found: {persona_id}"
        )

    # Parse config from JSON
    config_dict = persona.get_config()

    # Convert created_at to ISO format string
    if persona.created_at:
        if isinstance(persona.created_at, str):
            created_at_str = persona.created_at
        else:
            created_at_str = persona.created_at.isoformat()
    else:
        created_at_str = ""

    return PersonaCreateResponse(
        id=persona.id,
        reddit_username=persona.reddit_username,
        display_name=persona.display_name,
        config=config_dict,
        created_at=created_at_str
    )


@router.post(
    "/personas",
    response_model=PersonaCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new persona",
    description="Create a new persona with Reddit username, display name, and configuration.",
)
async def create_persona(
    request: PersonaCreateRequest,
    current_user: CurrentActiveUser,
    repo: PersonaRepo
) -> PersonaCreateResponse:
    """
    Create a new persona.

    Args:
        request: Persona creation request with username, display name, config
        current_user: Authenticated user (from dependency)
        repo: PersonaRepository instance (from dependency)

    Returns:
        PersonaCreateResponse with created persona details

    Raises:
        HTTPException 400: If validation fails
        HTTPException 401: If not authenticated
        HTTPException 409: If reddit_username already exists

    Security:
        - Requires valid JWT token
        - Username uniqueness enforced at database level

    Note:
        Config is serialized to JSON and stored in the database.
        Default configuration is used if not provided.
    """
    try:
        # Create persona using repository
        persona = await repo.create_persona(
            reddit_username=request.reddit_username,
            display_name=request.display_name,
            config=request.config.model_dump() if request.config else None
        )

        # Parse config from JSON for response
        config_dict = persona.get_config()

        # Convert created_at to ISO format string
        if persona.created_at:
            if isinstance(persona.created_at, str):
                created_at_str = persona.created_at
            else:
                created_at_str = persona.created_at.isoformat()
        else:
            created_at_str = ""

        return PersonaCreateResponse(
            id=persona.id,
            reddit_username=persona.reddit_username,
            display_name=persona.display_name,
            config=config_dict,
            created_at=created_at_str
        )

    except ValueError as e:
        # Username conflict or validation error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create persona: {str(e)}"
        )
