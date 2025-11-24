from typing import List, Dict, Any
from collections import defaultdict
from ..models import NewsItem
from ..clients.reddit_client import RedditClient
from .scoring import calculate_media_power
import logging
import asyncio

logger = logging.getLogger(__name__)

class NewsAnalyzer:
    def __init__(self, reddit_client: RedditClient):
        """Initialize news analyzer with Reddit client."""
        self.reddit_client = reddit_client

        # Group subreddits by political leaning/category
        self.subreddit_categories = {
            'mainstream': ['news', 'worldnews'],
            'political_right': ['conservative', 'republicans'],
            'political_left': ['politics', 'democrats'],
            'technology': ['technology', 'futurology'],
            'science': ['science', 'environment'],
        }

    async def get_top_news(self) -> List[NewsItem]:
        """
        Fetch and score top news from various subreddits.
        Ensures diversity in sources and topics.

        Returns:
            List[NewsItem]: List of top scored news items
        """
        all_news_items = []
        category_top_items = defaultdict(list)

        # Fetch posts from all subreddits
        for category, subreddits in self.subreddit_categories.items():
            for subreddit in subreddits:
                try:
                    posts = await self.reddit_client.get_hot_posts(subreddit)

                    for post in posts:
                        # Skip posts that are likely not news
                        if self._should_skip_post(post):
                            continue

                        score = calculate_media_power(post)

                        news_item = NewsItem(
                            title=post['title'],
                            url=post['url'],
                            score=score,
                            subreddit=subreddit,
                            upvote_ratio=post['upvote_ratio'],
                            num_comments=post['num_comments']
                        )

                        all_news_items.append(news_item)
                        category_top_items[category].append(news_item)

                except Exception as e:
                    logger.error(f"Error analyzing {subreddit}: {str(e)}")
                    continue

        # Select top items ensuring category diversity
        return self._select_diverse_top_items(category_top_items)

    def _should_skip_post(self, post: Dict[str, Any]) -> bool:
        """
        Determine if a post should be skipped based on various criteria.
        """
        # Skip if title is too short (likely not a news article)
        if len(post['title']) < 30:
            return True

        # Skip if it's a meme or image post without substance
        if post['url'].endswith(('.jpg', '.png', '.gif')):
            return True

        # Skip if upvote ratio is too low (controversial or low quality)
        if post['upvote_ratio'] < 0.5:
            return True

        return False

    def _select_diverse_top_items(self, category_items: Dict[str, List[NewsItem]]) -> List[NewsItem]:
        """
        Select top items ensuring representation from different categories.
        """
        selected_items = []

        # Sort items within each category
        for category in category_items:
            category_items[category].sort(key=lambda x: x.score, reverse=True)

        # Select top item from each category first
        for category in category_items:
            if category_items[category]:
                selected_items.append(category_items[category][0])
                category_items[category].pop(0)

        # Fill remaining slots with highest scoring items from any category
        remaining_slots = 5 - len(selected_items)
        if remaining_slots > 0:
            all_remaining = []
            for items in category_items.values():
                all_remaining.extend(items)

            all_remaining.sort(key=lambda x: x.score, reverse=True)
            selected_items.extend(all_remaining[:remaining_slots])

        return selected_items[:5]  # Ensure we return at most 5 items