from typing import List, Dict, Any
from pydantic import BaseModel


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
