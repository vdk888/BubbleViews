"""
Belief graph and history endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_current_user
from app.services.memory_store import SQLiteMemoryStore
from app.services.belief_updater import BeliefUpdater
from app.schemas.beliefs import (
    BeliefGraphResponse,
    BeliefHistoryResponse,
    BeliefUpdateRequest,
    BeliefUpdateResponse,
    BeliefNudgeRequest,
    BeliefLockRequest,
    BeliefUnlockRequest,
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
