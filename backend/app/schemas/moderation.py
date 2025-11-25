from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class BeliefUpdateProposal(BaseModel):
    """Proposal to update an existing belief's confidence."""
    belief_id: str
    belief_title: str
    current_confidence: float
    proposed_confidence: float
    reason: str
    evidence_strength: str  # weak, moderate, strong


class NewBeliefProposal(BaseModel):
    """Proposal to create a new belief."""
    title: str
    summary: str
    initial_confidence: float
    tags: List[str]
    reason: str


class BeliefProposals(BaseModel):
    """Container for belief proposals from an interaction."""
    updates: List[BeliefUpdateProposal] = []
    new_belief: Optional[NewBeliefProposal] = None


class PendingItem(BaseModel):
    id: str
    persona_id: str
    content: str
    post_type: Optional[str] = None
    target_subreddit: Optional[str] = None
    parent_id: Optional[str] = None
    draft_metadata: Dict[str, Any] = {}
    status: str
    created_at: Any | None = None
    belief_proposals: Optional[BeliefProposals] = None  # Proposed belief changes on approval

    class Config:
        from_attributes = True


class ModerationActionRequest(BaseModel):
    item_id: str
    persona_id: str


class ModerationDecisionResponse(BaseModel):
    item_id: str
    status: str
    reviewed_by: str | None = None
    reviewed_at: Any | None = None
