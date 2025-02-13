from datetime import datetime
from typing import Dict, Any
import math

def calculate_media_power(submission: Dict[str, Any]) -> float:
    """
    Calculate a media power score based on various metrics.

    Args:
        submission: Dictionary containing submission data with fields:
            - score: Post score (upvotes - downvotes)
            - num_comments: Number of comments
            - upvote_ratio: Ratio of upvotes to total votes
            - created_utc: UTC timestamp of post creation

    Returns:
        float: Calculated media power score

    The score is calculated using:
    1. Base engagement (upvotes + weighted comments)
    2. Time decay factor (newer posts score higher)
    3. Controversy factor (posts with mixed reactions may indicate important topics)
    4. Velocity factor (rate of engagement over time)
    """
    current_time = datetime.utcnow().timestamp()
    post_age = current_time - submission['created_utc']

    # Calculate base engagement score
    engagement_score = submission['score'] + (submission['num_comments'] * 2)

    # Time decay factor (half-life of 12 hours)
    time_factor = math.exp(-post_age / (12 * 3600))

    # Controversy factor (peaks at 0.5 upvote ratio)
    controversy_factor = 1 + (abs(0.5 - submission['upvote_ratio']) * 2)

    # Velocity factor (engagement per hour, normalized)
    hours_since_posted = max(1, post_age / 3600)
    velocity = (engagement_score / hours_since_posted) / 100
    velocity_factor = math.log1p(velocity) + 1

    # Combine factors with weights
    final_score = (
        engagement_score * 
        time_factor * 
        controversy_factor * 
        velocity_factor
    )

    return max(0, final_score)  # Ensure non-negative score