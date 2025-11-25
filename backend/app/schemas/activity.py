from typing import Any, Dict, Optional
from pydantic import BaseModel


class ActivityItem(BaseModel):
    id: str
    content: str
    interaction_type: str
    reddit_id: str
    subreddit: str
    parent_id: Optional[str] = None
    created_at: Optional[Any] = None
    metadata: Dict[str, Any] = {}

    class Config:
        from_attributes = True
