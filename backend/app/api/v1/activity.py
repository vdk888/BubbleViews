"""
Activity feed endpoints.

Provides paginated access to interaction history for the dashboard.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.interaction import Interaction
from app.schemas.activity import ActivityItem

router = APIRouter()


@router.get(
    "/activity",
    response_model=List[ActivityItem],
    summary="Recent activity",
    description="Returns recent interactions for the specified persona.",
)
async def list_activity(
    persona_id: str,
    limit: int = Query(20, ge=1, le=100),
    since: Optional[datetime] = None,
    subreddit: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> List[ActivityItem]:
    stmt = select(Interaction).where(Interaction.persona_id == persona_id)

    if since:
        stmt = stmt.where(Interaction.created_at >= since.isoformat())

    if subreddit:
        stmt = stmt.where(Interaction.subreddit == subreddit)

    stmt = stmt.order_by(desc(Interaction.created_at)).limit(limit)

    result = await db.execute(stmt)
    interactions = result.scalars().all()

    return [
        ActivityItem(
            id=i.id,
            content=i.content,
            interaction_type=i.interaction_type,
            reddit_id=i.reddit_id,
            subreddit=i.subreddit,
            parent_id=i.parent_id,
            created_at=i.created_at,
            metadata=i.get_metadata(),
        )
        for i in interactions
    ]
