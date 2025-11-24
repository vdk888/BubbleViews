from pydantic import BaseModel
from typing import Optional, List

class NewsItem(BaseModel):
    title: str
    url: str
    score: float
    subreddit: str
    upvote_ratio: float
    num_comments: int

class AnalysisResult(BaseModel):
    news_item: NewsItem
    mckenna_analysis: str
    platforms_posted: List[str] = []
    validation_status: Optional[str] = None
