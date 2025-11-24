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
from app.core.config import settings
from app.models.pending_post import PendingPost
from app.schemas.moderation import (
    PendingItem,
    ModerationActionRequest,
    ModerationDecisionResponse,
)
from app.services.reddit_client import AsyncPRAWClient

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


async def _post_to_reddit(item: PendingPost) -> str:
    """
    Publish a pending item to Reddit using AsyncPRAWClient.

    Supports:
    - post/post_type="post": requires target_subreddit and title in metadata
    - comment/reply: requires parent_id (from model or draft_metadata)
    """
    client = AsyncPRAWClient(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        username=settings.reddit_username,
        password=settings.reddit_password,
    )

    metadata = item.get_draft_metadata()
    try:
        if item.post_type == "post":
            title = metadata.get("title")
            if not title or not item.target_subreddit:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing title or target_subreddit for post submission",
                )
            reddit_id = await client.submit_post(
                subreddit=item.target_subreddit,
                title=title,
                content=item.content,
                flair_id=metadata.get("flair_id"),
            )
        else:
            parent_id = item.parent_id or metadata.get("parent_id")
            if not parent_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing parent_id for reply/comment submission",
                )
            reddit_id = await client.reply(
                parent_id=parent_id,
                content=item.content,
            )
        return reddit_id
    finally:
        await client.close()


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

    # Attempt to publish to Reddit immediately
    try:
        reddit_id = await _post_to_reddit(item)
        metadata = item.get_draft_metadata()
        metadata["reddit_id"] = reddit_id
        item.set_draft_metadata(metadata)
        db.add(item)
        await db.commit()
        await db.refresh(item)
    except HTTPException:
        # Already contains proper status codes/messages
        raise
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        # revert status to pending so it can be retried
        item.status = "pending"
        item.reviewed_by = None
        item.reviewed_at = None
        metadata = item.get_draft_metadata()
        metadata["post_error"] = str(exc)
        item.set_draft_metadata(metadata)
        db.add(item)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to publish to Reddit: {exc}"
        ) from exc

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
