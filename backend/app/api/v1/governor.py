"""
Governor API Endpoints

Provides conversational interface for admins to query the agent's reasoning,
belief evolution, and past interactions. The Governor acts as an introspective
observer that can explain but not directly modify agent state.

Belief adjustment proposals from the Governor require explicit admin approval.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.interfaces.memory_store import IMemoryStore
from app.services.interfaces.llm_client import ILLMClient
from app.services.belief_updater import BeliefUpdater
from app.services.governor import query_governor
from app.api.dependencies import (
    get_memory_store,
    get_llm_client,
    get_belief_updater,
    get_current_user
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governor", tags=["governor"])


# Pydantic models
class GovernorQueryRequest(BaseModel):
    """Request model for governor query"""
    persona_id: str = Field(..., description="UUID of persona to query about")
    question: str = Field(..., min_length=1, max_length=1000, description="Question to ask the governor")


class BeliefProposal(BaseModel):
    """Belief adjustment proposal from governor"""
    type: str = Field(..., description="Proposal type (always 'belief_adjustment')")
    belief_id: str = Field(..., description="UUID of belief to adjust")
    current_confidence: float = Field(..., ge=0.0, le=1.0)
    proposed_confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., description="Rationale for adjustment")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence (interaction IDs)")


class SourceReference(BaseModel):
    """Source citation in governor response"""
    type: str = Field(..., description="Type of reference (id_reference, reddit_id, etc.)")
    id: str = Field(..., description="The ID or reference value")


class GovernorQueryResponse(BaseModel):
    """Response model for governor query"""
    answer: str = Field(..., description="Governor's response text")
    sources: List[SourceReference] = Field(default_factory=list, description="Cited sources")
    proposal: Optional[BeliefProposal] = Field(None, description="Belief adjustment proposal if generated")
    intent: str = Field(..., description="Classified query intent")
    tokens_used: int = Field(..., description="Total tokens consumed")
    cost: float = Field(..., description="Cost in USD")
    model: str = Field(..., description="LLM model used")


class ApproveProposalRequest(BaseModel):
    """Request model for approving/rejecting a proposal"""
    persona_id: str = Field(..., description="UUID of persona")
    belief_id: str = Field(..., description="UUID of belief to update")
    proposed_confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., description="Reason for the update")
    approved: bool = Field(..., description="True to approve, False to reject")


class ApproveProposalResponse(BaseModel):
    """Response model for approval action"""
    status: str = Field(..., description="approved or rejected")
    belief_id: Optional[str] = Field(None, description="Updated belief ID if approved")
    message: str = Field(..., description="Status message")


@router.post("/query", response_model=GovernorQueryResponse)
async def query_governor_endpoint(
    request: GovernorQueryRequest,
    memory_store: IMemoryStore = Depends(get_memory_store),
    llm_client: ILLMClient = Depends(get_llm_client),
    current_user = Depends(get_current_user)
):
    """
    Query the Governor for introspective analysis.

    Ask questions about:
    - Why the agent said or did something
    - How beliefs evolved over time
    - Past interactions on specific topics
    - Whether beliefs should be adjusted

    The Governor will respond with explanations, citations, and optionally
    a belief adjustment proposal for admin approval.

    Requires authentication.
    """
    try:
        logger.info(
            "Governor query received",
            extra={
                "persona_id": request.persona_id,
                "question": request.question,
                "user_id": current_user.id
            }
        )

        result = await query_governor(
            persona_id=request.persona_id,
            question=request.question,
            memory_store=memory_store,
            llm_client=llm_client
        )

        # Convert to response model
        response = GovernorQueryResponse(
            answer=result["answer"],
            sources=[
                SourceReference(type=s["type"], id=s["id"])
                for s in result.get("sources", [])
            ],
            proposal=(
                BeliefProposal(**result["proposal"])
                if result.get("proposal")
                else None
            ),
            intent=result["intent"],
            tokens_used=result["tokens_used"],
            cost=result["cost"],
            model=result["model"]
        )

        logger.info(
            "Governor query completed",
            extra={
                "persona_id": request.persona_id,
                "intent": result["intent"],
                "has_proposal": result.get("proposal") is not None,
                "tokens_used": result["tokens_used"],
                "cost": result["cost"]
            }
        )

        return response

    except ValueError as e:
        logger.error(f"Governor query validation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Governor query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process governor query"
        )


@router.post("/approve-proposal", response_model=ApproveProposalResponse)
async def approve_proposal_endpoint(
    request: ApproveProposalRequest,
    memory_store: IMemoryStore = Depends(get_memory_store),
    belief_updater: BeliefUpdater = Depends(get_belief_updater),
    current_user = Depends(get_current_user)
):
    """
    Approve or reject a belief adjustment proposal from the Governor.

    If approved, the belief's confidence will be updated and logged as a
    manual adjustment by the current admin user.

    If rejected, no action is taken.

    Requires authentication.
    """
    try:
        logger.info(
            "Proposal approval request",
            extra={
                "persona_id": request.persona_id,
                "belief_id": request.belief_id,
                "approved": request.approved,
                "user_id": current_user.id
            }
        )

        if not request.approved:
            return ApproveProposalResponse(
                status="rejected",
                message="Proposal rejected by admin"
            )

        # Verify belief exists
        try:
            belief_data = await memory_store.get_belief_with_stances(
                persona_id=request.persona_id,
                belief_id=request.belief_id
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Belief {request.belief_id} not found"
            )

        # Get current stance to check if locked
        current_stance = None
        for stance in belief_data.get("stances", []):
            if stance["status"] in ("current", "locked"):
                current_stance = stance
                break

        if current_stance and current_stance["status"] == "locked":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Belief stance is locked and cannot be updated"
            )

        # Apply the belief update
        rationale = f"Governor proposal approved by {current_user.username}: {request.reason}"

        new_stance_id = await memory_store.update_stance_version(
            persona_id=request.persona_id,
            belief_id=request.belief_id,
            text=current_stance["text"] if current_stance else "Updated via Governor",
            confidence=request.proposed_confidence,
            rationale=rationale,
            updated_by=f"admin:{current_user.username}"
        )

        logger.info(
            "Proposal approved and applied",
            extra={
                "persona_id": request.persona_id,
                "belief_id": request.belief_id,
                "new_stance_id": new_stance_id,
                "old_confidence": current_stance["confidence"] if current_stance else None,
                "new_confidence": request.proposed_confidence,
                "user_id": current_user.id
            }
        )

        return ApproveProposalResponse(
            status="approved",
            belief_id=request.belief_id,
            message=f"Belief confidence updated from {current_stance['confidence']:.2f} to {request.proposed_confidence:.2f}"
        )

    except HTTPException:
        raise
    except PermissionError as e:
        logger.error(f"Permission denied for proposal approval: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        logger.error(f"Proposal approval validation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Proposal approval failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve proposal"
        )


@router.get("/health")
async def governor_health():
    """
    Health check endpoint for governor service.

    Returns simple OK status to verify the governor API is accessible.
    """
    return {"status": "ok", "service": "governor"}
