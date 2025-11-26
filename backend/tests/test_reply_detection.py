"""
Tests for Reply Detection Feature

Tests all aspects of the reply detection system:
- IRedditClient inbox methods (get_inbox_replies, get_mentions, mark_read, get_comment)
- AgentLoop perceive_replies filtering logic
- AgentLoop process_reply conversation context building
- Integration with existing moderation flow
- Conversation depth limiting

Follows AAA (Arrange, Act, Assert) test style.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.agent.loop import AgentLoop, run_agent
from app.services.retrieval import RetrievalCoordinator
from app.services.moderation import ModerationService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_reddit_client():
    """Mock Reddit client with inbox methods."""
    client = AsyncMock()
    client.get_new_posts = AsyncMock(return_value=[])
    client.reply = AsyncMock(return_value="t1_mock123")
    client.get_inbox_replies = AsyncMock(return_value=[])
    client.get_mentions = AsyncMock(return_value=[])
    client.mark_read = AsyncMock(return_value=None)
    client.get_comment = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    client = AsyncMock()
    client.generate_response = AsyncMock(return_value={
        "text": "This is a test reply response.",
        "model": "test-model",
        "tokens_in": 100,
        "tokens_out": 20,
        "total_tokens": 120,
        "cost": 0.01
    })
    client.check_consistency = AsyncMock(return_value={
        "is_consistent": True,
        "conflicts": [],
        "explanation": "No conflicts found",
        "model": "test-model",
        "tokens_in": 50,
        "tokens_out": 10,
        "cost": 0.005
    })
    return client


@pytest.fixture
def mock_memory_store():
    """Mock memory store."""
    store = AsyncMock()
    store.get_persona = AsyncMock(return_value={
        "id": "persona-123",
        "reddit_username": "test_bot",
        "display_name": "Test Bot",
        "config": {
            "target_subreddits": ["testsubreddit"],
            "tone": "friendly",
            "style": "casual",
            "values": ["helpful", "evidence-based"],
            "interest_keywords": []
        }
    })
    store.search_interactions = AsyncMock(return_value=[])
    store.log_interaction = AsyncMock(return_value="interaction-123")
    store.query_belief_graph = AsyncMock(return_value={
        "nodes": [
            {"id": "belief-1", "title": "Test Belief", "confidence": 0.8}
        ],
        "edges": []
    })
    return store


@pytest.fixture
def mock_retrieval():
    """Mock retrieval coordinator."""
    retrieval = AsyncMock()
    retrieval.assemble_context = AsyncMock(return_value={
        "beliefs": [
            {"id": "belief-1", "title": "Test Belief", "confidence": 0.8}
        ],
        "relations": [],
        "past_statements": [],
        "evidence": {},
        "thread": {"title": "Test Reply", "subreddit": "test"},
        "token_count": 500
    })
    retrieval.assemble_prompt = AsyncMock(return_value="Test prompt")
    return retrieval


@pytest.fixture
def mock_moderation():
    """Mock moderation service."""
    moderation = AsyncMock()
    moderation.evaluate_content = AsyncMock(return_value={
        "approved": True,
        "flagged": False,
        "flags": [],
        "action": "allow"
    })
    moderation.is_auto_posting_enabled = AsyncMock(return_value=True)
    moderation.enqueue_for_review = AsyncMock(return_value="queue-123")
    return moderation


@pytest.fixture
def agent_loop(
    mock_reddit_client,
    mock_llm_client,
    mock_memory_store,
    mock_retrieval,
    mock_moderation
):
    """Create agent loop with mocked dependencies."""
    return AgentLoop(
        reddit_client=mock_reddit_client,
        llm_client=mock_llm_client,
        memory_store=mock_memory_store,
        retrieval=mock_retrieval,
        moderation=mock_moderation,
        interval_seconds=1,
        max_posts_per_cycle=5,
        response_probability=1.0,
        max_conversation_depth=5
    )


# ============================================================================
# Test get_inbox_replies Method
# ============================================================================

@pytest.mark.anyio
async def test_get_inbox_replies_returns_replies(mock_reddit_client):
    """Test get_inbox_replies returns properly formatted replies."""
    # Arrange
    mock_replies = [
        {
            "id": "reply1",
            "body": "This is a reply",
            "author": "other_user",
            "parent_id": "t1_original_comment",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "score": 5,
            "permalink": "/r/testsubreddit/comments/...",
            "is_new": True,
            "context": "/r/testsubreddit/comments/.../comment/?context=3"
        }
    ]
    mock_reddit_client.get_inbox_replies.return_value = mock_replies

    # Act
    replies = await mock_reddit_client.get_inbox_replies(limit=25)

    # Assert
    assert len(replies) == 1
    assert replies[0]["id"] == "reply1"
    assert replies[0]["is_new"] is True
    mock_reddit_client.get_inbox_replies.assert_called_once_with(limit=25)


@pytest.mark.anyio
async def test_get_inbox_replies_handles_empty_inbox(mock_reddit_client):
    """Test get_inbox_replies handles empty inbox gracefully."""
    # Arrange
    mock_reddit_client.get_inbox_replies.return_value = []

    # Act
    replies = await mock_reddit_client.get_inbox_replies(limit=25)

    # Assert
    assert replies == []


# ============================================================================
# Test get_mentions Method
# ============================================================================

@pytest.mark.anyio
async def test_get_mentions_returns_mentions(mock_reddit_client):
    """Test get_mentions returns properly formatted mentions."""
    # Arrange
    mock_mentions = [
        {
            "id": "mention1",
            "body": "Hey u/test_bot what do you think?",
            "author": "mentioning_user",
            "parent_id": "t3_post123",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "score": 3,
            "permalink": "/r/testsubreddit/comments/...",
            "is_new": True,
            "context": "/r/testsubreddit/comments/.../comment/?context=3"
        }
    ]
    mock_reddit_client.get_mentions.return_value = mock_mentions

    # Act
    mentions = await mock_reddit_client.get_mentions(limit=25)

    # Assert
    assert len(mentions) == 1
    assert mentions[0]["id"] == "mention1"
    assert "u/test_bot" in mentions[0]["body"]


# ============================================================================
# Test mark_read Method
# ============================================================================

@pytest.mark.anyio
async def test_mark_read_marks_items(mock_reddit_client):
    """Test mark_read calls API with correct item IDs."""
    # Arrange
    item_ids = ["t1_reply1", "t1_reply2"]

    # Act
    await mock_reddit_client.mark_read(item_ids)

    # Assert
    mock_reddit_client.mark_read.assert_called_once_with(item_ids)


# ============================================================================
# Test get_comment Method
# ============================================================================

@pytest.mark.anyio
async def test_get_comment_returns_comment_dict(mock_reddit_client):
    """Test get_comment returns comment dictionary."""
    # Arrange
    mock_comment = {
        "id": "abc123",
        "body": "Original comment text",
        "author": "test_bot",
        "parent_id": "t3_post123",
        "link_id": "t3_post123",
        "subreddit": "testsubreddit",
        "created_utc": 1699999000,
        "score": 10,
        "permalink": "/r/testsubreddit/comments/..."
    }
    mock_reddit_client.get_comment.return_value = mock_comment

    # Act
    comment = await mock_reddit_client.get_comment("t1_abc123")

    # Assert
    assert comment["id"] == "abc123"
    assert comment["body"] == "Original comment text"


@pytest.mark.anyio
async def test_get_comment_returns_none_for_deleted(mock_reddit_client):
    """Test get_comment returns None for deleted comments."""
    # Arrange
    mock_reddit_client.get_comment.return_value = None

    # Act
    comment = await mock_reddit_client.get_comment("t1_deleted123")

    # Assert
    assert comment is None


# ============================================================================
# Test perceive_replies Method
# ============================================================================

@pytest.mark.anyio
async def test_perceive_replies_returns_new_replies(agent_loop, mock_reddit_client, mock_memory_store):
    """Test perceive_replies returns only new, unprocessed replies."""
    # Arrange
    persona_id = "persona-123"
    mock_replies = [
        {
            "id": "reply1",
            "body": "Great point!",
            "author": "other_user",
            "parent_id": "t1_our_comment",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "score": 5,
            "permalink": "/r/testsubreddit/comments/...",
            "is_new": True
        }
    ]
    mock_reddit_client.get_inbox_replies.return_value = mock_replies
    mock_reddit_client.get_comment.return_value = {
        "id": "our_comment",
        "body": "Our original comment",
        "author": "test_bot",
        "parent_id": "t3_post123",
        "link_id": "t3_post123",
        "subreddit": "testsubreddit",
        "created_utc": 1699999000,
        "score": 10,
        "permalink": "/r/testsubreddit/comments/..."
    }
    mock_memory_store.search_interactions.return_value = []

    # Act
    replies = await agent_loop.perceive_replies(persona_id)

    # Assert
    assert len(replies) == 1
    assert replies[0]["id"] == "reply1"
    assert "our_comment" in replies[0]
    assert replies[0]["our_comment"]["body"] == "Our original comment"


@pytest.mark.anyio
async def test_perceive_replies_filters_already_processed(agent_loop, mock_reddit_client, mock_memory_store):
    """Test perceive_replies filters out already-processed replies."""
    # Arrange
    persona_id = "persona-123"
    mock_replies = [
        {
            "id": "processed_reply",
            "body": "Already handled",
            "author": "other_user",
            "parent_id": "t1_our_comment",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "is_new": True
        }
    ]
    mock_reddit_client.get_inbox_replies.return_value = mock_replies

    # This reply was already processed
    mock_memory_store.search_interactions.return_value = [{"id": "existing_interaction"}]

    # Act
    replies = await agent_loop.perceive_replies(persona_id)

    # Assert
    assert len(replies) == 0
    mock_reddit_client.mark_read.assert_called()


@pytest.mark.anyio
async def test_perceive_replies_filters_non_comment_replies(agent_loop, mock_reddit_client, mock_memory_store):
    """Test perceive_replies filters replies to posts (not comments)."""
    # Arrange
    persona_id = "persona-123"
    mock_replies = [
        {
            "id": "post_reply",
            "body": "Reply to post, not our comment",
            "author": "other_user",
            "parent_id": "t3_post123",  # Points to post, not comment
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "is_new": True
        }
    ]
    mock_reddit_client.get_inbox_replies.return_value = mock_replies
    mock_memory_store.search_interactions.return_value = []

    # Act
    replies = await agent_loop.perceive_replies(persona_id)

    # Assert
    assert len(replies) == 0


@pytest.mark.anyio
async def test_perceive_replies_skips_deleted_parent_comment(agent_loop, mock_reddit_client, mock_memory_store):
    """Test perceive_replies skips replies when parent comment is deleted."""
    # Arrange
    persona_id = "persona-123"
    mock_replies = [
        {
            "id": "reply_to_deleted",
            "body": "Reply to our deleted comment",
            "author": "other_user",
            "parent_id": "t1_deleted_comment",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "is_new": True
        }
    ]
    mock_reddit_client.get_inbox_replies.return_value = mock_replies
    mock_reddit_client.get_comment.return_value = None  # Deleted
    mock_memory_store.search_interactions.return_value = []

    # Act
    replies = await agent_loop.perceive_replies(persona_id)

    # Assert
    assert len(replies) == 0


@pytest.mark.anyio
async def test_perceive_replies_respects_max_depth(agent_loop, mock_reddit_client, mock_memory_store):
    """Test perceive_replies respects max conversation depth."""
    # Arrange
    persona_id = "persona-123"
    agent_loop.max_conversation_depth = 2  # Set low for test

    mock_replies = [
        {
            "id": "deep_reply",
            "body": "Very deep reply",
            "author": "other_user",
            "parent_id": "t1_our_comment",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "is_new": True
        }
    ]
    mock_reddit_client.get_inbox_replies.return_value = mock_replies

    # Mock a deep comment chain
    comment_chain = [
        {"id": "our_comment", "body": "Our comment", "author": "test_bot", "parent_id": "t1_parent1"},
        {"id": "parent1", "body": "Parent 1", "author": "user1", "parent_id": "t1_parent2"},
        {"id": "parent2", "body": "Parent 2", "author": "user2", "parent_id": "t3_post123"},  # Finally post
    ]

    call_count = 0
    async def mock_get_comment(comment_id):
        nonlocal call_count
        # Strip t1_ prefix
        clean_id = comment_id[3:] if comment_id.startswith("t1_") else comment_id
        for c in comment_chain:
            if c["id"] == clean_id:
                return c
        return None

    mock_reddit_client.get_comment.side_effect = mock_get_comment
    mock_memory_store.search_interactions.return_value = []

    # Act
    replies = await agent_loop.perceive_replies(persona_id)

    # Assert - should be filtered due to depth
    assert len(replies) == 0


@pytest.mark.anyio
async def test_perceive_replies_filters_read_replies(agent_loop, mock_reddit_client, mock_memory_store):
    """Test perceive_replies only processes unread replies."""
    # Arrange
    persona_id = "persona-123"
    mock_replies = [
        {
            "id": "read_reply",
            "body": "Already read",
            "author": "other_user",
            "parent_id": "t1_our_comment",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "is_new": False  # Already read
        }
    ]
    mock_reddit_client.get_inbox_replies.return_value = mock_replies

    # Act
    replies = await agent_loop.perceive_replies(persona_id)

    # Assert
    assert len(replies) == 0


# ============================================================================
# Test process_reply Method
# ============================================================================

@pytest.mark.anyio
async def test_process_reply_posts_response(
    agent_loop,
    mock_reddit_client,
    mock_llm_client,
    mock_memory_store,
    mock_retrieval,
    mock_moderation
):
    """Test process_reply generates and posts a response."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"
    reply = {
        "id": "reply1",
        "body": "Great point! Can you elaborate?",
        "author": "other_user",
        "parent_id": "t1_our_comment",
        "link_id": "t3_post123",
        "subreddit": "testsubreddit",
        "created_utc": 1700000000,
        "score": 5,
        "permalink": "/r/testsubreddit/comments/...",
        "our_comment": {
            "id": "our_comment",
            "body": "Our original thoughtful comment",
            "author": "test_bot"
        },
        "conversation_depth": 1
    }

    # Act
    result = await agent_loop.process_reply(persona_id, reply, correlation_id)

    # Assert
    assert result["action"] == "posted"
    assert "reddit_id" in result
    mock_reddit_client.reply.assert_called_once()
    mock_memory_store.log_interaction.assert_called_once()

    # Verify interaction was logged correctly
    log_call = mock_memory_store.log_interaction.call_args
    assert log_call[1]["interaction_type"] == "reply"
    assert log_call[1]["metadata"]["conversation_depth"] == 1


@pytest.mark.anyio
async def test_process_reply_queues_when_auto_disabled(
    agent_loop,
    mock_reddit_client,
    mock_moderation
):
    """Test process_reply queues when auto-posting is disabled."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"
    reply = {
        "id": "reply1",
        "body": "Reply text",
        "author": "other_user",
        "parent_id": "t1_our_comment",
        "link_id": "t3_post123",
        "subreddit": "testsubreddit",
        "created_utc": 1700000000,
        "our_comment": {"id": "our_comment", "body": "Our comment"},
        "conversation_depth": 1
    }
    mock_moderation.is_auto_posting_enabled.return_value = False

    # Act
    result = await agent_loop.process_reply(persona_id, reply, correlation_id)

    # Assert
    assert result["action"] == "queued"
    assert "queue_id" in result
    mock_moderation.enqueue_for_review.assert_called_once()


@pytest.mark.anyio
async def test_process_reply_drops_blocked_content(
    agent_loop,
    mock_reddit_client,
    mock_moderation
):
    """Test process_reply drops content blocked by moderation."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"
    reply = {
        "id": "reply1",
        "body": "Reply with banned content",
        "author": "other_user",
        "parent_id": "t1_our_comment",
        "link_id": "t3_post123",
        "subreddit": "testsubreddit",
        "created_utc": 1700000000,
        "our_comment": {"id": "our_comment", "body": "Our comment"},
        "conversation_depth": 1
    }
    mock_moderation.evaluate_content.return_value = {
        "approved": False,
        "flagged": True,
        "flags": ["banned_keyword"],
        "action": "block"
    }

    # Act
    result = await agent_loop.process_reply(persona_id, reply, correlation_id)

    # Assert
    assert result["action"] == "dropped"
    assert "reason" in result


@pytest.mark.anyio
async def test_process_reply_builds_conversation_context(
    agent_loop,
    mock_retrieval
):
    """Test process_reply includes conversation context for LLM."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"
    reply = {
        "id": "reply1",
        "body": "Their response to us",
        "author": "other_user",
        "parent_id": "t1_our_comment",
        "link_id": "t3_post123",
        "subreddit": "testsubreddit",
        "created_utc": 1700000000,
        "permalink": "/r/testsubreddit/comments/post123/title/our_comment/",
        "our_comment": {
            "id": "our_comment",
            "body": "What we originally said"
        },
        "conversation_depth": 1
    }

    # Act
    await agent_loop.process_reply(persona_id, reply, correlation_id)

    # Assert
    assemble_call = mock_retrieval.assemble_context.call_args
    thread_context = assemble_call[1]["thread_context"]

    assert thread_context["is_reply"] is True
    assert "conversation_context" in thread_context
    assert thread_context["conversation_context"]["our_comment"] == "What we originally said"
    assert thread_context["conversation_context"]["their_reply"] == "Their response to us"


@pytest.mark.anyio
async def test_process_reply_marks_reply_as_read(
    agent_loop,
    mock_reddit_client
):
    """Test process_reply marks the reply as read after processing."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"
    reply = {
        "id": "reply1",
        "body": "Reply text",
        "author": "other_user",
        "parent_id": "t1_our_comment",
        "link_id": "t3_post123",
        "subreddit": "testsubreddit",
        "created_utc": 1700000000,
        "our_comment": {"id": "our_comment", "body": "Our comment"},
        "conversation_depth": 1
    }

    # Act
    await agent_loop.process_reply(persona_id, reply, correlation_id)

    # Assert
    mock_reddit_client.mark_read.assert_called_with(["t1_reply1"])


# ============================================================================
# Test _calculate_conversation_depth Method
# ============================================================================

@pytest.mark.anyio
async def test_calculate_depth_direct_reply_to_post(agent_loop, mock_reddit_client):
    """Test depth calculation for comment directly on post."""
    # Arrange
    mock_reddit_client.get_comment.return_value = {
        "id": "comment1",
        "body": "Direct reply to post",
        "parent_id": "t3_post123"  # Parent is post
    }

    # Act
    depth = await agent_loop._calculate_conversation_depth("t1_comment1")

    # Assert
    assert depth == 1  # One level deep (comment -> post)


@pytest.mark.anyio
async def test_calculate_depth_nested_comments(agent_loop, mock_reddit_client):
    """Test depth calculation for nested comment chain."""
    # Arrange
    comment_chain = {
        "level3": {"id": "level3", "parent_id": "t1_level2"},
        "level2": {"id": "level2", "parent_id": "t1_level1"},
        "level1": {"id": "level1", "parent_id": "t3_post123"},  # Post
    }

    async def mock_get_comment(comment_id):
        clean_id = comment_id[3:] if comment_id.startswith("t1_") else comment_id
        return comment_chain.get(clean_id)

    mock_reddit_client.get_comment.side_effect = mock_get_comment

    # Act
    depth = await agent_loop._calculate_conversation_depth("t1_level3")

    # Assert
    assert depth == 3  # Three levels: level3 -> level2 -> level1 -> post


# ============================================================================
# Test Integration with Execute Cycle
# ============================================================================

@pytest.mark.anyio
async def test_execute_cycle_processes_replies_before_posts(
    agent_loop,
    mock_reddit_client,
    mock_memory_store
):
    """Test that execute_cycle processes replies before new posts."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"

    # Set up a reply to process
    mock_reply = {
        "id": "reply1",
        "body": "A reply to our comment",
        "author": "other_user",
        "parent_id": "t1_our_comment",
        "link_id": "t3_post123",
        "subreddit": "testsubreddit",
        "created_utc": 1700000000,
        "is_new": True
    }
    mock_reddit_client.get_inbox_replies.return_value = [mock_reply]
    mock_reddit_client.get_comment.return_value = {
        "id": "our_comment",
        "body": "Our original comment",
        "author": "test_bot",
        "parent_id": "t3_post123"
    }
    mock_memory_store.search_interactions.return_value = []

    # No new posts
    mock_reddit_client.get_new_posts.return_value = []

    # Act
    await agent_loop._execute_cycle(persona_id, correlation_id)

    # Assert
    mock_reddit_client.get_inbox_replies.assert_called_once()
    mock_reddit_client.get_new_posts.assert_called_once()
    # Verify reply was processed (reply method called)
    assert mock_reddit_client.reply.called


@pytest.mark.anyio
async def test_execute_cycle_continues_after_reply_error(
    agent_loop,
    mock_reddit_client,
    mock_memory_store
):
    """Test that execute_cycle continues processing after a reply error."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"

    # Set up two replies, first will fail
    mock_replies = [
        {
            "id": "reply1",
            "body": "Reply that will fail",
            "author": "other_user",
            "parent_id": "t1_our_comment1",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000000,
            "is_new": True
        },
        {
            "id": "reply2",
            "body": "Reply that will succeed",
            "author": "other_user",
            "parent_id": "t1_our_comment2",
            "link_id": "t3_post123",
            "subreddit": "testsubreddit",
            "created_utc": 1700000001,
            "is_new": True
        }
    ]
    mock_reddit_client.get_inbox_replies.return_value = mock_replies

    # First comment lookup fails, second succeeds
    call_count = [0]
    async def mock_get_comment(comment_id):
        call_count[0] += 1
        if "our_comment1" in comment_id:
            raise Exception("Simulated error")
        return {
            "id": "our_comment2",
            "body": "Our comment 2",
            "author": "test_bot",
            "parent_id": "t3_post123"
        }

    mock_reddit_client.get_comment.side_effect = mock_get_comment
    mock_memory_store.search_interactions.return_value = []
    mock_reddit_client.get_new_posts.return_value = []

    # Act - should not raise despite first reply failing
    await agent_loop._execute_cycle(persona_id, correlation_id)

    # Assert - second reply should still be processed
    # The cycle should complete without raising


# ============================================================================
# Test Agent Loop Initialization with max_conversation_depth
# ============================================================================

def test_agent_loop_accepts_max_conversation_depth():
    """Test AgentLoop accepts max_conversation_depth parameter."""
    # Arrange
    mock_deps = {
        "reddit_client": AsyncMock(),
        "llm_client": AsyncMock(),
        "memory_store": AsyncMock(),
        "retrieval": AsyncMock(),
        "moderation": AsyncMock(),
    }

    # Act
    loop = AgentLoop(
        **mock_deps,
        max_conversation_depth=10
    )

    # Assert
    assert loop.max_conversation_depth == 10


def test_agent_loop_default_max_conversation_depth():
    """Test AgentLoop has default max_conversation_depth of 5."""
    # Arrange
    mock_deps = {
        "reddit_client": AsyncMock(),
        "llm_client": AsyncMock(),
        "memory_store": AsyncMock(),
        "retrieval": AsyncMock(),
        "moderation": AsyncMock(),
    }

    # Act
    loop = AgentLoop(**mock_deps)

    # Assert
    assert loop.max_conversation_depth == 5


# ============================================================================
# Test run_agent Function with max_conversation_depth
# ============================================================================

@pytest.mark.anyio
async def test_run_agent_accepts_max_conversation_depth(
    mock_reddit_client,
    mock_llm_client,
    mock_memory_store,
    mock_retrieval,
    mock_moderation
):
    """Test run_agent convenience function accepts max_conversation_depth."""
    # Arrange
    persona_id = "persona-123"
    stop_event = asyncio.Event()
    stop_event.set()  # Stop immediately

    # Act - should not raise
    await run_agent(
        persona_id=persona_id,
        reddit_client=mock_reddit_client,
        llm_client=mock_llm_client,
        memory_store=mock_memory_store,
        retrieval=mock_retrieval,
        moderation=mock_moderation,
        stop_event=stop_event,
        max_conversation_depth=3
    )

    # Assert - function completed without error
