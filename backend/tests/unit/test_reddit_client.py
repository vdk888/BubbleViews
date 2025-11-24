"""
Unit tests for AsyncPRAWClient.

Tests cover:
- Initialization and credential validation
- get_new_posts with mocked responses
- search_posts with various filters
- submit_post error handling
- reply to posts and comments
- Rate limiting enforcement
- Retry logic and error transformation
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from asyncpraw.exceptions import RedditAPIException

from app.services.reddit_client import AsyncPRAWClient


@pytest.fixture
def mock_reddit():
    """Create a mocked asyncpraw.Reddit instance."""
    with patch('app.services.reddit_client.asyncpraw.Reddit') as mock:
        reddit_instance = AsyncMock()
        mock.return_value = reddit_instance
        yield reddit_instance


@pytest.fixture
def reddit_client(mock_reddit):
    """Create AsyncPRAWClient with mocked Reddit."""
    client = AsyncPRAWClient(
        client_id="test_id",
        client_secret="test_secret",
        user_agent="test_agent:v1.0 (by /u/testuser)",
        username="testuser",
        password="testpass",
        rate_limit_capacity=60,
        rate_limit_refill=1.0
    )
    return client


@pytest.fixture
def mock_submission():
    """Create a mock Reddit submission."""
    submission = Mock()
    submission.id = "abc123"
    submission.title = "Test Post"
    submission.selftext = "Test content"
    submission.author = Mock()
    submission.author.__str__ = Mock(return_value="testauthor")
    submission.score = 42
    submission.url = "https://reddit.com/r/test/comments/abc123"
    submission.subreddit = Mock()
    submission.subreddit.__str__ = Mock(return_value="test")
    submission.created_utc = 1700000000
    submission.num_comments = 5
    submission.is_self = True
    submission.permalink = "/r/test/comments/abc123/test_post"
    submission.link_flair_text = "Discussion"
    submission.over_18 = False
    return submission


class TestAsyncPRAWClientInitialization:
    """Test client initialization."""

    def test_initialization(self, reddit_client):
        """Test client initializes correctly."""
        assert reddit_client is not None
        assert reddit_client.reddit is not None
        assert reddit_client.rate_limiter is not None
        assert reddit_client.rate_limiter.capacity == 60

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_reddit):
        """Test async context manager usage."""
        async with AsyncPRAWClient(
            client_id="test_id",
            client_secret="test_secret",
            user_agent="test_agent",
            username="test",
            password="pass"
        ) as client:
            assert client is not None

        # Verify close was called
        mock_reddit.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_credentials_success(self, reddit_client, mock_reddit):
        """Test credential validation succeeds."""
        mock_user = Mock()
        mock_user.name = "testuser"
        mock_reddit.user.me = AsyncMock(return_value=mock_user)

        result = await reddit_client.validate_credentials()

        assert result is True
        mock_reddit.user.me.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_credentials_failure(self, reddit_client, mock_reddit):
        """Test credential validation fails gracefully."""
        mock_reddit.user.me = AsyncMock(side_effect=Exception("Auth failed"))

        result = await reddit_client.validate_credentials()

        assert result is False


class TestGetNewPosts:
    """Test get_new_posts method."""

    @pytest.mark.asyncio
    async def test_get_new_posts_success(
        self,
        reddit_client,
        mock_reddit,
        mock_submission
    ):
        """Test fetching new posts successfully."""
        # Mock subreddit and submissions
        mock_subreddit = AsyncMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)

        async def mock_new_generator(limit):
            yield mock_submission

        mock_subreddit.new = Mock(return_value=mock_new_generator(10))

        # Call method
        posts = await reddit_client.get_new_posts(["test"], limit=10)

        # Assertions
        assert len(posts) == 1
        assert posts[0]['id'] == "abc123"
        assert posts[0]['title'] == "Test Post"
        assert posts[0]['subreddit'] == "test"
        mock_reddit.subreddit.assert_called_once_with("test")

    @pytest.mark.asyncio
    async def test_get_new_posts_empty_subreddits(self, reddit_client):
        """Test validation fails with empty subreddits list."""
        with pytest.raises(ValueError, match="Subreddits list cannot be empty"):
            await reddit_client.get_new_posts([], limit=10)

    @pytest.mark.asyncio
    async def test_get_new_posts_invalid_limit(self, reddit_client):
        """Test validation fails with invalid limit."""
        with pytest.raises(ValueError, match="Limit must be 1-100"):
            await reddit_client.get_new_posts(["test"], limit=0)

        with pytest.raises(ValueError, match="Limit must be 1-100"):
            await reddit_client.get_new_posts(["test"], limit=101)

    @pytest.mark.asyncio
    async def test_get_new_posts_filters_deleted(
        self,
        reddit_client,
        mock_reddit
    ):
        """Test deleted/removed posts are filtered out."""
        mock_subreddit = AsyncMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)

        # Create deleted submission
        deleted_sub = Mock()
        deleted_sub.id = "deleted1"
        deleted_sub.selftext = "[deleted]"

        async def mock_new_generator(limit):
            yield deleted_sub

        mock_subreddit.new = Mock(return_value=mock_new_generator(10))

        posts = await reddit_client.get_new_posts(["test"], limit=10)

        # Deleted post should be filtered
        assert len(posts) == 0

    @pytest.mark.asyncio
    async def test_get_new_posts_rate_limited(
        self,
        reddit_client,
        mock_reddit,
        mock_submission
    ):
        """Test rate limiting is enforced."""
        mock_subreddit = AsyncMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)

        async def mock_new_generator(limit):
            yield mock_submission

        mock_subreddit.new = Mock(return_value=mock_new_generator(10))

        # Drain rate limiter
        for _ in range(60):
            await reddit_client.rate_limiter.acquire(1)

        # This should wait for token
        posts = await reddit_client.get_new_posts(["test"], limit=10)

        assert len(posts) == 1

    @pytest.mark.asyncio
    async def test_get_new_posts_multiple_subreddits(
        self,
        reddit_client,
        mock_reddit,
        mock_submission
    ):
        """Test fetching from multiple subreddits."""
        mock_subreddit = AsyncMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)

        async def mock_new_generator(limit):
            yield mock_submission

        # Return a fresh generator each time .new() is called
        mock_subreddit.new = Mock(side_effect=lambda limit: mock_new_generator(limit))

        posts = await reddit_client.get_new_posts(["test1", "test2"], limit=5)

        # Should have posts from both subreddits
        assert len(posts) == 2
        assert mock_reddit.subreddit.call_count == 2


class TestSearchPosts:
    """Test search_posts method."""

    @pytest.mark.asyncio
    async def test_search_posts_success(
        self,
        reddit_client,
        mock_reddit,
        mock_submission
    ):
        """Test searching posts successfully."""
        mock_subreddit = AsyncMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)

        async def mock_search_generator(query, time_filter, limit):
            yield mock_submission

        mock_subreddit.search = Mock(return_value=mock_search_generator(
            "test query", "day", 10
        ))

        posts = await reddit_client.search_posts(
            query="test query",
            subreddit="test",
            time_filter="day",
            limit=10
        )

        assert len(posts) == 1
        assert posts[0]['title'] == "Test Post"
        mock_reddit.subreddit.assert_called_once_with("test")

    @pytest.mark.asyncio
    async def test_search_posts_all_reddit(
        self,
        reddit_client,
        mock_reddit,
        mock_submission
    ):
        """Test searching all of Reddit (no subreddit filter)."""
        mock_subreddit = AsyncMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)

        async def mock_search_generator(query, time_filter, limit):
            yield mock_submission

        mock_subreddit.search = Mock(return_value=mock_search_generator(
            "test", "day", 10
        ))

        posts = await reddit_client.search_posts(
            query="test",
            subreddit=None,  # Search all
            time_filter="day",
            limit=10
        )

        assert len(posts) == 1
        mock_reddit.subreddit.assert_called_once_with("all")

    @pytest.mark.asyncio
    async def test_search_posts_empty_query(self, reddit_client):
        """Test validation fails with empty query."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            await reddit_client.search_posts("", subreddit="test")

        with pytest.raises(ValueError, match="Query cannot be empty"):
            await reddit_client.search_posts("   ", subreddit="test")

    @pytest.mark.asyncio
    async def test_search_posts_invalid_time_filter(self, reddit_client):
        """Test validation fails with invalid time filter."""
        with pytest.raises(ValueError, match="Invalid time_filter"):
            await reddit_client.search_posts(
                "test",
                subreddit="test",
                time_filter="invalid"
            )

    @pytest.mark.asyncio
    async def test_search_posts_invalid_limit(self, reddit_client):
        """Test validation fails with invalid limit."""
        with pytest.raises(ValueError, match="Limit must be 1-100"):
            await reddit_client.search_posts("test", limit=0)


class TestSubmitPost:
    """Test submit_post method."""

    @pytest.mark.asyncio
    async def test_submit_post_success(self, reddit_client, mock_reddit):
        """Test submitting a post successfully."""
        mock_subreddit = AsyncMock()
        mock_submission = Mock()
        mock_submission.id = "new123"

        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)
        mock_subreddit.submit = AsyncMock(return_value=mock_submission)

        reddit_id = await reddit_client.submit_post(
            subreddit="test",
            title="Test Post",
            content="Test content"
        )

        assert reddit_id == "t3_new123"
        mock_subreddit.submit.assert_called_once_with(
            title="Test Post",
            selftext="Test content",
            flair_id=None
        )

    @pytest.mark.asyncio
    async def test_submit_post_with_flair(self, reddit_client, mock_reddit):
        """Test submitting a post with flair."""
        mock_subreddit = AsyncMock()
        mock_submission = Mock()
        mock_submission.id = "new123"

        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)
        mock_subreddit.submit = AsyncMock(return_value=mock_submission)

        reddit_id = await reddit_client.submit_post(
            subreddit="test",
            title="Test Post",
            content="Test content",
            flair_id="flair123"
        )

        assert reddit_id == "t3_new123"
        mock_subreddit.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_post_invalid_title(self, reddit_client):
        """Test validation fails with invalid title."""
        with pytest.raises(ValueError, match="Title must be 1-300 characters"):
            await reddit_client.submit_post(
                subreddit="test",
                title="",
                content="content"
            )

        with pytest.raises(ValueError, match="Title must be 1-300 characters"):
            await reddit_client.submit_post(
                subreddit="test",
                title="x" * 301,
                content="content"
            )

    @pytest.mark.asyncio
    async def test_submit_post_invalid_content(self, reddit_client):
        """Test validation fails with invalid content."""
        with pytest.raises(ValueError, match="Content must be <= 40000 characters"):
            await reddit_client.submit_post(
                subreddit="test",
                title="Title",
                content="x" * 40001
            )

    @pytest.mark.asyncio
    async def test_submit_post_banned(self, reddit_client, mock_reddit):
        """Test error handling when banned from subreddit."""
        mock_subreddit = AsyncMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)

        # Simulate ban error - RedditAPIException expects list of (error_type, message, field) tuples
        # The error_type property will be computed from the first item
        error = RedditAPIException(items=[
            ('SUBREDDIT_NOTALLOWED', 'You are banned from this subreddit', '')
        ])
        mock_subreddit.submit = AsyncMock(side_effect=error)

        with pytest.raises(PermissionError, match="Cannot post"):
            await reddit_client.submit_post(
                subreddit="test",
                title="Title",
                content="Content"
            )


class TestReply:
    """Test reply method."""

    @pytest.mark.asyncio
    async def test_reply_to_post(self, reddit_client, mock_reddit):
        """Test replying to a post."""
        mock_submission = AsyncMock()
        mock_comment = Mock()
        mock_comment.id = "reply123"

        mock_reddit.submission = AsyncMock(return_value=mock_submission)
        mock_submission.reply = AsyncMock(return_value=mock_comment)

        reddit_id = await reddit_client.reply(
            parent_id="t3_abc123",
            content="Test reply"
        )

        assert reddit_id == "t1_reply123"
        mock_reddit.submission.assert_called_once_with("abc123")
        mock_submission.reply.assert_called_once_with("Test reply")

    @pytest.mark.asyncio
    async def test_reply_to_comment(self, reddit_client, mock_reddit):
        """Test replying to a comment."""
        mock_comment_parent = AsyncMock()
        mock_comment_reply = Mock()
        mock_comment_reply.id = "reply456"

        mock_reddit.comment = AsyncMock(return_value=mock_comment_parent)
        mock_comment_parent.reply = AsyncMock(return_value=mock_comment_reply)

        reddit_id = await reddit_client.reply(
            parent_id="t1_def456",
            content="Test reply"
        )

        assert reddit_id == "t1_reply456"
        mock_reddit.comment.assert_called_once_with("def456")
        mock_comment_parent.reply.assert_called_once_with("Test reply")

    @pytest.mark.asyncio
    async def test_reply_invalid_parent_id(self, reddit_client):
        """Test validation fails with invalid parent ID."""
        with pytest.raises(ValueError, match="Invalid parent_id format"):
            await reddit_client.reply("invalid", "content")

        with pytest.raises(ValueError, match="Invalid parent_id format"):
            await reddit_client.reply("t2_abc123", "content")  # Wrong type

    @pytest.mark.asyncio
    async def test_reply_invalid_content(self, reddit_client):
        """Test validation fails with invalid content."""
        with pytest.raises(ValueError, match="Content must be 1-10000 characters"):
            await reddit_client.reply("t3_abc123", "")

        with pytest.raises(ValueError, match="Content must be 1-10000 characters"):
            await reddit_client.reply("t3_abc123", "x" * 10001)

    @pytest.mark.asyncio
    async def test_reply_locked_thread(self, reddit_client, mock_reddit):
        """Test error handling for locked threads."""
        mock_submission = AsyncMock()
        mock_reddit.submission = AsyncMock(return_value=mock_submission)

        # Simulate locked error - RedditAPIException expects list of (error_type, message, field) tuples
        error = RedditAPIException(items=[
            ('THREAD_LOCKED', 'This thread has been locked', '')
        ])
        mock_submission.reply = AsyncMock(side_effect=error)

        with pytest.raises(PermissionError, match="thread is locked"):
            await reddit_client.reply("t3_abc123", "Reply")

    @pytest.mark.asyncio
    async def test_reply_deleted_parent(self, reddit_client, mock_reddit):
        """Test error handling for deleted parent."""
        mock_submission = AsyncMock()
        mock_reddit.submission = AsyncMock(return_value=mock_submission)

        # Simulate deleted error - RedditAPIException expects list of (error_type, message, field) tuples
        error = RedditAPIException(items=[
            ('DELETED_COMMENT', 'This comment has been deleted', '')
        ])
        mock_submission.reply = AsyncMock(side_effect=error)

        with pytest.raises(PermissionError, match="deleted or removed"):
            await reddit_client.reply("t3_abc123", "Reply")


class TestSubmissionToDict:
    """Test _submission_to_dict helper method."""

    @pytest.mark.asyncio
    async def test_submission_to_dict_success(
        self,
        reddit_client,
        mock_submission
    ):
        """Test converting submission to dictionary."""
        result = await reddit_client._submission_to_dict(mock_submission)

        assert result is not None
        assert result['id'] == "abc123"
        assert result['title'] == "Test Post"
        assert result['author'] == "testauthor"
        assert result['subreddit'] == "test"

    @pytest.mark.asyncio
    async def test_submission_to_dict_deleted(self, reddit_client):
        """Test filtering deleted submissions."""
        deleted_sub = Mock()
        deleted_sub.selftext = "[deleted]"

        result = await reddit_client._submission_to_dict(deleted_sub)
        assert result is None

    @pytest.mark.asyncio
    async def test_submission_to_dict_removed(self, reddit_client):
        """Test filtering removed submissions."""
        removed_sub = Mock()
        removed_sub.selftext = "[removed]"

        result = await reddit_client._submission_to_dict(removed_sub)
        assert result is None

    @pytest.mark.asyncio
    async def test_submission_to_dict_deleted_author(self, reddit_client):
        """Test filtering submissions with deleted authors."""
        sub = Mock()
        sub.selftext = "Content"
        sub.author = None

        result = await reddit_client._submission_to_dict(sub)
        assert result is None
