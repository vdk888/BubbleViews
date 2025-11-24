"""
Lightweight stats endpoints.
"""

from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.interaction import Interaction
from app.models.pending_post import PendingPost
from app.models.belief import BeliefUpdate
from app.schemas.stats import StatsResponse

router = APIRouter()


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Basic stats",
    description="Returns counts for interactions, pending queue, and belief updates.",
)
async def get_stats(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> StatsResponse:
    counts: Dict[str, int] = {}

    # interactions count
    result = await db.execute(
        select(func.count()).select_from(Interaction).where(Interaction.persona_id == persona_id)
    )
    counts["interactions"] = result.scalar_one()

    # pending posts count
    result = await db.execute(
        select(func.count())
        .select_from(PendingPost)
        .where(PendingPost.persona_id == persona_id, PendingPost.status == "pending")
    )
    counts["pending_posts"] = result.scalar_one()

    # belief updates
    result = await db.execute(
        select(func.count()).select_from(BeliefUpdate).where(BeliefUpdate.persona_id == persona_id)
    )
    counts["belief_updates"] = result.scalar_one()

    return StatsResponse(**counts)
