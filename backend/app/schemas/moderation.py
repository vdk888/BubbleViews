from typing import Any, Dict, Optional
from pydantic import BaseModel


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
