from typing import List, Dict, Any
from pydantic import BaseModel, Field


class BeliefNodeModel(BaseModel):
    id: str
    title: str
    summary: str
    confidence: float | None = None
    tags: List[str] | None = None
    created_at: Any | None = None
    updated_at: Any | None = None


class BeliefEdgeModel(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation: str
    weight: float | None = None
    created_at: Any | None = None


class BeliefGraphResponse(BaseModel):
    nodes: List[BeliefNodeModel]
    edges: List[BeliefEdgeModel]


class StanceModel(BaseModel):
    id: str
    text: str
    confidence: float | None = None
    status: str | None = None
    rationale: str | None = None
    created_at: Any | None = None


class EvidenceModel(BaseModel):
    id: str
    source_type: str
    source_ref: str
    strength: str | None = None
    created_at: Any | None = None


class BeliefUpdateModel(BaseModel):
    id: str
    old_value: Dict[str, Any] | None = None
    new_value: Dict[str, Any] | None = None
    reason: str
    trigger_type: str | None = None
    updated_by: str | None = None
    created_at: Any | None = None


class BeliefHistoryResponse(BaseModel):
    belief: Dict[str, Any]
    stances: List[StanceModel]
    evidence: List[EvidenceModel]
    updates: List[BeliefUpdateModel]


# Request schemas for belief updates

class BeliefUpdateRequest(BaseModel):
    """Request to manually update a belief."""
    persona_id: str
    confidence: float | None = None
    text: str | None = None
    rationale: str


class BeliefNudgeRequest(BaseModel):
    """Request to nudge belief confidence."""
    persona_id: str
    direction: str  # "more_confident" or "less_confident"
    amount: float = 0.1


class BeliefLockRequest(BaseModel):
    """Request to lock a belief stance."""
    persona_id: str
    reason: str | None = None


class BeliefUnlockRequest(BaseModel):
    """Request to unlock a belief stance."""
    persona_id: str
    reason: str | None = None


# Response schemas

class BeliefUpdateResponse(BaseModel):
    """Response after updating a belief."""
    belief_id: str
    old_confidence: float
    new_confidence: float
    status: str
    message: str


# ============================================================================
# Belief Creation Schemas
# ============================================================================

class BeliefCreateRequest(BaseModel):
    """Request to create a new belief."""
    persona_id: str
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Brief title/summary of the belief (max 500 chars)"
    )
    summary: str = Field(
        ...,
        min_length=1,
        description="Detailed description of the belief"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Initial confidence level (0.0-1.0)"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="List of tags for categorization"
    )
    auto_link: bool = Field(
        default=True,
        description="If True, suggest relationships with existing beliefs"
    )


class RelationshipSuggestion(BaseModel):
    """Suggestion for a relationship between beliefs."""
    target_belief_id: str = Field(
        ...,
        description="UUID of the related belief"
    )
    target_belief_title: str = Field(
        ...,
        description="Title of the related belief"
    )
    relation: str = Field(
        ...,
        pattern="^(supports|contradicts|depends_on|evidence_for)$",
        description="Type of relationship (supports, contradicts, depends_on, evidence_for)"
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Strength of relationship (0.0-1.0)"
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation for the suggested relationship"
    )


class BeliefCreateResponse(BaseModel):
    """Response after creating a new belief."""
    belief_id: str = Field(
        ...,
        description="UUID of the newly created belief"
    )
    suggested_relationships: List[RelationshipSuggestion] = Field(
        default_factory=list,
        description="List of suggested relationships with existing beliefs"
    )


class RelationshipCreateRequest(BaseModel):
    """Request to create a relationship between beliefs."""
    persona_id: str
    target_belief_id: str = Field(
        ...,
        description="UUID of the target belief"
    )
    relation: str = Field(
        ...,
        pattern="^(supports|contradicts|depends_on|evidence_for)$",
        description="Type of relationship (supports, contradicts, depends_on, evidence_for)"
    )
    weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Strength of relationship (0.0-1.0)"
    )
