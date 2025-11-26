"""
Moderation queue endpoints.

Handles pending post approval/rejection with belief evolution:
- On approval: Post to Reddit AND apply belief changes
- On rejection: No changes applied
- On new belief creation: Automatically suggest and create relationships
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db, async_session_maker
from app.core.config import settings
from app.models.pending_post import PendingPost
from app.models.belief import BeliefNode, StanceVersion, BeliefEdge
from app.schemas.moderation import (
    PendingItem,
    ModerationActionRequest,
    ModerationDecisionResponse,
    BeliefProposals,
)
from app.services.reddit_client import AsyncPRAWClient
from app.services.memory_store import SQLiteMemoryStore
from app.services.belief_updater import BeliefUpdater
from app.services.relationship_suggester import suggest_relationships
from app.services.llm_client import OpenRouterClient

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
            results["new_belief_id"] = belief_id
            logger.info(
                "Created new belief from moderation approval",
                extra={
                    "persona_id": persona_id,
                    "belief_id": belief_id,
                    "title": new_belief.get("title"),
                    "reviewer": reviewer
                }
            )

            # Auto-create relationships if enabled
            if getattr(settings, 'auto_link_beliefs', True):
                relationship_results = await _auto_create_relationships(
                    persona_id=persona_id,
                    new_belief_id=belief_id,
                    belief_title=new_belief.get("title", ""),
                    belief_summary=new_belief.get("summary", ""),
                    correlation_id=reddit_id,
                )
                results["relationships_created"] = relationship_results.get("edges_created", 0)
                if relationship_results.get("errors"):
                    results["errors"].extend(relationship_results["errors"])

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


async def _auto_create_relationships(
    persona_id: str,
    new_belief_id: str,
    belief_title: str,
    belief_summary: str,
    correlation_id: Optional[str] = None,
) -> dict:
    """
    Automatically suggest and create relationships for a new belief.

    Fetches existing beliefs for the persona, uses LLM to suggest relationships,
    and creates BeliefEdge records for suggestions above the configured threshold.

    Args:
        persona_id: UUID of the persona
        new_belief_id: UUID of the newly created belief
        belief_title: Title of the new belief
        belief_summary: Summary/description of the new belief
        correlation_id: Optional request ID for tracing

    Returns:
        Dict with:
            - edges_created: Number of edges successfully created
            - suggestions_count: Total suggestions received from LLM
            - errors: List of error messages (if any)
    """
    results = {"edges_created": 0, "suggestions_count": 0, "errors": []}

    # Get threshold from settings (default 0.5)
    min_weight = getattr(settings, 'auto_link_min_weight', 0.5)

    try:
        # Fetch existing beliefs for the persona (limit to most recent/relevant)
        async with async_session_maker() as session:
            stmt = (
                select(BeliefNode)
                .where(
                    BeliefNode.persona_id == persona_id,
                    BeliefNode.id != new_belief_id  # Exclude the new belief itself
                )
                .order_by(BeliefNode.updated_at.desc())
                .limit(20)  # Limit to 20 most relevant beliefs
            )
            result = await session.execute(stmt)
            existing_beliefs = result.scalars().all()

        if not existing_beliefs:
            logger.info(
                "No existing beliefs to create relationships with",
                extra={
                    "correlation_id": correlation_id,
                    "persona_id": persona_id,
                    "new_belief_id": new_belief_id
                }
            )
            return results

        # Convert to dict format for relationship suggester
        existing_beliefs_data = [
            {
                "id": b.id,
                "title": b.title,
                "summary": b.summary,
                "confidence": b.current_confidence or 0.5
            }
            for b in existing_beliefs
        ]

        # Initialize LLM client for relationship suggestions
        llm_client = OpenRouterClient()

        # Get suggestions from LLM
        suggestions = await suggest_relationships(
            persona_id=persona_id,
            belief_title=belief_title,
            belief_summary=belief_summary,
            existing_beliefs=existing_beliefs_data,
            llm_client=llm_client,
            max_suggestions=5,
            correlation_id=correlation_id,
        )

        results["suggestions_count"] = len(suggestions)

        if not suggestions:
            logger.info(
                "No relationship suggestions generated",
                extra={
                    "correlation_id": correlation_id,
                    "persona_id": persona_id,
                    "new_belief_id": new_belief_id,
                    "existing_belief_count": len(existing_beliefs)
                }
            )
            return results

        # Filter suggestions by weight threshold and create edges
        edges_to_create = []
        for suggestion in suggestions:
            if suggestion.weight >= min_weight:
                edges_to_create.append({
                    "id": str(uuid.uuid4()),
                    "persona_id": persona_id,
                    "source_id": new_belief_id,
                    "target_id": suggestion.target_belief_id,
                    "relation": suggestion.relation,
                    "weight": suggestion.weight,
                })

        if not edges_to_create:
            logger.info(
                "No suggestions met minimum weight threshold",
                extra={
                    "correlation_id": correlation_id,
                    "persona_id": persona_id,
                    "new_belief_id": new_belief_id,
                    "suggestions_count": len(suggestions),
                    "min_weight": min_weight
                }
            )
            return results

        # Create BeliefEdge records
        async with async_session_maker() as session:
            async with session.begin():
                for edge_data in edges_to_create:
                    edge = BeliefEdge(**edge_data)
                    session.add(edge)
                    results["edges_created"] += 1

        logger.info(
            f"Auto-created {results['edges_created']} belief relationships for new belief {new_belief_id}",
            extra={
                "correlation_id": correlation_id,
                "persona_id": persona_id,
                "new_belief_id": new_belief_id,
                "edges_created": results["edges_created"],
                "suggestions_count": results["suggestions_count"],
                "min_weight": min_weight
            }
        )

    except Exception as e:
        logger.error(
            f"Failed to auto-create relationships: {e}",
            extra={
                "correlation_id": correlation_id,
                "persona_id": persona_id,
                "new_belief_id": new_belief_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        # Don't fail the whole approval - just log the error
        results["errors"].append(f"Relationship creation: {str(e)}")

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

    # Log interaction for activity feed and deduplication
    try:
        memory_store = SQLiteMemoryStore()
        await memory_store.log_interaction(
            persona_id=payload.persona_id,
            content=item.content,
            interaction_type=item.post_type or "comment",
            metadata={
                "reddit_id": reddit_id,
                "parent_id": item.parent_id,
                "subreddit": item.target_subreddit,
                "approved_by": current_user.username,
                "approved_at": datetime.utcnow().isoformat(),
                "pending_post_id": str(item.id),
            }
        )
        logger.info(
            "Logged interaction for approved post",
            extra={
                "item_id": payload.item_id,
                "persona_id": payload.persona_id,
                "reddit_id": reddit_id,
            }
        )
    except Exception as e:
        # Don't fail the approval if logging fails, but log the error
        logger.error(
            "Failed to log interaction for approved post",
            extra={
                "item_id": payload.item_id,
                "persona_id": payload.persona_id,
                "error": str(e),
            }
        )

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
