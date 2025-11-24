"""
Tests for Agent Decision Loop Core

Tests all phases of the agent loop:
- Initialization and dependency injection
- Perception phase (post monitoring)
- Decision phase (should_respond logic)
- Retrieval integration
- Draft generation via LLM
- Consistency checking
- Moderation and action decisions
- Error handling and exponential backoff
- Complete end-to-end cycle

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
    """Mock Reddit client."""
    client = AsyncMock()
    client.get_new_posts = AsyncMock(return_value=[])
    client.reply = AsyncMock(return_value="t1_mock123")
    return client


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    client = AsyncMock()
    client.generate_response = AsyncMock(return_value={
        "text": "This is a test response.",
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
        "thread": {"title": "Test Post", "subreddit": "test"},
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
        interval_seconds=1,  # Short interval for tests
        max_posts_per_cycle=5,
        response_probability=1.0  # Always respond in tests
    )


# ============================================================================
# Test AgentLoop Initialization
# ============================================================================

@pytest.mark.anyio
async def test_agent_loop_initialization(agent_loop):
    """Test AgentLoop initializes correctly with dependencies."""
    # Arrange - already done by fixture

    # Act - check attributes

    # Assert
    assert agent_loop.interval_seconds == 1
    assert agent_loop.max_posts_per_cycle == 5
    assert agent_loop.response_probability == 1.0
    assert agent_loop._consecutive_errors == 0
    assert agent_loop._max_consecutive_errors == 5
    assert not agent_loop._stop_event.is_set()


# ============================================================================
# Test Perception Phase
# ============================================================================

@pytest.mark.anyio
async def test_perceive_returns_unseen_posts(agent_loop, mock_reddit_client, mock_memory_store):
    """Test perceive phase returns only unseen posts."""
    # Arrange
    persona_id = "persona-123"
    mock_posts = [
        {"id": "post1", "title": "Test 1", "author": "user1", "subreddit": "test"},
        {"id": "post2", "title": "Test 2", "author": "user2", "subreddit": "test"},
    ]
    mock_reddit_client.get_new_posts.return_value = mock_posts
    # post1 has been seen, post2 hasn't
    async def mock_search(persona_id, reddit_id):
        if reddit_id == "post1":
            return [{"id": "interaction-1"}]  # Already seen
        return []  # Not seen

    mock_memory_store.search_interactions.side_effect = mock_search

    # Act
    unseen_posts = await agent_loop.perceive(persona_id)

    # Assert
    assert len(unseen_posts) == 1
    assert unseen_posts[0]["id"] == "post2"
    mock_reddit_client.get_new_posts.assert_called_once_with(
        subreddits=["testsubreddit"],
        limit=10
    )


@pytest.mark.anyio
async def test_perceive_returns_empty_when_no_subreddits(agent_loop, mock_memory_store):
    """Test perceive returns empty list when no target subreddits configured."""
    # Arrange
    persona_id = "persona-123"
    mock_memory_store.get_persona.return_value = {
        "id": persona_id,
        "reddit_username": "test_bot",
        "config": {
            "target_subreddits": []  # Empty
        }
    }

    # Act
    unseen_posts = await agent_loop.perceive(persona_id)

    # Assert
    assert unseen_posts == []


# ============================================================================
# Test Decision Phase (should_respond)
# ============================================================================

@pytest.mark.anyio
async def test_should_respond_skips_own_posts(agent_loop, mock_memory_store):
    """Test should_respond returns False for own posts."""
    # Arrange
    persona_id = "persona-123"
    post = {
        "id": "post1",
        "author": "test_bot",  # Same as persona username
        "title": "Test Post",
        "selftext": "Content"
    }

    # Act
    result = await agent_loop.should_respond(persona_id, post)

    # Assert
    assert result is False


@pytest.mark.anyio
async def test_should_respond_checks_interest_keywords(agent_loop, mock_memory_store):
    """Test should_respond filters by interest keywords when configured."""
    # Arrange
    persona_id = "persona-123"
    mock_memory_store.get_persona.return_value = {
        "id": persona_id,
        "reddit_username": "test_bot",
        "config": {
            "interest_keywords": ["python", "coding"]
        }
    }

    # Post without matching keywords
    post_no_match = {
        "id": "post1",
        "author": "other_user",
        "title": "Random Topic",
        "selftext": "About something else"
    }

    # Post with matching keyword
    post_match = {
        "id": "post2",
        "author": "other_user",
        "title": "Python Question",
        "selftext": "Help with coding"
    }

    # Act
    result_no_match = await agent_loop.should_respond(persona_id, post_no_match)
    result_match = await agent_loop.should_respond(persona_id, post_match)

    # Assert
    assert result_no_match is False
    assert result_match is True


@pytest.mark.anyio
async def test_should_respond_accepts_when_no_keywords(agent_loop, mock_memory_store):
    """Test should_respond accepts posts when no interest keywords configured."""
    # Arrange
    persona_id = "persona-123"
    post = {
        "id": "post1",
        "author": "other_user",
        "title": "Any Topic",
        "selftext": "Any content"
    }

    # Act
    result = await agent_loop.should_respond(persona_id, post)

    # Assert
    assert result is True  # Should accept (with probability 1.0 in fixture)


# ============================================================================
# Test Draft Generation
# ============================================================================

@pytest.mark.anyio
async def test_generate_draft_calls_llm(agent_loop, mock_llm_client, mock_retrieval, mock_memory_store):
    """Test generate_draft calls LLM with correct parameters."""
    # Arrange
    persona_id = "persona-123"
    context = {
        "beliefs": [],
        "past_statements": [],
        "thread": {"title": "Test", "subreddit": "test"}
    }
    correlation_id = "test-correlation-id"

    # Act
    draft = await agent_loop.generate_draft(persona_id, context, correlation_id)

    # Assert
    assert draft["text"] == "This is a test response."
    assert draft["tokens_in"] == 100
    assert draft["tokens_out"] == 20
    assert draft["cost"] == 0.01
    mock_llm_client.generate_response.assert_called_once()


# ============================================================================
# Test Consistency Check
# ============================================================================

@pytest.mark.anyio
async def test_check_draft_consistency_no_beliefs(agent_loop):
    """Test consistency check with no beliefs returns consistent."""
    # Arrange
    draft = "Test draft"
    beliefs = []
    correlation_id = "test-id"

    # Act
    result = await agent_loop.check_draft_consistency(draft, beliefs, correlation_id)

    # Assert
    assert result["is_consistent"] is True
    assert result["conflicts"] == []


@pytest.mark.anyio
async def test_check_draft_consistency_with_beliefs(agent_loop, mock_llm_client):
    """Test consistency check calls LLM when beliefs present."""
    # Arrange
    draft = "Test draft"
    beliefs = [{"id": "belief-1", "title": "Test Belief", "confidence": 0.8}]
    correlation_id = "test-id"

    # Act
    result = await agent_loop.check_draft_consistency(draft, beliefs, correlation_id)

    # Assert
    assert result["is_consistent"] is True
    mock_llm_client.check_consistency.assert_called_once()


# ============================================================================
# Test Moderation
# ============================================================================

@pytest.mark.anyio
async def test_moderate_draft_post_now(agent_loop, mock_moderation):
    """Test moderation returns post_now when auto-posting enabled and approved."""
    # Arrange
    persona_id = "persona-123"
    draft = "Test draft"
    post = {"id": "post1", "subreddit": "test"}
    correlation_id = "test-id"

    # Act
    decision = await agent_loop.moderate_draft(persona_id, draft, post, correlation_id)

    # Assert
    assert decision["action"] == "post_now"
    assert decision["auto_posting_enabled"] is True


@pytest.mark.anyio
async def test_moderate_draft_queue_when_auto_disabled(agent_loop, mock_moderation):
    """Test moderation queues when auto-posting disabled."""
    # Arrange
    persona_id = "persona-123"
    draft = "Test draft"
    post = {"id": "post1", "subreddit": "test"}
    correlation_id = "test-id"
    mock_moderation.is_auto_posting_enabled.return_value = False

    # Act
    decision = await agent_loop.moderate_draft(persona_id, draft, post, correlation_id)

    # Assert
    assert decision["action"] == "queue"


@pytest.mark.anyio
async def test_moderate_draft_drop_when_blocked(agent_loop, mock_moderation):
    """Test moderation drops content when blocked."""
    # Arrange
    persona_id = "persona-123"
    draft = "Test draft"
    post = {"id": "post1", "subreddit": "test"}
    correlation_id = "test-id"
    mock_moderation.evaluate_content.return_value = {
        "approved": False,
        "flagged": True,
        "flags": ["banned_keyword: spam"],
        "action": "block"
    }

    # Act
    decision = await agent_loop.moderate_draft(persona_id, draft, post, correlation_id)

    # Assert
    assert decision["action"] == "drop"


# ============================================================================
# Test Action Execution
# ============================================================================

@pytest.mark.anyio
async def test_execute_action_posts_to_reddit(agent_loop, mock_reddit_client, mock_memory_store):
    """Test execute_action posts to Reddit and logs interaction."""
    # Arrange
    persona_id = "persona-123"
    draft = "Test draft"
    post = {"id": "post1", "subreddit": "test"}
    decision = {"action": "post_now", "evaluation": {}}
    correlation_id = "test-id"

    # Act
    result = await agent_loop.execute_action(persona_id, draft, post, decision, correlation_id)

    # Assert
    assert result.startswith("posted:")
    mock_reddit_client.reply.assert_called_once_with(
        parent_id="t3_post1",
        content=draft
    )
    mock_memory_store.log_interaction.assert_called_once()


@pytest.mark.anyio
async def test_execute_action_enqueues_for_review(agent_loop, mock_moderation):
    """Test execute_action enqueues content when action is queue."""
    # Arrange
    persona_id = "persona-123"
    draft = "Test draft"
    post = {"id": "post1", "subreddit": "test"}
    decision = {"action": "queue", "evaluation": {}}
    correlation_id = "test-id"

    # Act
    result = await agent_loop.execute_action(persona_id, draft, post, decision, correlation_id)

    # Assert
    assert result.startswith("queued:")
    mock_moderation.enqueue_for_review.assert_called_once()


@pytest.mark.anyio
async def test_execute_action_drops_content(agent_loop):
    """Test execute_action drops content when action is drop."""
    # Arrange
    persona_id = "persona-123"
    draft = "Test draft"
    post = {"id": "post1", "subreddit": "test"}
    decision = {
        "action": "drop",
        "evaluation": {"flags": ["banned_keyword"]}
    }
    correlation_id = "test-id"

    # Act
    result = await agent_loop.execute_action(persona_id, draft, post, decision, correlation_id)

    # Assert
    assert result.startswith("dropped:")
    assert "banned_keyword" in result


@pytest.mark.anyio
async def test_execute_action_falls_back_to_queue_on_reddit_error(
    agent_loop, mock_reddit_client, mock_moderation
):
    """Test execute_action falls back to queueing if Reddit post fails."""
    # Arrange
    persona_id = "persona-123"
    draft = "Test draft"
    post = {"id": "post1", "subreddit": "test"}
    decision = {"action": "post_now", "evaluation": {}}
    correlation_id = "test-id"
    mock_reddit_client.reply.side_effect = Exception("Reddit API error")

    # Act
    result = await agent_loop.execute_action(persona_id, draft, post, decision, correlation_id)

    # Assert
    assert result.startswith("queued:")
    mock_moderation.enqueue_for_review.assert_called_once()


# ============================================================================
# Test Error Handling and Backoff
# ============================================================================

@pytest.mark.anyio
async def test_calculate_backoff_increases_exponentially(agent_loop):
    """Test backoff calculation increases exponentially with jitter."""
    # Arrange & Act
    backoff_1 = agent_loop._calculate_backoff(1)
    backoff_2 = agent_loop._calculate_backoff(2)
    backoff_3 = agent_loop._calculate_backoff(3)
    backoff_10 = agent_loop._calculate_backoff(10)

    # Assert
    # 2^1 + jitter = 2-3
    assert 2 <= backoff_1 < 3
    # 2^2 + jitter = 4-5
    assert 4 <= backoff_2 < 5
    # 2^3 + jitter = 8-9
    assert 8 <= backoff_3 < 9
    # Capped at 60
    assert 60 <= backoff_10 < 61


# ============================================================================
# Test Graceful Shutdown
# ============================================================================

@pytest.mark.anyio
async def test_agent_loop_stop_sets_event(agent_loop):
    """Test stop() sets stop event."""
    # Arrange - agent_loop not running

    # Act
    await agent_loop.stop()

    # Assert
    assert agent_loop._stop_event.is_set()


# ============================================================================
# Test System Prompt Building
# ============================================================================

def test_build_system_prompt(agent_loop):
    """Test system prompt building from persona config."""
    # Arrange
    config = {
        "tone": "friendly",
        "style": "casual",
        "values": ["helpful", "honest"]
    }

    # Act
    prompt = agent_loop._build_system_prompt(config)

    # Assert
    assert "friendly" in prompt
    assert "casual" in prompt
    assert "helpful" in prompt
    assert "honest" in prompt
    assert "Reddit" in prompt
    assert "Never" in prompt  # Safety rules section


# ============================================================================
# Test Integration: Full Cycle
# ============================================================================

@pytest.mark.anyio
async def test_full_cycle_integration(
    agent_loop,
    mock_reddit_client,
    mock_llm_client,
    mock_memory_store,
    mock_retrieval,
    mock_moderation
):
    """Test complete agent cycle from perception to action."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"

    # Mock a new post
    mock_reddit_client.get_new_posts.return_value = [
        {
            "id": "post1",
            "title": "Test Post",
            "selftext": "Test content",
            "author": "other_user",
            "subreddit": "test",
            "url": "https://reddit.com/r/test/post1"
        }
    ]

    # Act - execute one cycle
    await agent_loop._execute_cycle(persona_id, correlation_id)

    # Assert - verify all phases called
    mock_reddit_client.get_new_posts.assert_called_once()
    mock_memory_store.search_interactions.assert_called()
    mock_retrieval.assemble_context.assert_called_once()
    mock_llm_client.generate_response.assert_called_once()
    mock_llm_client.check_consistency.assert_called_once()
    mock_moderation.evaluate_content.assert_called_once()
    mock_reddit_client.reply.assert_called_once()
    mock_memory_store.log_interaction.assert_called_once()


@pytest.mark.anyio
async def test_cycle_with_no_posts(agent_loop, mock_reddit_client):
    """Test cycle completes cleanly when no posts found."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"
    mock_reddit_client.get_new_posts.return_value = []

    # Act
    await agent_loop._execute_cycle(persona_id, correlation_id)

    # Assert - cycle should complete without errors
    mock_reddit_client.get_new_posts.assert_called_once()


@pytest.mark.anyio
async def test_cycle_with_ineligible_posts(
    agent_loop, mock_reddit_client, mock_memory_store
):
    """Test cycle completes cleanly when no posts are eligible."""
    # Arrange
    persona_id = "persona-123"
    correlation_id = "test-correlation"

    # Return posts from self (should be filtered)
    mock_reddit_client.get_new_posts.return_value = [
        {
            "id": "post1",
            "title": "My Own Post",
            "selftext": "Content",
            "author": "test_bot",  # Same as persona
            "subreddit": "test"
        }
    ]

    # Act
    await agent_loop._execute_cycle(persona_id, correlation_id)

    # Assert - no drafts should be generated
    mock_reddit_client.get_new_posts.assert_called_once()


# ============================================================================
# Test Input Validation
# ============================================================================

@pytest.mark.anyio
async def test_run_raises_on_invalid_persona_id(agent_loop):
    """Test run() raises ValueError for invalid persona_id."""
    # Arrange
    persona_id = ""

    # Act & Assert
    with pytest.raises(ValueError, match="persona_id is required"):
        await agent_loop.run(persona_id)


@pytest.mark.anyio
async def test_run_raises_when_persona_not_found(agent_loop, mock_memory_store):
    """Test run() raises ValueError when persona doesn't exist."""
    # Arrange
    persona_id = "nonexistent"
    mock_memory_store.get_persona.return_value = None

    # Act & Assert
    with pytest.raises(ValueError, match="Persona not found"):
        await agent_loop.run(persona_id)


@pytest.mark.anyio
async def test_should_respond_raises_on_missing_fields(agent_loop):
    """Test should_respond raises on invalid post dict."""
    # Arrange
    persona_id = "persona-123"
    post = {"id": "post1"}  # Missing 'author'

    # Act & Assert
    with pytest.raises(ValueError, match="must contain 'author' and 'id'"):
        await agent_loop.should_respond(persona_id, post)
