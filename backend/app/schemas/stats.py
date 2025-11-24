from pydantic import BaseModel


class StatsResponse(BaseModel):
    interactions: int = 0
    pending_posts: int = 0
    belief_updates: int = 0
