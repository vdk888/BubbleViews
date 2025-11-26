"""
Reddit Client Interface (IRedditClient)

Abstract base class defining the contract for Reddit API interactions.
Provides methods for fetching posts, searching, submitting content, and replying.

Implementation guide:
- All methods must be async
- Rate limiting must be enforced (60 requests/minute)
- Exponential backoff with jitter for retries
- Handle deleted/removed posts gracefully
- All exceptions should be caught and transformed to domain errors
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any


class IRedditClient(ABC):
    """
    Abstract interface for Reddit API operations.

    The Reddit client manages:
    1. Fetching new posts from subreddits
    2. Searching posts with filters
    3. Submitting new posts
    4. Replying to posts and comments
    5. Rate limiting and retry logic

    All operations respect Reddit API rate limits and implement
    exponential backoff for transient failures.
    """

    @abstractmethod
    async def get_new_posts(
        self,
        subreddits: List[str],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch new posts from specified subreddits.

        Retrieves the most recent posts from one or more subreddits.
        Posts are returned in reverse chronological order (newest first).

        Args:
            subreddits: List of subreddit names (without r/ prefix)
                Example: ["AskReddit", "Python", "MachineLearning"]
            limit: Maximum number of posts to fetch per subreddit (default: 10)
                Valid range: 1-100

        Returns:
            List of post dictionaries with structure:
            [
                {
                    "id": "abc123",
                    "title": "Post title",
                    "selftext": "Post body text (empty for link posts)",
                    "author": "username",
                    "score": 42,
                    "url": "https://reddit.com/r/subreddit/comments/...",
                    "subreddit": "AskReddit",
                    "created_utc": 1700000000,
                    "num_comments": 15,
                    "is_self": true,
                    "permalink": "/r/AskReddit/comments/abc123/...",
                    "link_flair_text": "Discussion",
                    "over_18": false
                },
                ...
            ]

        Raises:
            ValueError: If subreddits list is empty or limit out of range
            ConnectionError: If Reddit API is unreachable after retries
            PermissionError: If authentication fails or rate limit exceeded

        Note:
            - Deleted/removed posts are filtered out
            - Rate limiting: 60 requests/minute token bucket
            - Retries with exponential backoff: 1s, 2s, 4s (max 3 attempts)
            - Empty posts (no title) are excluded
            - Suspended user posts are handled gracefully
        """
        pass

    @abstractmethod
    async def search_posts(
        self,
        query: str,
        subreddit: Optional[str] = None,
        time_filter: str = "day",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for posts matching a query.

        Searches Reddit posts by keyword, optionally filtered by subreddit
        and time range. Results sorted by relevance.

        Args:
            query: Search query string
                Supports Reddit search operators (e.g., "flair:Discussion")
            subreddit: Optional subreddit to search within
                If None, searches all of Reddit
            time_filter: Time range for results
                Must be one of: "hour", "day", "week", "month", "year", "all"
                Default: "day"
            limit: Maximum number of results (default: 10)
                Valid range: 1-100

        Returns:
            List of post dictionaries (same structure as get_new_posts)
            Ordered by relevance score

        Raises:
            ValueError: If query is empty, invalid time_filter, or limit out of range
            ConnectionError: If Reddit API is unreachable after retries
            PermissionError: If authentication fails or rate limit exceeded

        Note:
            - Rate limited to 60 requests/minute
            - Retries with exponential backoff
            - Empty results return empty list (not an error)
            - Deleted/removed posts filtered out
            - Query is URL-encoded automatically
        """
        pass

    @abstractmethod
    async def submit_post(
        self,
        subreddit: str,
        title: str,
        content: str,
        flair_id: Optional[str] = None
    ) -> str:
        """
        Submit a new post to a subreddit.

        Creates a self-post (text post) in the specified subreddit.
        Returns Reddit ID of created post.

        Args:
            subreddit: Target subreddit name (without r/ prefix)
            title: Post title
                Length: 1-300 characters
            content: Post body text (markdown supported)
                Length: 0-40000 characters
            flair_id: Optional flair template ID
                Must be valid for the subreddit

        Returns:
            Reddit ID of the created post (e.g., "t3_abc123")

        Raises:
            ValueError: If title/content invalid or subreddit not found
            PermissionError: If banned from subreddit or rate limited
            ConnectionError: If Reddit API is unreachable after retries

        Note:
            - Rate limited to 60 requests/minute
            - Retries with exponential backoff
            - Post is immediately visible (no queue)
            - Markdown formatting supported in content
            - Returns full ID including type prefix (t3_)
            - Throws PermissionError for shadowban/temporary ban
        """
        pass

    @abstractmethod
    async def reply(
        self,
        parent_id: str,
        content: str
    ) -> str:
        """
        Reply to a post or comment.

        Creates a comment in response to a submission (post) or another comment.
        Returns Reddit ID of created comment.

        Args:
            parent_id: Reddit fullname of parent
                Format: "t1_xxx" (comment) or "t3_xxx" (post)
                Example: "t3_abc123", "t1_def456"
            content: Comment text (markdown supported)
                Length: 1-10000 characters

        Returns:
            Reddit ID of the created comment (e.g., "t1_xyz789")

        Raises:
            ValueError: If parent_id invalid format or content too long
            PermissionError: If thread locked, deleted, or rate limited
            ConnectionError: If Reddit API is unreachable after retries

        Note:
            - Rate limited to 60 requests/minute
            - Retries with exponential backoff
            - Cannot reply to deleted/removed content
            - Cannot reply to locked threads
            - Markdown formatting supported
            - Returns full ID including type prefix (t1_)
            - Throws PermissionError for banned/shadowbanned accounts
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Validate Reddit API credentials.

        Tests authentication by making a lightweight API call.
        Use this to verify configuration before starting operations.

        Returns:
            True if credentials are valid and API is reachable
            False otherwise

        Note:
            - Does not count against rate limit
            - Should be called at service startup
            - Catches all exceptions and returns False
            - Does not throw errors (safe to call anytime)
        """
        pass

    @abstractmethod
    async def get_inbox_replies(
        self,
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Fetch comment replies from inbox.

        Retrieves replies to the authenticated user's comments.
        Used by the agent loop to detect when users respond to its comments.

        Args:
            limit: Maximum number of replies to fetch (default: 25)
                Valid range: 1-100

        Returns:
            List of reply dictionaries with structure:
            [
                {
                    "id": "abc123",
                    "body": "Reply text content",
                    "author": "replying_username",
                    "parent_id": "t1_parentcomment",
                    "link_id": "t3_postid",
                    "subreddit": "SubredditName",
                    "created_utc": 1700000000,
                    "score": 5,
                    "permalink": "/r/subreddit/comments/...",
                    "is_new": true,
                    "context": "/r/subreddit/comments/.../comment/?context=3"
                },
                ...
            ]

        Raises:
            ValueError: If limit out of range
            ConnectionError: If Reddit API is unreachable after retries
            PermissionError: If authentication fails or rate limit exceeded

        Note:
            - Returns only comment replies (not post replies)
            - Rate limiting: 60 requests/minute token bucket
            - Retries with exponential backoff: 1s, 2s, 4s (max 3 attempts)
            - Deleted/removed replies are filtered out
            - is_new flag indicates unread status
        """
        pass

    @abstractmethod
    async def get_mentions(
        self,
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Fetch username mentions from inbox.

        Retrieves comments that mention the authenticated user's username.
        Useful for detecting when users directly address the agent.

        Args:
            limit: Maximum number of mentions to fetch (default: 25)
                Valid range: 1-100

        Returns:
            List of mention dictionaries with structure:
            [
                {
                    "id": "xyz789",
                    "body": "Comment text mentioning u/username",
                    "author": "mentioning_username",
                    "parent_id": "t3_postid or t1_commentid",
                    "link_id": "t3_postid",
                    "subreddit": "SubredditName",
                    "created_utc": 1700000000,
                    "score": 3,
                    "permalink": "/r/subreddit/comments/...",
                    "is_new": true,
                    "context": "/r/subreddit/comments/.../comment/?context=3"
                },
                ...
            ]

        Raises:
            ValueError: If limit out of range
            ConnectionError: If Reddit API is unreachable after retries
            PermissionError: If authentication fails or rate limit exceeded

        Note:
            - Mentions are identified by u/username patterns
            - Rate limiting: 60 requests/minute token bucket
            - Retries with exponential backoff: 1s, 2s, 4s (max 3 attempts)
            - Deleted/removed mentions are filtered out
            - is_new flag indicates unread status
        """
        pass

    @abstractmethod
    async def mark_read(
        self,
        item_ids: List[str]
    ) -> None:
        """
        Mark inbox items as read.

        Marks specified inbox items (replies, mentions) as read
        to prevent reprocessing in subsequent inbox fetches.

        Args:
            item_ids: List of Reddit fullnames to mark as read
                Format: "t1_xxx" for comments
                Example: ["t1_abc123", "t1_def456"]

        Raises:
            ValueError: If item_ids is empty or contains invalid IDs
            ConnectionError: If Reddit API is unreachable after retries
            PermissionError: If authentication fails

        Note:
            - Idempotent: marking already-read items has no effect
            - Rate limiting: 60 requests/minute token bucket
            - Items must belong to authenticated user's inbox
            - Batch operation: processes all IDs in single API call
        """
        pass

    @abstractmethod
    async def get_comment(
        self,
        comment_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific comment by ID.

        Retrieves details of a single comment. Used for getting
        the agent's original comment when processing replies.

        Args:
            comment_id: Reddit comment ID (with or without t1_ prefix)
                Example: "abc123" or "t1_abc123"

        Returns:
            Comment dictionary if found:
            {
                "id": "abc123",
                "body": "Comment text content",
                "author": "username",
                "parent_id": "t3_postid or t1_commentid",
                "link_id": "t3_postid",
                "subreddit": "SubredditName",
                "created_utc": 1700000000,
                "score": 10,
                "permalink": "/r/subreddit/comments/..."
            }
            Returns None if comment is deleted, removed, or not found.

        Raises:
            ConnectionError: If Reddit API is unreachable after retries
            PermissionError: If rate limit exceeded

        Note:
            - Rate limiting: 60 requests/minute token bucket
            - Retries with exponential backoff
            - Handles deleted/removed comments gracefully (returns None)
        """
        pass
