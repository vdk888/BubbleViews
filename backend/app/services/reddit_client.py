"""
AsyncPRAW Reddit Client Implementation

Implements IRedditClient using the asyncpraw library for Reddit API interactions.
Provides rate limiting, retry logic, and error handling for all Reddit operations.

Key features:
- Full async/await support via asyncpraw
- Token bucket rate limiting (60 req/min)
- Exponential backoff with jitter for retries
- Graceful handling of deleted/removed content
- Detailed error transformation
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any

import asyncpraw
from asyncpraw.exceptions import RedditAPIException
from asyncpraw.models import Submission, Comment

from app.services.interfaces.reddit_client import IRedditClient
from app.services.rate_limiter import TokenBucket
from app.core.retry import retry_with_backoff, retry_on_rate_limit

logger = logging.getLogger(__name__)


class AsyncPRAWClient(IRedditClient):
    """
    Reddit client implementation using asyncpraw.

    Manages Reddit API authentication, rate limiting, and operations
    for fetching, searching, and posting content.

    Attributes:
        reddit: asyncpraw.Reddit instance
        rate_limiter: TokenBucket for rate limiting
        max_retries: Maximum retry attempts for transient failures
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        username: str,
        password: str,
        rate_limit_capacity: int = 60,
        rate_limit_refill: float = 1.0
    ):
        """
        Initialize AsyncPRAW client with credentials.

        Args:
            client_id: Reddit app client ID
            client_secret: Reddit app client secret
            user_agent: User agent string (format: "platform:appname:version (by /u/username)")
            username: Reddit account username
            password: Reddit account password
            rate_limit_capacity: Token bucket capacity (default: 60)
            rate_limit_refill: Tokens per second (default: 1.0)

        Note:
            - Credentials must be for a valid Reddit script app
            - User agent should follow Reddit's guidelines
            - Rate limits: 60 requests/minute default
        """
        self.reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            username=username,
            password=password
        )

        self.rate_limiter = TokenBucket(
            capacity=rate_limit_capacity,
            refill_rate=rate_limit_refill
        )

        logger.info(
            f"AsyncPRAWClient initialized for user {username} "
            f"(rate limit: {rate_limit_capacity} req/min)"
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes Reddit session."""
        await self.reddit.close()

    async def close(self):
        """Close the Reddit session and cleanup resources."""
        await self.reddit.close()
        logger.info("AsyncPRAWClient closed")

    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(ConnectionError, asyncio.TimeoutError, RedditAPIException)
    )
    @retry_on_rate_limit(max_retries=2, base_delay=60.0)
    async def get_new_posts(
        self,
        subreddits: List[str],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch new posts from specified subreddits.

        See IRedditClient.get_new_posts for full documentation.
        """
        if not subreddits:
            raise ValueError("Subreddits list cannot be empty")
        if limit < 1 or limit > 100:
            raise ValueError(f"Limit must be 1-100, got {limit}")

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        posts = []

        for subreddit_name in subreddits:
            try:
                subreddit = await self.reddit.subreddit(subreddit_name)

                # Fetch new posts
                async for submission in subreddit.new(limit=limit):
                    try:
                        post_dict = await self._submission_to_dict(submission)
                        if post_dict:  # Filter out None (deleted/removed)
                            posts.append(post_dict)
                    except Exception as e:
                        logger.warning(
                            f"Failed to process submission {submission.id} "
                            f"in r/{subreddit_name}: {e}"
                        )
                        continue

            except (ConnectionError, asyncio.TimeoutError, RedditAPIException):
                # Re-raise transient errors to trigger retry decorator
                raise
            except Exception as e:
                # Log and continue for non-retryable errors (e.g., subreddit not found)
                logger.error(f"Failed to fetch posts from r/{subreddit_name}: {e}")
                # Continue with other subreddits
                continue

        logger.info(f"Fetched {len(posts)} posts from {len(subreddits)} subreddits")
        return posts

    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(ConnectionError, asyncio.TimeoutError, RedditAPIException)
    )
    @retry_on_rate_limit(max_retries=2, base_delay=60.0)
    async def search_posts(
        self,
        query: str,
        subreddit: Optional[str] = None,
        time_filter: str = "day",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for posts matching a query.

        See IRedditClient.search_posts for full documentation.
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        valid_time_filters = ["hour", "day", "week", "month", "year", "all"]
        if time_filter not in valid_time_filters:
            raise ValueError(
                f"Invalid time_filter '{time_filter}'. "
                f"Must be one of: {', '.join(valid_time_filters)}"
            )

        if limit < 1 or limit > 100:
            raise ValueError(f"Limit must be 1-100, got {limit}")

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        posts = []

        try:
            # Search in specific subreddit or all of Reddit
            if subreddit:
                search_target = await self.reddit.subreddit(subreddit)
            else:
                search_target = await self.reddit.subreddit("all")

            # Perform search
            async for submission in search_target.search(
                query,
                time_filter=time_filter,
                limit=limit
            ):
                try:
                    post_dict = await self._submission_to_dict(submission)
                    if post_dict:
                        posts.append(post_dict)
                except Exception as e:
                    logger.warning(
                        f"Failed to process search result {submission.id}: {e}"
                    )
                    continue

        except (ConnectionError, asyncio.TimeoutError, RedditAPIException):
            # Re-raise transient errors to trigger retry decorator
            raise
        except Exception as e:
            location = f"r/{subreddit}" if subreddit else "all of Reddit"
            logger.error(f"Search failed for '{query}' in {location}: {e}")
            raise ConnectionError(f"Reddit search failed: {e}") from e

        logger.info(
            f"Search '{query}' returned {len(posts)} results "
            f"(filter: {time_filter}, limit: {limit})"
        )
        return posts

    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(ConnectionError, asyncio.TimeoutError, RedditAPIException)
    )
    @retry_on_rate_limit(max_retries=2, base_delay=60.0)
    async def submit_post(
        self,
        subreddit: str,
        title: str,
        content: str,
        flair_id: Optional[str] = None
    ) -> str:
        """
        Submit a new post to a subreddit.

        See IRedditClient.submit_post for full documentation.
        """
        if not title or len(title) > 300:
            raise ValueError(f"Title must be 1-300 characters, got {len(title)}")
        if len(content) > 40000:
            raise ValueError(f"Content must be <= 40000 characters, got {len(content)}")

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        try:
            target_subreddit = await self.reddit.subreddit(subreddit)

            # Submit post
            submission = await target_subreddit.submit(
                title=title,
                selftext=content,
                flair_id=flair_id
            )

            reddit_id = f"t3_{submission.id}"

            logger.info(
                f"Posted to r/{subreddit}: '{title[:50]}...' (ID: {reddit_id})"
            )

            return reddit_id

        except RedditAPIException as e:
            # Transform Reddit API errors to appropriate exceptions
            # Get error_type from the first item (RedditErrorItem)
            error_type = e.items[0].error_type if e.items else str(e)

            if any(term in error_type.lower() for term in ['banned', 'restricted', 'forbidden', 'notallowed']):
                raise PermissionError(
                    f"Cannot post to r/{subreddit}: {error_type}"
                ) from e
            elif 'not found' in error_type.lower():
                raise ValueError(f"Subreddit r/{subreddit} not found") from e
            else:
                raise ConnectionError(f"Failed to post: {error_type}") from e

        except Exception as e:
            logger.error(f"Unexpected error posting to r/{subreddit}: {e}")
            raise ConnectionError(f"Failed to post: {e}") from e

    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(ConnectionError, asyncio.TimeoutError, RedditAPIException)
    )
    @retry_on_rate_limit(max_retries=2, base_delay=60.0)
    async def reply(
        self,
        parent_id: str,
        content: str
    ) -> str:
        """
        Reply to a post or comment.

        See IRedditClient.reply for full documentation.
        """
        if not parent_id or not parent_id.startswith(('t1_', 't3_')):
            raise ValueError(
                f"Invalid parent_id format: '{parent_id}'. "
                "Must start with 't1_' (comment) or 't3_' (post)"
            )

        if not content or len(content) > 10000:
            raise ValueError(f"Content must be 1-10000 characters, got {len(content)}")

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        try:
            # Fetch parent (comment or submission)
            if parent_id.startswith('t1_'):
                parent = await self.reddit.comment(parent_id[3:])
            else:  # t3_
                parent = await self.reddit.submission(parent_id[3:])

            # Submit reply
            comment = await parent.reply(content)

            reddit_id = f"t1_{comment.id}"

            parent_type = "comment" if parent_id.startswith('t1_') else "post"
            logger.info(
                f"Replied to {parent_type} {parent_id}: "
                f"'{content[:50]}...' (ID: {reddit_id})"
            )

            return reddit_id

        except RedditAPIException as e:
            # Get error_type from the first item (RedditErrorItem)
            error_type = e.items[0].error_type if e.items else str(e)

            if any(term in error_type.lower() for term in ['locked', 'archived']):
                raise PermissionError(
                    f"Cannot reply to {parent_id}: thread is locked or archived"
                ) from e
            elif 'deleted' in error_type.lower() or 'removed' in error_type.lower():
                raise PermissionError(
                    f"Cannot reply to {parent_id}: parent is deleted or removed"
                ) from e
            elif any(term in error_type.lower() for term in ['banned', 'restricted']):
                raise PermissionError(
                    f"Cannot reply: account is banned or restricted"
                ) from e
            else:
                raise ConnectionError(f"Failed to reply: {error_type}") from e

        except Exception as e:
            logger.error(f"Unexpected error replying to {parent_id}: {e}")
            raise ConnectionError(f"Failed to reply: {e}") from e

    async def validate_credentials(self) -> bool:
        """
        Validate Reddit API credentials.

        See IRedditClient.validate_credentials for full documentation.
        """
        try:
            # Make a lightweight API call to test auth
            user = await self.reddit.user.me()

            if user:
                logger.info(f"Credentials validated for user: {user.name}")
                return True
            else:
                logger.error("Credentials validation failed: no user returned")
                return False

        except Exception as e:
            logger.error(f"Credentials validation failed: {e}")
            return False

    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(ConnectionError, asyncio.TimeoutError, RedditAPIException)
    )
    @retry_on_rate_limit(max_retries=2, base_delay=60.0)
    async def get_inbox_replies(
        self,
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Fetch comment replies from inbox.

        See IRedditClient.get_inbox_replies for full documentation.
        """
        if limit < 1 or limit > 100:
            raise ValueError(f"Limit must be 1-100, got {limit}")

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        replies = []

        try:
            # Fetch comment replies from inbox
            async for item in self.reddit.inbox.comment_replies(limit=limit):
                try:
                    reply_dict = await self._comment_to_dict(item)
                    if reply_dict:
                        # Add inbox-specific fields
                        reply_dict["is_new"] = item.new
                        reply_dict["context"] = getattr(item, "context", "")
                        replies.append(reply_dict)
                except Exception as e:
                    logger.warning(
                        f"Failed to process inbox reply {item.id}: {e}"
                    )
                    continue

        except (ConnectionError, asyncio.TimeoutError, RedditAPIException):
            # Re-raise transient errors to trigger retry decorator
            raise
        except Exception as e:
            logger.error(f"Failed to fetch inbox replies: {e}")
            raise ConnectionError(f"Failed to fetch inbox replies: {e}") from e

        logger.info(f"Fetched {len(replies)} inbox replies")
        return replies

    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(ConnectionError, asyncio.TimeoutError, RedditAPIException)
    )
    @retry_on_rate_limit(max_retries=2, base_delay=60.0)
    async def get_mentions(
        self,
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Fetch username mentions from inbox.

        See IRedditClient.get_mentions for full documentation.
        """
        if limit < 1 or limit > 100:
            raise ValueError(f"Limit must be 1-100, got {limit}")

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        mentions = []

        try:
            # Fetch username mentions from inbox
            async for item in self.reddit.inbox.mentions(limit=limit):
                try:
                    mention_dict = await self._comment_to_dict(item)
                    if mention_dict:
                        # Add inbox-specific fields
                        mention_dict["is_new"] = item.new
                        mention_dict["context"] = getattr(item, "context", "")
                        mentions.append(mention_dict)
                except Exception as e:
                    logger.warning(
                        f"Failed to process mention {item.id}: {e}"
                    )
                    continue

        except (ConnectionError, asyncio.TimeoutError, RedditAPIException):
            # Re-raise transient errors to trigger retry decorator
            raise
        except Exception as e:
            logger.error(f"Failed to fetch mentions: {e}")
            raise ConnectionError(f"Failed to fetch mentions: {e}") from e

        logger.info(f"Fetched {len(mentions)} mentions")
        return mentions

    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(ConnectionError, asyncio.TimeoutError, RedditAPIException)
    )
    @retry_on_rate_limit(max_retries=2, base_delay=60.0)
    async def mark_read(
        self,
        item_ids: List[str]
    ) -> None:
        """
        Mark inbox items as read.

        See IRedditClient.mark_read for full documentation.
        """
        if not item_ids:
            raise ValueError("item_ids cannot be empty")

        # Validate all IDs have valid format
        for item_id in item_ids:
            if not item_id or not item_id.startswith('t1_'):
                raise ValueError(
                    f"Invalid item_id format: '{item_id}'. Must start with 't1_'"
                )

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        try:
            # Fetch the actual comment objects for marking as read
            items_to_mark = []
            for item_id in item_ids:
                comment = await self.reddit.comment(item_id[3:])
                items_to_mark.append(comment)

            # Mark items as read
            if items_to_mark:
                await self.reddit.inbox.mark_read(items_to_mark)

            logger.info(f"Marked {len(item_ids)} inbox items as read")

        except (ConnectionError, asyncio.TimeoutError, RedditAPIException):
            # Re-raise transient errors to trigger retry decorator
            raise
        except Exception as e:
            logger.error(f"Failed to mark items as read: {e}")
            raise ConnectionError(f"Failed to mark items as read: {e}") from e

    @retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(ConnectionError, asyncio.TimeoutError, RedditAPIException)
    )
    @retry_on_rate_limit(max_retries=2, base_delay=60.0)
    async def get_comment(
        self,
        comment_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific comment by ID.

        See IRedditClient.get_comment for full documentation.
        """
        # Strip t1_ prefix if present
        if comment_id.startswith('t1_'):
            comment_id = comment_id[3:]

        # Acquire rate limit token
        await self.rate_limiter.acquire()

        try:
            comment = await self.reddit.comment(comment_id)

            # Force fetch to load comment data
            await comment.load()

            return await self._comment_to_dict(comment)

        except (ConnectionError, asyncio.TimeoutError, RedditAPIException):
            # Re-raise transient errors to trigger retry decorator
            raise
        except Exception as e:
            logger.warning(f"Failed to fetch comment {comment_id}: {e}")
            return None

    async def _comment_to_dict(
        self,
        comment: Comment
    ) -> Optional[Dict[str, Any]]:
        """
        Convert asyncpraw Comment to dictionary.

        Handles deleted/removed comments gracefully and extracts
        relevant fields for the agent.

        Args:
            comment: asyncpraw Comment object

        Returns:
            Dictionary with comment data, or None if comment is deleted/removed

        Note:
            - Filters out deleted/removed content
            - Filters out suspended user comments
            - Extracts only fields relevant to the agent
        """
        try:
            # Check if comment is deleted or removed
            if comment.body in ['[deleted]', '[removed]']:
                return None

            # Check if author is suspended or deleted
            if comment.author is None or str(comment.author) == '[deleted]':
                return None

            # Extract comment data
            return {
                'id': comment.id,
                'body': comment.body or '',
                'author': str(comment.author),
                'parent_id': comment.parent_id,
                'link_id': comment.link_id,
                'subreddit': str(comment.subreddit),
                'created_utc': int(comment.created_utc),
                'score': comment.score,
                'permalink': comment.permalink,
            }

        except Exception as e:
            logger.warning(f"Failed to convert comment to dict: {e}")
            return None

    async def _submission_to_dict(
        self,
        submission: Submission
    ) -> Optional[Dict[str, Any]]:
        """
        Convert asyncpraw Submission to dictionary.

        Handles deleted/removed posts gracefully and extracts
        relevant fields for the agent.

        Args:
            submission: asyncpraw Submission object

        Returns:
            Dictionary with post data, or None if post is deleted/removed

        Note:
            - Filters out deleted/removed content
            - Filters out suspended user posts
            - Extracts only fields relevant to the agent
        """
        try:
            # Check if post is deleted or removed
            if submission.selftext in ['[deleted]', '[removed]']:
                return None

            # Check if author is suspended or deleted
            if submission.author is None or str(submission.author) == '[deleted]':
                return None

            # Extract post data
            return {
                'id': submission.id,
                'title': submission.title or '',
                'selftext': submission.selftext or '',
                'author': str(submission.author),
                'score': submission.score,
                'url': submission.url,
                'subreddit': str(submission.subreddit),
                'created_utc': int(submission.created_utc),
                'num_comments': submission.num_comments,
                'is_self': submission.is_self,
                'permalink': submission.permalink,
                'link_flair_text': submission.link_flair_text or '',
                'over_18': submission.over_18
            }

        except Exception as e:
            logger.warning(f"Failed to convert submission to dict: {e}")
            return None
