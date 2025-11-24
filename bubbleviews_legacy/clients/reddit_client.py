from typing import List
import asyncpraw
from pydantic import BaseModel
from ..models import NewsItem
from ..exceptions import APIError
import logging
import asyncio
from aiohttp import ClientError
import backoff

logger = logging.getLogger(__name__)

class RedditClient:
    def __init__(self, config: dict):
        """Initialize Reddit client with configuration."""
        try:
            self.reddit = asyncpraw.Reddit(
                client_id=config['client_id'],
                client_secret=config['client_secret'],
                user_agent=config['user_agent'],
                username=config['username'],
                password=config['password']
            )
            self.subreddits = [
                'news', 'worldnews', 'politics', 'conservative',
                'liberal', 'technology', 'science', 'environment'
            ]
        except Exception as e:
            raise APIError(f"Failed to initialize Reddit client: {str(e)}")

    @backoff.on_exception(
        backoff.expo,
        (asyncio.TimeoutError, ClientError),
        max_tries=3,
        max_time=30
    )
    async def get_hot_posts(self, subreddit_name: str, limit: int = 10) -> List[dict]:
        """
        Fetch hot posts from a subreddit with retry logic.

        Args:
            subreddit_name: Name of the subreddit
            limit: Maximum number of posts to fetch

        Returns:
            List[dict]: List of post data dictionaries
        """
        try:
            async with asyncio.timeout(30):
                subreddit = await self.reddit.subreddit(subreddit_name)
                posts = []

                async for submission in subreddit.hot(limit=limit):
                    try:
                        # Extract post data within a separate timeout context
                        async with asyncio.timeout(5):
                            posts.append({
                                'title': submission.title,
                                'url': submission.url,
                                'score': submission.score,
                                'upvote_ratio': submission.upvote_ratio,
                                'num_comments': submission.num_comments,
                                'created_utc': submission.created_utc
                            })
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout processing post in {subreddit_name}, skipping")
                        continue

                return posts

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching posts from {subreddit_name}")
            raise APIError(f"Timeout fetching Reddit posts from {subreddit_name}")
        except Exception as e:
            logger.error(f"Error fetching posts from {subreddit_name}: {str(e)}")
            raise APIError(f"Failed to fetch Reddit posts: {str(e)}")

    @backoff.on_exception(
        backoff.expo,
        (asyncio.TimeoutError, ClientError),
        max_tries=3,
        max_time=30
    )
    async def submit_post(self, subreddit_name: str, title: str, content: str) -> None:
        """
        Submit a new post to a subreddit with retry logic.

        Args:
            subreddit_name: Target subreddit name
            title: Post title
            content: Post content
        """
        try:
            async with asyncio.timeout(30):
                subreddit = await self.reddit.subreddit(subreddit_name)
                await subreddit.submit(title=title, selftext=content)
                logger.info(f"Successfully posted to r/{subreddit_name}")

        except asyncio.TimeoutError:
            logger.error(f"Timeout posting to {subreddit_name}")
            raise APIError(f"Timeout submitting Reddit post to {subreddit_name}")
        except Exception as e:
            logger.error(f"Error posting to {subreddit_name}: {str(e)}")
            raise APIError(f"Failed to submit Reddit post: {str(e)}")