"""
Moderation queue endpoints.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.pending_post import PendingPost
from app.schemas.moderation import (
    PendingItem,
    ModerationActionRequest,
    ModerationDecisionResponse,
)

router = APIRouter()


@router.get(
    "/moderation/pending",
    response_model=List[PendingItem],
    summary="List pending posts",
)
async def list_pending(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> List[PendingItem]:
    stmt = (
        select(PendingPost)
        .where(PendingPost.persona_id == persona_id, PendingPost.status == "pending")
        .order_by(PendingPost.created_at.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        PendingItem(
            id=item.id,
            persona_id=item.persona_id,
            content=item.content,
            post_type=item.post_type,
            target_subreddit=item.target_subreddit,
            parent_id=item.parent_id,
            draft_metadata=item.get_draft_metadata(),
            status=item.status,
            created_at=item.created_at,
        )
        for item in items
    ]


async def _update_status(
    db: AsyncSession,
    item_id: str,
    persona_id: str,
    status_value: str,
    reviewer: str,
    reason: str | None = None,
) -> PendingPost:
    stmt = select(PendingPost).where(
        PendingPost.id == item_id,
        PendingPost.persona_id == persona_id,
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    item.status = status_value
    item.reviewed_by = reviewer
    item.reviewed_at = datetime.utcnow().isoformat()
    metadata = item.get_draft_metadata()
    if reason:
        metadata["review_reason"] = reason
    item.set_draft_metadata(metadata)
    db.add(item)
    await db.commit()
    return item


@router.post(
    "/moderation/approve",
    response_model=ModerationDecisionResponse,
    summary="Approve a pending item",
)
async def approve(
    payload: ModerationActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> ModerationDecisionResponse:
    item = await _update_status(
        db=db,
        item_id=payload.item_id,
        persona_id=payload.persona_id,
        status_value="approved",
        reviewer=current_user.username,
    )
    return ModerationDecisionResponse(
        item_id=item.id,
        status=item.status,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
    )


@router.post(
    "/moderation/reject",
    response_model=ModerationDecisionResponse,
    summary="Reject a pending item",
)
async def reject(
    payload: ModerationActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> ModerationDecisionResponse:
    item = await _update_status(
        db=db,
        item_id=payload.item_id,
        persona_id=payload.persona_id,
        status_value="rejected",
        reviewer=current_user.username,
        reason="rejected",
    )
    return ModerationDecisionResponse(
        item_id=item.id,
        status=item.status,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
    )


@router.post(
    "/moderation/override-flag",
    response_model=ModerationDecisionResponse,
    summary="Override moderation flag",
)
async def override_flag(
    payload: ModerationActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> ModerationDecisionResponse:
    # mark override in metadata and approve
    stmt = select(PendingPost).where(
        PendingPost.id == payload.item_id,
        PendingPost.persona_id == payload.persona_id,
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    metadata = item.get_draft_metadata()
    metadata["flag_override"] = True
    item.set_draft_metadata(metadata)

    item.status = "approved"
    item.reviewed_by = current_user.username
    item.reviewed_at = datetime.utcnow().isoformat()
    db.add(item)
    await db.commit()

    return ModerationDecisionResponse(
        item_id=item.id,
        status=item.status,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
    )
