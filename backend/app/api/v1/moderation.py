"""
Moderation queue endpoints.

Handles pending post approval/rejection with belief evolution:
- On approval: Post to Reddit AND apply belief changes
- On rejection: No changes applied
"""

import logging
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db, async_session_maker
from app.core.config import settings
from app.models.pending_post import PendingPost
from app.models.belief import BeliefNode, StanceVersion
from app.schemas.moderation import (
    PendingItem,
    ModerationActionRequest,
    ModerationDecisionResponse,
    BeliefProposals,
)
from app.services.reddit_client import AsyncPRAWClient
from app.services.memory_store import SQLiteMemoryStore
from app.services.belief_updater import BeliefUpdater

logger = logging.getLogger(__name__)

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

    pending_items = []
    for item in items:
        metadata = item.get_draft_metadata()

        # Extract belief proposals from metadata if present
        belief_proposals = None
        raw_proposals = metadata.get("belief_proposals")
        if raw_proposals:
            belief_proposals = BeliefProposals(**raw_proposals)

        pending_items.append(PendingItem(
            id=item.id,
            persona_id=item.persona_id,
            content=item.content,
            post_type=item.post_type,
            target_subreddit=item.target_subreddit,
            parent_id=item.parent_id,
            draft_metadata=metadata,
            status=item.status,
            created_at=item.created_at,
            belief_proposals=belief_proposals,
        ))

    return pending_items


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


async def _apply_belief_changes(
    persona_id: str,
    proposals: dict,
    reviewer: str,
    reddit_id: str,
) -> dict:
    """
    Apply belief changes from proposals after successful Reddit post.

    Args:
        persona_id: UUID of the persona
        proposals: Dict with 'updates' and 'new_belief' from belief_proposals
        reviewer: Username of the admin who approved
        reddit_id: Reddit ID of the posted content (for evidence linking)

    Returns:
        Dict with applied changes summary
    """
    results = {"updates_applied": 0, "new_belief_created": False, "errors": []}

    if not proposals:
        return results

    memory_store = SQLiteMemoryStore()
    belief_updater = BeliefUpdater(memory_store=memory_store)

    # Apply confidence updates (max 3)
    updates = proposals.get("updates", [])[:3]
    for update in updates:
        try:
            belief_id = update.get("belief_id")
            current_conf = update.get("current_confidence", 0.5)
            proposed_conf = update.get("proposed_confidence", current_conf)
            evidence_strength = update.get("evidence_strength", "moderate")
            reason = update.get("reason", "From approved Reddit interaction")

            # Determine direction
            direction = "increase" if proposed_conf > current_conf else "decrease"

            await belief_updater.update_from_evidence(
                persona_id=persona_id,
                belief_id=belief_id,
                evidence_strength=evidence_strength,
                direction=direction,
                reason=f"[Approved by {reviewer}] {reason}",
                updated_by=f"moderation:{reviewer}"
            )
            results["updates_applied"] += 1

            logger.info(
                "Applied belief update from moderation approval",
                extra={
                    "persona_id": persona_id,
                    "belief_id": belief_id,
                    "direction": direction,
                    "evidence_strength": evidence_strength,
                    "reviewer": reviewer
                }
            )

        except Exception as e:
            logger.error(
                f"Failed to apply belief update: {e}",
                extra={
                    "persona_id": persona_id,
                    "belief_id": update.get("belief_id"),
                    "error": str(e)
                }
            )
            results["errors"].append(f"Update {update.get('belief_id')}: {str(e)}")

    # Create new belief (max 1)
    new_belief = proposals.get("new_belief")
    if new_belief:
        try:
            async with async_session_maker() as session:
                async with session.begin():
                    belief_id = str(uuid.uuid4())
                    belief_node = BeliefNode(
                        id=belief_id,
                        persona_id=persona_id,
                        title=new_belief.get("title", ""),
                        summary=new_belief.get("summary", ""),
                        current_confidence=new_belief.get("initial_confidence", 0.6),
                    )
                    belief_node.set_tags(new_belief.get("tags", []))
                    session.add(belief_node)

                    # Create initial stance
                    stance_id = str(uuid.uuid4())
                    stance = StanceVersion(
                        id=stance_id,
                        persona_id=persona_id,
                        belief_id=belief_id,
                        text=new_belief.get("summary", ""),
                        confidence=new_belief.get("initial_confidence", 0.6),
                        status="current",
                        rationale=f"[Created from interaction approved by {reviewer}] {new_belief.get('reason', '')}",
                    )
                    session.add(stance)

            results["new_belief_created"] = True
            logger.info(
                "Created new belief from moderation approval",
                extra={
                    "persona_id": persona_id,
                    "belief_id": belief_id,
                    "title": new_belief.get("title"),
                    "reviewer": reviewer
                }
            )

        except Exception as e:
            logger.error(
                f"Failed to create new belief: {e}",
                extra={
                    "persona_id": persona_id,
                    "title": new_belief.get("title"),
                    "error": str(e)
                }
            )
            results["errors"].append(f"New belief: {str(e)}")

    return results


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

    # Apply belief changes after successful Reddit post
    metadata = item.get_draft_metadata()
    belief_proposals = metadata.get("belief_proposals")
    if belief_proposals:
        belief_results = await _apply_belief_changes(
            persona_id=payload.persona_id,
            proposals=belief_proposals,
            reviewer=current_user.username,
            reddit_id=reddit_id,
        )
        # Store results in metadata for audit trail
        metadata["belief_changes_applied"] = belief_results
        item.set_draft_metadata(metadata)
        db.add(item)
        await db.commit()

        logger.info(
            "Applied belief changes on approval",
            extra={
                "item_id": payload.item_id,
                "persona_id": payload.persona_id,
                "updates_applied": belief_results["updates_applied"],
                "new_belief_created": belief_results["new_belief_created"]
            }
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
