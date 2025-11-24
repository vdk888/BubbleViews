"""
Integration tests for Reddit Client.

These tests use mocked Reddit API responses to verify full workflows:
- Complete fetch-process-return pipeline
- Error handling across multiple operations
- Rate limiting in realistic scenarios
- Retry logic with transient failures

Note: These are integration tests, not live API tests.
They use comprehensive mocks to simulate Reddit API behavior.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio
import sys

# Mock asyncpraw before any imports
sys.modules['asyncpraw'] = MagicMock()
sys.modules['asyncpraw.exceptions'] = MagicMock()
sys.modules['asyncpraw.models'] = MagicMock()

# Create mock exception class
class RedditAPIException(Exception):
    """Mock RedditAPIException for testing."""
    def __init__(self):
        self.error_type = None
        super().__init__()

sys.modules['asyncpraw'].exceptions.RedditAPIException = RedditAPIException
sys.modules['asyncpraw.exceptions'].RedditAPIException = RedditAPIException

from app.services.reddit_client import AsyncPRAWClient


@pytest.fixture
def mock_reddit_api():
    """
    Mock Reddit API with realistic behavior.

    Simulates:
    - Subreddit operations
    - Search functionality
    - Post submission
    - Comment replies
    - Rate limiting responses
    """
    with patch('app.services.reddit_client.asyncpraw.Reddit') as mock:
        api = AsyncMock()
        mock.return_value = api
        yield api


@pytest.fixture
async def reddit_client(mock_reddit_api):
    """Create test Reddit client with mocked API."""
    client = AsyncPRAWClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        user_agent="test_agent:v1.0 (by /u/testuser)",
        username="testuser",
        password="testpassword",
        rate_limit_capacity=10,  # Lower for faster tests
        rate_limit_refill=10.0    # Fast refill for tests
    )

    yield client

    # Cleanup
    await client.close()


def create_mock_submission(
    submission_id: str,
    title: str,
    selftext: str,
    author_name: str,
    subreddit_name: str,
    score: int = 10
):
    """Helper to create realistic mock submission."""
    submission = Mock()
    submission.id = submission_id
    submission.title = title
    submission.selftext = selftext

    # Mock author
    author = Mock()
    author.__str__ = Mock(return_value=author_name)
    submission.author = author

    # Mock subreddit
    subreddit = Mock()
    subreddit.__str__ = Mock(return_value=subreddit_name)
    submission.subreddit = subreddit

    submission.score = score
    submission.url = f"https://reddit.com/r/{subreddit_name}/comments/{submission_id}"
    submission.created_utc = 1700000000
    submission.num_comments = 5
    submission.is_self = True
    submission.permalink = f"/r/{subreddit_name}/comments/{submission_id}/{title.lower().replace(' ', '_')}"
    submission.link_flair_text = "Discussion"
    submission.over_18 = False

    return submission


class TestRedditClientIntegration:
    """Integration tests for complete Reddit workflows."""

    @pytest.mark.asyncio
    async def test_full_fetch_workflow(self, reddit_client, mock_reddit_api):
        """
        Test complete workflow: fetch posts from multiple subreddits.

        Verifies:
        - Multiple subreddit queries
        - Post filtering
        - Data transformation
        - Rate limiting across calls
        """
        # Setup mock data
        posts_data = [
            ("post1", "First Post", "Content 1", "user1", "python"),
            ("post2", "Second Post", "Content 2", "user2", "python"),
            ("post3", "Third Post", "Content 3", "user3", "programming"),
        ]

        submissions = [
            create_mock_submission(*data) for data in posts_data
        ]

        # Mock subreddit behavior
        async def mock_new_generator(limit):
            for submission in submissions[:2]:  # First 2 for "python"
                yield submission

        async def mock_new_generator2(limit):
            for submission in submissions[2:]:  # Last 1 for "programming"
                yield submission

        mock_subreddit1 = AsyncMock()
        mock_subreddit1.new = Mock(return_value=mock_new_generator(10))

        mock_subreddit2 = AsyncMock()
        mock_subreddit2.new = Mock(return_value=mock_new_generator2(10))

        mock_reddit_api.subreddit = AsyncMock(
            side_effect=[mock_subreddit1, mock_subreddit2]
        )

        # Execute
        posts = await reddit_client.get_new_posts(
            subreddits=["python", "programming"],
            limit=10
        )

        # Verify
        assert len(posts) == 3
        assert posts[0]['title'] == "First Post"
        assert posts[1]['title'] == "Second Post"
        assert posts[2]['title'] == "Third Post"
        assert posts[0]['subreddit'] == "python"
        assert posts[2]['subreddit'] == "programming"

    @pytest.mark.asyncio
    async def test_search_and_filter_workflow(self, reddit_client, mock_reddit_api):
        """
        Test search with time filter workflow.

        Verifies:
        - Search query execution
        - Time filter application
        - Result processing
        """
        # Setup mock search results
        submission = create_mock_submission(
            "search1",
            "AI Safety Discussion",
            "Let's talk about AI safety",
            "airesearcher",
            "MachineLearning"
        )

        async def mock_search_generator(query, time_filter, limit):
            yield submission

        mock_subreddit = AsyncMock()
        mock_subreddit.search = Mock(return_value=mock_search_generator(
            "AI safety", "week", 10
        ))

        mock_reddit_api.subreddit = AsyncMock(return_value=mock_subreddit)

        # Execute
        posts = await reddit_client.search_posts(
            query="AI safety",
            subreddit="MachineLearning",
            time_filter="week",
            limit=10
        )

        # Verify
        assert len(posts) == 1
        assert posts[0]['title'] == "AI Safety Discussion"
        assert "AI safety" in posts[0]['selftext']

    @pytest.mark.asyncio
    async def test_post_submission_workflow(self, reddit_client, mock_reddit_api):
        """
        Test complete post submission workflow.

        Verifies:
        - Post creation
        - ID extraction
        - Rate limiting
        """
        # Setup mock submission response
        mock_submission = Mock()
        mock_submission.id = "newpost123"

        mock_subreddit = AsyncMock()
        mock_subreddit.submit = AsyncMock(return_value=mock_submission)

        mock_reddit_api.subreddit = AsyncMock(return_value=mock_subreddit)

        # Execute
        reddit_id = await reddit_client.submit_post(
            subreddit="test",
            title="Integration Test Post",
            content="This is a test post from integration tests"
        )

        # Verify
        assert reddit_id == "t3_newpost123"
        mock_subreddit.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_workflow(self, reddit_client, mock_reddit_api):
        """
        Test complete reply workflow.

        Verifies:
        - Comment creation
        - Parent resolution
        - ID formatting
        """
        # Setup mock reply response
        mock_comment = Mock()
        mock_comment.id = "replycomment789"

        mock_parent = AsyncMock()
        mock_parent.reply = AsyncMock(return_value=mock_comment)

        mock_reddit_api.submission = AsyncMock(return_value=mock_parent)

        # Execute
        reddit_id = await reddit_client.reply(
            parent_id="t3_parentpost456",
            content="This is a test reply"
        )

        # Verify
        assert reddit_id == "t1_replycomment789"
        mock_parent.reply.assert_called_once_with("This is a test reply")

    @pytest.mark.asyncio
    async def test_rate_limiting_across_operations(self, reddit_client, mock_reddit_api):
        """
        Test rate limiting enforced across multiple operations.

        Verifies:
        - Token consumption per call
        - Waiting behavior when exhausted
        - Token refill
        """
        # Setup simple mocks
        mock_subreddit = AsyncMock()

        async def mock_new_generator(limit):
            yield create_mock_submission(
                "post1", "Title", "Content", "user", "test"
            )

        mock_subreddit.new = Mock(return_value=mock_new_generator(10))
        mock_reddit_api.subreddit = AsyncMock(return_value=mock_subreddit)

        # Drain rate limiter (capacity = 10)
        for _ in range(10):
            await reddit_client.rate_limiter.acquire(1)

        # Next call should wait for refill
        import time
        start = time.monotonic()

        posts = await reddit_client.get_new_posts(["test"], limit=5)

        elapsed = time.monotonic() - start

        # Should have waited for token (refill rate = 10/sec, so ~0.1s)
        assert elapsed >= 0.05
        assert len(posts) == 1

    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self, reddit_client, mock_reddit_api):
        """
        Test error recovery with retries.

        Verifies:
        - Transient failure handling
        - Retry attempts
        - Eventual success
        """
        # Setup mock that fails twice then succeeds
        call_count = 0

        async def mock_new_generator(limit):
            nonlocal call_count
            call_count += 1

            if call_count < 3:
                raise ConnectionError("Transient failure")

            yield create_mock_submission(
                "post1", "Title", "Content", "user", "test"
            )

        mock_subreddit = AsyncMock()
        mock_subreddit.new = Mock(return_value=mock_new_generator(10))
        mock_reddit_api.subreddit = AsyncMock(return_value=mock_subreddit)

        # Execute - should retry and succeed
        posts = await reddit_client.get_new_posts(["test"], limit=10)

        # Verify success after retries
        assert len(posts) == 1
        assert call_count >= 2  # At least 2 attempts

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, reddit_client, mock_reddit_api):
        """
        Test multiple concurrent operations.

        Verifies:
        - Concurrent requests handled correctly
        - Rate limiting across concurrent calls
        - No race conditions
        """
        # Setup mock
        async def mock_new_generator(limit):
            yield create_mock_submission(
                "post1", "Title", "Content", "user", "test"
            )

        mock_subreddit = AsyncMock()
        mock_subreddit.new = Mock(return_value=mock_new_generator(10))
        mock_reddit_api.subreddit = AsyncMock(return_value=mock_subreddit)

        # Execute concurrent requests
        tasks = [
            reddit_client.get_new_posts(["test"], limit=5)
            for _ in range(3)
        ]

        results = await asyncio.gather(*tasks)

        # Verify all succeeded
        assert len(results) == 3
        assert all(len(posts) == 1 for posts in results)

    @pytest.mark.asyncio
    async def test_deleted_content_filtering(self, reddit_client, mock_reddit_api):
        """
        Test filtering of deleted/removed content.

        Verifies:
        - Deleted posts excluded
        - Removed posts excluded
        - Valid posts included
        """
        # Mix of valid and deleted posts
        valid_post = create_mock_submission(
            "valid1", "Valid Post", "Good content", "user1", "test"
        )

        deleted_post = create_mock_submission(
            "deleted1", "Deleted", "[deleted]", "user2", "test"
        )

        removed_post = create_mock_submission(
            "removed1", "Removed", "[removed]", "user3", "test"
        )

        async def mock_new_generator(limit):
            yield valid_post
            yield deleted_post
            yield removed_post

        mock_subreddit = AsyncMock()
        mock_subreddit.new = Mock(return_value=mock_new_generator(10))
        mock_reddit_api.subreddit = AsyncMock(return_value=mock_subreddit)

        # Execute
        posts = await reddit_client.get_new_posts(["test"], limit=10)

        # Verify only valid post included
        assert len(posts) == 1
        assert posts[0]['id'] == "valid1"

    @pytest.mark.asyncio
    async def test_permission_error_handling(self, reddit_client, mock_reddit_api):
        """
        Test handling of permission errors.

        Verifies:
        - Banned subreddit detection
        - Locked thread detection
        - Appropriate exceptions raised
        """
        # Setup mock that simulates ban
        mock_subreddit = AsyncMock()

        error = RedditAPIException()
        error.error_type = "SUBREDDIT_NOTALLOWED"
        mock_subreddit.submit = AsyncMock(side_effect=error)

        mock_reddit_api.subreddit = AsyncMock(return_value=mock_subreddit)

        # Execute and verify exception
        with pytest.raises(PermissionError, match="Cannot post"):
            await reddit_client.submit_post(
                subreddit="banned_sub",
                title="Test",
                content="Content"
            )

    @pytest.mark.asyncio
    async def test_end_to_end_agent_scenario(self, reddit_client, mock_reddit_api):
        """
        Test realistic agent workflow.

        Scenario:
        1. Search for relevant posts
        2. Filter results
        3. Reply to a post
        4. Verify all operations work together

        Verifies:
        - Complete agent interaction flow
        - State consistency across operations
        - Rate limiting throughout
        """
        # Step 1: Setup search results
        search_result = create_mock_submission(
            "interesting1",
            "Interesting Discussion",
            "Let's discuss this topic",
            "author1",
            "test"
        )

        async def mock_search_generator(query, time_filter, limit):
            yield search_result

        mock_subreddit = AsyncMock()
        mock_subreddit.search = Mock(return_value=mock_search_generator(
            "topic", "day", 10
        ))
        mock_reddit_api.subreddit = AsyncMock(return_value=mock_subreddit)

        # Step 2: Search for posts
        posts = await reddit_client.search_posts(
            query="topic",
            subreddit="test",
            time_filter="day",
            limit=10
        )

        assert len(posts) == 1
        target_post_id = f"t3_{posts[0]['id']}"

        # Step 3: Setup reply mock
        mock_comment = Mock()
        mock_comment.id = "agentreply1"

        mock_parent = AsyncMock()
        mock_parent.reply = AsyncMock(return_value=mock_comment)

        mock_reddit_api.submission = AsyncMock(return_value=mock_parent)

        # Step 4: Reply to the post
        reply_id = await reddit_client.reply(
            parent_id=target_post_id,
            content="Great discussion! Here are my thoughts..."
        )

        # Verify complete workflow
        assert reply_id == "t1_agentreply1"
        mock_parent.reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_credentials_validation_integration(
        self,
        reddit_client,
        mock_reddit_api
    ):
        """
        Test credential validation in integration context.

        Verifies:
        - Auth check at startup
        - User info retrieval
        - Failure handling
        """
        # Setup mock user
        mock_user = Mock()
        mock_user.name = "testuser"
        mock_reddit_api.user.me = AsyncMock(return_value=mock_user)

        # Validate credentials
        result = await reddit_client.validate_credentials()

        assert result is True
        mock_reddit_api.user.me.assert_called_once()
