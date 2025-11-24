"""
Belief graph and history endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.services.memory_store import SQLiteMemoryStore
from app.schemas.beliefs import BeliefGraphResponse, BeliefHistoryResponse

router = APIRouter()
memory_store = SQLiteMemoryStore()


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
