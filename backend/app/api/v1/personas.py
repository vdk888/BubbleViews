"""
Persona endpoints.

Provides a minimal listing endpoint to support dashboard persona selection
and to satisfy Phase 1/2 requirements for persona-scoped operations.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.persona import Persona
from app.schemas.persona import PersonaSummary

router = APIRouter()


@router.get(
    "/personas",
    response_model=List[PersonaSummary],
    summary="List personas",
    description="Returns basic persona information for dashboard selection.",
)
async def list_personas(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> List[PersonaSummary]:
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
