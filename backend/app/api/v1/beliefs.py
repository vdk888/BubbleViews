"""
Belief graph and history endpoints.

Provides CRUD operations for belief management:
- GET /beliefs - Query belief graph
- GET /beliefs/{belief_id}/history - Get belief history
- POST /beliefs - Create new belief with optional auto-linking
- PUT /beliefs/{belief_id} - Update belief
- POST /beliefs/{belief_id}/relationships - Create relationship
- DELETE /beliefs/{belief_id}/relationships/{edge_id} - Delete relationship
- POST /beliefs/{belief_id}/suggest-relationships - Get relationship suggestions
- POST /beliefs/{belief_id}/lock - Lock belief stance
- POST /beliefs/{belief_id}/unlock - Unlock belief stance
- POST /beliefs/{belief_id}/nudge - Nudge belief confidence
"""

import json
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_

from app.api.dependencies import get_current_user, get_llm_client
from app.core.database import async_session_maker
from app.models.belief import BeliefNode, BeliefEdge, StanceVersion
from app.models.persona import Persona
from app.services.memory_store import SQLiteMemoryStore
from app.services.belief_updater import BeliefUpdater
from app.services.relationship_suggester import suggest_relationships
from app.services.interfaces.llm_client import ILLMClient
from app.schemas.beliefs import (
    BeliefGraphResponse,
    BeliefHistoryResponse,
    BeliefUpdateRequest,
    BeliefUpdateResponse,
    BeliefNudgeRequest,
    BeliefLockRequest,
    BeliefUnlockRequest,
    BeliefCreateRequest,
    BeliefCreateResponse,
    RelationshipSuggestion,
    RelationshipCreateRequest,
)

router = APIRouter()
memory_store = SQLiteMemoryStore()
belief_updater = BeliefUpdater(memory_store=memory_store)
logger = logging.getLogger(__name__)


@router.get(
    "/beliefs",
    response_model=BeliefGraphResponse,
    summary="Belief graph",
    description="Returns belief nodes and edges for a persona.",
)
async def get_belief_graph(
    persona_id: str,
    min_confidence: Optional[float] = None,
    tags: Optional[str] = None,
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> BeliefGraphResponse:
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    graph = await memory_store.query_belief_graph(
        persona_id=persona_id,
        tags=tag_list,
        min_confidence=min_confidence,
    )
    return BeliefGraphResponse(**graph)


@router.get(
    "/beliefs/{belief_id}/history",
    response_model=BeliefHistoryResponse,
    summary="Belief history",
    description="Returns stances, evidence, and updates for a belief.",
)
async def get_belief_history(
    belief_id: str,
    persona_id: str,
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> BeliefHistoryResponse:
    data = await memory_store.get_belief_with_stances(
        persona_id=persona_id,
        belief_id=belief_id,
    )
    return BeliefHistoryResponse(**data)


@router.put(
    "/beliefs/{belief_id}",
    response_model=BeliefUpdateResponse,
    summary="Update belief",
    description="Manually update a belief's confidence and/or text (requires auth).",
)
async def update_belief(
    belief_id: str,
    request: BeliefUpdateRequest,
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> BeliefUpdateResponse:
    """
    Manually update a belief with new confidence and/or text.

    This endpoint allows admins to override belief values directly.
    The update will be logged with the admin's username in the audit trail.
    """
    try:
        # Get current belief data
        belief_data = await memory_store.get_belief_with_stances(
            persona_id=request.persona_id,
            belief_id=belief_id,
        )
        old_confidence = belief_data["belief"]["current_confidence"]

        # Perform manual update
        new_confidence = await belief_updater.manual_update(
            persona_id=request.persona_id,
            belief_id=belief_id,
            confidence=request.confidence,
            text=request.text,
            rationale=request.rationale,
            updated_by=current_user.username if hasattr(current_user, "username") else "admin"
        )

        return BeliefUpdateResponse(
            belief_id=belief_id,
            old_confidence=old_confidence,
            new_confidence=new_confidence,
            status="updated",
            message="Belief successfully updated"
        )

    except ValueError as e:
        logger.error(f"Belief update failed: {e}", extra={"belief_id": belief_id})
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        logger.warning(f"Belief update blocked: {e}", extra={"belief_id": belief_id})
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error updating belief: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/beliefs/{belief_id}/lock",
    summary="Lock belief stance",
    description="Lock a belief stance to prevent automatic updates (requires auth).",
)
async def lock_belief(
    belief_id: str,
    request: BeliefLockRequest,
    current_user=Depends(get_current_user),  # noqa: ANN001
):
    """
    Lock a belief stance to prevent automatic updates.

    Locked stances will reject all automatic evidence-based updates.
    Manual updates via PUT /beliefs/{id} will also be blocked.
    To modify a locked belief, unlock it first.
    """
    try:
        await memory_store.lock_stance(
            persona_id=request.persona_id,
            belief_id=belief_id,
            reason=request.reason,
            updated_by=current_user.username if hasattr(current_user, "username") else "admin"
        )

        return {
            "belief_id": belief_id,
            "status": "locked",
            "message": "Belief stance successfully locked"
        }

    except ValueError as e:
        logger.error(f"Belief lock failed: {e}", extra={"belief_id": belief_id})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error locking belief: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/beliefs/{belief_id}/unlock",
    summary="Unlock belief stance",
    description="Unlock a belief stance to allow automatic updates (requires auth).",
)
async def unlock_belief(
    belief_id: str,
    request: BeliefUnlockRequest,
    current_user=Depends(get_current_user),  # noqa: ANN001
):
    """
    Unlock a belief stance to allow automatic updates.

    This will change the stance status from "locked" back to "current",
    allowing the belief updater to apply evidence-based confidence changes.
    """
    try:
        await memory_store.unlock_stance(
            persona_id=request.persona_id,
            belief_id=belief_id,
            reason=request.reason,
            updated_by=current_user.username if hasattr(current_user, "username") else "admin"
        )

        return {
            "belief_id": belief_id,
            "status": "unlocked",
            "message": "Belief stance successfully unlocked"
        }

    except ValueError as e:
        logger.error(f"Belief unlock failed: {e}", extra={"belief_id": belief_id})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error unlocking belief: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/beliefs/{belief_id}/nudge",
    response_model=BeliefUpdateResponse,
    summary="Nudge belief confidence",
    description="Apply a small confidence adjustment (soft update, requires auth).",
)
async def nudge_belief(
    belief_id: str,
    request: BeliefNudgeRequest,
    current_user=Depends(get_current_user),  # noqa: ANN001
) -> BeliefUpdateResponse:
    """
    Nudge belief confidence up or down by a small amount.

    This is a convenience endpoint for making minor adjustments without
    needing to specify exact confidence values. Useful for dashboard UI
    with +/- buttons.

    Direction values:
    - "more_confident" or "increase": increases confidence
    - "less_confident" or "decrease": decreases confidence
    """
    try:
        # Map direction values
        direction_map = {
            "more_confident": "increase",
            "increase": "increase",
            "less_confident": "decrease",
            "decrease": "decrease",
        }

        direction = direction_map.get(request.direction.lower())
        if not direction:
            raise ValueError(
                f"Invalid direction: {request.direction}. "
                f"Must be 'more_confident', 'less_confident', 'increase', or 'decrease'"
            )

        # Get current belief data
        belief_data = await memory_store.get_belief_with_stances(
            persona_id=request.persona_id,
            belief_id=belief_id,
        )
        old_confidence = belief_data["belief"]["current_confidence"]

        # Perform nudge
        new_confidence = await belief_updater.nudge_confidence(
            persona_id=request.persona_id,
            belief_id=belief_id,
            direction=direction,
            amount=request.amount,
            reason=f"Manual nudge: {direction} by {request.amount}",
            updated_by=current_user.username if hasattr(current_user, "username") else "admin"
        )

        return BeliefUpdateResponse(
            belief_id=belief_id,
            old_confidence=old_confidence,
            new_confidence=new_confidence,
            status="nudged",
            message=f"Belief confidence {direction}d by {request.amount}"
        )

    except ValueError as e:
        logger.error(f"Belief nudge failed: {e}", extra={"belief_id": belief_id})
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        logger.warning(f"Belief nudge blocked: {e}", extra={"belief_id": belief_id})
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error nudging belief: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Belief Creation and Relationship Management Endpoints
# ============================================================================


@router.post(
    "/beliefs",
    response_model=BeliefCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new belief",
    description="Create a new belief node with optional auto-linking to existing beliefs.",
)
async def create_belief(
    request: BeliefCreateRequest,
    current_user=Depends(get_current_user),  # noqa: ANN001
    llm_client: ILLMClient = Depends(get_llm_client),
) -> BeliefCreateResponse:
    """
    Create a new belief in the persona's knowledge graph.

    This endpoint creates a new belief node with an initial stance version.
    If auto_link is True, it will use LLM to suggest relationships with
    existing beliefs (but does NOT automatically create edges).

    Args:
        request: BeliefCreateRequest with persona_id, title, summary, etc.
        current_user: Authenticated user
        llm_client: LLM client for relationship suggestions

    Returns:
        BeliefCreateResponse with belief_id and suggested_relationships

    Raises:
        400: Validation error
        404: Persona not found
        500: Internal server error
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        "Creating new belief",
        extra={
            "correlation_id": correlation_id,
            "persona_id": request.persona_id,
            "title": request.title[:50],
            "auto_link": request.auto_link
        }
    )

    try:
        async with async_session_maker() as session:
            async with session.begin():
                # 1. Validate persona exists
                stmt = select(Persona).where(Persona.id == request.persona_id)
                result = await session.execute(stmt)
                persona = result.scalar_one_or_none()

                if not persona:
                    logger.warning(
                        "Persona not found for belief creation",
                        extra={
                            "correlation_id": correlation_id,
                            "persona_id": request.persona_id
                        }
                    )
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Persona {request.persona_id} not found"
                    )

                # 2. Create BeliefNode
                belief_id = str(uuid.uuid4())
                belief_node = BeliefNode(
                    id=belief_id,
                    persona_id=request.persona_id,
                    title=request.title,
                    summary=request.summary,
                    current_confidence=request.confidence,
                )
                belief_node.set_tags(request.tags)
                session.add(belief_node)

                # 3. Create initial StanceVersion
                stance_id = str(uuid.uuid4())
                stance = StanceVersion(
                    id=stance_id,
                    persona_id=request.persona_id,
                    belief_id=belief_id,
                    text=request.summary,
                    confidence=request.confidence,
                    status="current",
                    rationale="Initial belief creation",
                )
                session.add(stance)

                await session.flush()

                logger.info(
                    "Belief created successfully",
                    extra={
                        "correlation_id": correlation_id,
                        "belief_id": belief_id,
                        "persona_id": request.persona_id
                    }
                )

        # 4. Get relationship suggestions if auto_link is True
        suggested_relationships: List[RelationshipSuggestion] = []

        if request.auto_link:
            # Fetch existing beliefs for this persona
            graph = await memory_store.query_belief_graph(
                persona_id=request.persona_id,
                min_confidence=0.0  # Include all beliefs
            )

            existing_beliefs = [
                node for node in graph.get("nodes", [])
                if node.get("id") != belief_id  # Exclude the just-created belief
            ]

            if existing_beliefs:
                suggested_relationships = await suggest_relationships(
                    persona_id=request.persona_id,
                    belief_title=request.title,
                    belief_summary=request.summary,
                    existing_beliefs=existing_beliefs,
                    llm_client=llm_client,
                    max_suggestions=5,
                    correlation_id=correlation_id
                )

                logger.info(
                    "Relationship suggestions generated",
                    extra={
                        "correlation_id": correlation_id,
                        "belief_id": belief_id,
                        "suggestion_count": len(suggested_relationships)
                    }
                )

        return BeliefCreateResponse(
            belief_id=belief_id,
            suggested_relationships=suggested_relationships
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Unexpected error creating belief: {e}",
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/beliefs/{belief_id}/relationships",
    status_code=status.HTTP_201_CREATED,
    summary="Create relationship",
    description="Create a relationship (edge) between two beliefs.",
)
async def create_relationship(
    belief_id: str,
    request: RelationshipCreateRequest,
    current_user=Depends(get_current_user),  # noqa: ANN001
):
    """
    Create a relationship between the source belief and target belief.

    This endpoint creates an edge in the belief graph connecting two beliefs.
    Both beliefs must exist and belong to the same persona.

    Args:
        belief_id: UUID of the source belief
        request: RelationshipCreateRequest with target_belief_id, relation, weight
        current_user: Authenticated user

    Returns:
        Dict with edge_id and status

    Raises:
        400: Validation error (same belief, invalid relation)
        404: Belief not found
        500: Internal server error
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        "Creating belief relationship",
        extra={
            "correlation_id": correlation_id,
            "source_belief_id": belief_id,
            "target_belief_id": request.target_belief_id,
            "relation": request.relation
        }
    )

    # Validate not linking to self
    if belief_id == request.target_belief_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create relationship to the same belief"
        )

    try:
        async with async_session_maker() as session:
            async with session.begin():
                # 1. Validate source belief exists
                stmt = select(BeliefNode).where(
                    and_(
                        BeliefNode.id == belief_id,
                        BeliefNode.persona_id == request.persona_id
                    )
                )
                result = await session.execute(stmt)
                source_belief = result.scalar_one_or_none()

                if not source_belief:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Source belief {belief_id} not found for persona {request.persona_id}"
                    )

                # 2. Validate target belief exists
                stmt = select(BeliefNode).where(
                    and_(
                        BeliefNode.id == request.target_belief_id,
                        BeliefNode.persona_id == request.persona_id
                    )
                )
                result = await session.execute(stmt)
                target_belief = result.scalar_one_or_none()

                if not target_belief:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Target belief {request.target_belief_id} not found for persona {request.persona_id}"
                    )

                # 3. Create BeliefEdge
                edge_id = str(uuid.uuid4())
                edge = BeliefEdge(
                    id=edge_id,
                    persona_id=request.persona_id,
                    source_id=belief_id,
                    target_id=request.target_belief_id,
                    relation=request.relation,
                    weight=request.weight,
                )
                session.add(edge)

                await session.flush()

                logger.info(
                    "Relationship created successfully",
                    extra={
                        "correlation_id": correlation_id,
                        "edge_id": edge_id,
                        "source_id": belief_id,
                        "target_id": request.target_belief_id,
                        "relation": request.relation
                    }
                )

        return {
            "edge_id": edge_id,
            "status": "created",
            "message": "Relationship created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Unexpected error creating relationship: {e}",
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete(
    "/beliefs/{belief_id}/relationships/{edge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete relationship",
    description="Delete a relationship (edge) between beliefs.",
)
async def delete_relationship(
    belief_id: str,
    edge_id: str,
    persona_id: str,
    current_user=Depends(get_current_user),  # noqa: ANN001
):
    """
    Delete a relationship (edge) from the belief graph.

    The edge must exist and belong to the specified persona.

    Args:
        belief_id: UUID of the source belief
        edge_id: UUID of the edge to delete
        persona_id: UUID of the persona (query param)
        current_user: Authenticated user

    Returns:
        204 No Content on success

    Raises:
        404: Edge not found
        500: Internal server error
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        "Deleting belief relationship",
        extra={
            "correlation_id": correlation_id,
            "belief_id": belief_id,
            "edge_id": edge_id,
            "persona_id": persona_id
        }
    )

    try:
        async with async_session_maker() as session:
            async with session.begin():
                # Find and delete the edge
                stmt = select(BeliefEdge).where(
                    and_(
                        BeliefEdge.id == edge_id,
                        BeliefEdge.source_id == belief_id,
                        BeliefEdge.persona_id == persona_id
                    )
                )
                result = await session.execute(stmt)
                edge = result.scalar_one_or_none()

                if not edge:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Edge {edge_id} not found for belief {belief_id}"
                    )

                await session.delete(edge)

                logger.info(
                    "Relationship deleted successfully",
                    extra={
                        "correlation_id": correlation_id,
                        "edge_id": edge_id
                    }
                )

        return None  # 204 No Content

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Unexpected error deleting relationship: {e}",
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/beliefs/{belief_id}/suggest-relationships",
    response_model=List[RelationshipSuggestion],
    summary="Suggest relationships",
    description="Get LLM-powered relationship suggestions for an existing belief.",
)
async def suggest_relationships_for_belief(
    belief_id: str,
    persona_id: str,
    current_user=Depends(get_current_user),  # noqa: ANN001
    llm_client: ILLMClient = Depends(get_llm_client),
) -> List[RelationshipSuggestion]:
    """
    Get relationship suggestions for an existing belief.

    Uses LLM to analyze the belief and suggest meaningful relationships
    with other beliefs in the persona's knowledge graph.

    This is a GET endpoint that fetches suggestions without modifying state.

    Args:
        belief_id: UUID of the belief to get suggestions for
        persona_id: UUID of the persona (query param)
        current_user: Authenticated user
        llm_client: LLM client for generating suggestions

    Returns:
        List of RelationshipSuggestion objects

    Raises:
        404: Belief not found
        500: Internal server error
    """
    correlation_id = str(uuid.uuid4())

    logger.info(
        "Suggesting relationships for existing belief",
        extra={
            "correlation_id": correlation_id,
            "belief_id": belief_id,
            "persona_id": persona_id
        }
    )

    try:
        # 1. Fetch the belief
        belief_data = await memory_store.get_belief_with_stances(
            persona_id=persona_id,
            belief_id=belief_id
        )

        belief = belief_data["belief"]

        # 2. Fetch all other beliefs for this persona
        graph = await memory_store.query_belief_graph(
            persona_id=persona_id,
            min_confidence=0.0  # Include all beliefs
        )

        existing_beliefs = [
            node for node in graph.get("nodes", [])
            if node.get("id") != belief_id  # Exclude the target belief
        ]

        if not existing_beliefs:
            logger.info(
                "No other beliefs to suggest relationships with",
                extra={
                    "correlation_id": correlation_id,
                    "belief_id": belief_id
                }
            )
            return []

        # 3. Get suggestions from LLM
        suggestions = await suggest_relationships(
            persona_id=persona_id,
            belief_title=belief["title"],
            belief_summary=belief["summary"],
            existing_beliefs=existing_beliefs,
            llm_client=llm_client,
            max_suggestions=5,
            correlation_id=correlation_id
        )

        logger.info(
            "Relationship suggestions generated for existing belief",
            extra={
                "correlation_id": correlation_id,
                "belief_id": belief_id,
                "suggestion_count": len(suggestions)
            }
        )

        return suggestions

    except ValueError as e:
        logger.error(
            f"Belief not found: {e}",
            extra={
                "correlation_id": correlation_id,
                "belief_id": belief_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(
            f"Unexpected error suggesting relationships: {e}",
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
