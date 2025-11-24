"""
Integration tests for all Week 3 services.

Tests memory store, Reddit client, LLM client, and moderation service
working together with real database interactions.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.services.memory_store import SQLiteMemoryStore
from app.services.reddit_client import AsyncPRAWClient
from app.services.llm_client import OpenRouterClient
from app.services.moderation import ModerationService
from app.models.persona import Persona
from app.models.belief import BeliefNode
from app.models.interaction import Interaction
from app.models.agent_config import AgentConfig


class TestMemoryStoreIntegration:
    """Integration tests for memory store with real database."""

    @pytest.mark.anyio
    async def test_belief_graph_operations(self, async_session):
        """Test belief graph queries and updates."""
        # Create persona
        persona = Persona(
            id="test_persona",
            reddit_username="test_user",
            display_name="Test User"
        )
        persona.set_config({"tone": "friendly"})
        async_session.add(persona)
        await async_session.commit()

        # Create memory store
        memory_store = SQLiteMemoryStore(async_session)

        # Add belief nodes
        belief1 = BeliefNode(
            persona_id="test_persona",
            title="Test Belief 1",
            summary="First test belief",
            current_confidence=0.8
        )
        belief1.set_tags(["test", "core"])

        belief2 = BeliefNode(
            persona_id="test_persona",
            title="Test Belief 2",
            summary="Second test belief",
            current_confidence=0.6
        )
        belief2.set_tags(["test"])

        async_session.add_all([belief1, belief2])
        await async_session.commit()

        # Query belief graph
        graph = await memory_store.query_belief_graph("test_persona")

        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) == 2
        assert graph["nodes"][0]["title"] == "Test Belief 1"
        assert graph["nodes"][0]["confidence"] == 0.8

    @pytest.mark.anyio
    async def test_interaction_logging(self, async_session):
        """Test interaction logging and retrieval."""
        # Create persona
        persona = Persona(
            id="test_persona",
            reddit_username="test_user"
        )
        async_session.add(persona)
        await async_session.commit()

        # Create memory store
        memory_store = SQLiteMemoryStore(async_session)

        # Log interaction
        interaction_id = await memory_store.log_interaction(
            persona_id="test_persona",
            content="Test comment about climate change",
            interaction_type="comment",
            metadata={
                "reddit_id": "t1_test123",
                "subreddit": "science",
                "parent_id": "t3_parent"
            }
        )

        assert interaction_id is not None

        # Verify interaction was stored
        interaction = await async_session.get(Interaction, interaction_id)
        assert interaction is not None
        assert interaction.content == "Test comment about climate change"
        assert interaction.interaction_type == "comment"
        assert interaction.reddit_id == "t1_test123"


class TestRedditClientIntegration:
    """Integration tests for Reddit client with mocked asyncpraw."""

    @pytest.mark.anyio
    async def test_fetch_posts_with_rate_limiting(self):
        """Test fetching posts with rate limiting."""
        # Mock asyncpraw
        mock_reddit = AsyncMock()
        mock_subreddit = AsyncMock()
        mock_submission = MagicMock()
        mock_submission.id = "test123"
        mock_submission.title = "Test Post"
        mock_submission.selftext = "Test content"
        mock_submission.author.name = "test_author"
        mock_submission.score = 100
        mock_submission.url = "https://reddit.com/r/test/test123"
        mock_submission.subreddit.display_name = "test"

        mock_subreddit.new = AsyncMock(return_value=[mock_submission])
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)

        with patch('asyncpraw.Reddit', return_value=mock_reddit):
            from app.core.config import settings
            client = AsyncPRAWClient(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT,
                username=settings.REDDIT_USERNAME,
                password=settings.REDDIT_PASSWORD
            )

            # Fetch posts
            posts = await client.get_new_posts(["test"], limit=1)

            assert len(posts) == 1
            assert posts[0]["id"] == "test123"
            assert posts[0]["title"] == "Test Post"


class TestLLMClientIntegration:
    """Integration tests for LLM client with mocked OpenRouter."""

    @pytest.mark.anyio
    async def test_generate_response_with_cost_tracking(self):
        """Test response generation with cost tracking."""
        # Mock OpenAI client
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content="This is a test response."
                )
            )
        ]
        mock_completion.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )
        mock_completion.model = "openai/gpt-3.5-turbo"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_completion
        )

        with patch('openai.AsyncOpenAI', return_value=mock_client):
            from app.core.config import settings
            llm_client = OpenRouterClient(
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                primary_model="openai/gpt-3.5-turbo",
                secondary_model="anthropic/claude-3-haiku"
            )

            result = await llm_client.generate_response(
                system_prompt="You are a helpful assistant",
                context={"topic": "testing"},
                user_message="Write a test response"
            )

            assert "response" in result
            assert result["response"] == "This is a test response."
            assert "tokens" in result
            assert result["tokens"]["total"] == 150
            assert "cost" in result
            assert result["cost"] > 0


class TestModerationServiceIntegration:
    """Integration tests for moderation service."""

    @pytest.mark.anyio
    async def test_content_evaluation(self, async_session):
        """Test content evaluation rules."""
        # Create persona
        persona = Persona(
            id="test_persona",
            reddit_username="test_user"
        )
        async_session.add(persona)
        await async_session.commit()

        # Create moderation service
        mod_service = ModerationService(async_session)

        # Test valid content
        result = await mod_service.evaluate_content(
            persona_id="test_persona",
            content="This is a valid comment about technology.",
            context={"subreddit": "technology"}
        )

        assert result["approved"] is True
        assert result["flagged"] is False
        assert len(result["flags"]) == 0
        assert result["action"] == "allow"

        # Test content too short
        result = await mod_service.evaluate_content(
            persona_id="test_persona",
            content="Hi",
            context={}
        )

        assert result["approved"] is False
        assert result["flagged"] is True
        assert any("too_short" in flag for flag in result["flags"])
        assert result["action"] == "block"

        # Test banned keyword
        result = await mod_service.evaluate_content(
            persona_id="test_persona",
            content="Check out this spam link for casino offers!",
            context={}
        )

        assert result["approved"] is False
        assert result["flagged"] is True
        assert any("banned_keyword" in flag for flag in result["flags"])

    @pytest.mark.anyio
    async def test_moderation_queue(self, async_session):
        """Test enqueueing and retrieving moderation items."""
        # Create persona
        persona = Persona(
            id="test_persona",
            reddit_username="test_user"
        )
        async_session.add(persona)
        await async_session.commit()

        # Create moderation service
        mod_service = ModerationService(async_session)

        # Enqueue content
        item_id = await mod_service.enqueue_for_review(
            persona_id="test_persona",
            content="This is a test comment requiring review.",
            metadata={
                "post_type": "comment",
                "target_subreddit": "test",
                "parent_id": "t3_parent"
            }
        )

        assert item_id is not None

        # Verify item was queued
        from app.models.pending_post import PendingPost
        item = await async_session.get(PendingPost, item_id)
        assert item is not None
        assert item.status == "pending"
        assert item.content == "This is a test comment requiring review."

    @pytest.mark.anyio
    async def test_auto_posting_flag(self, async_session):
        """Test auto-posting flag check."""
        # Create persona
        persona = Persona(
            id="test_persona",
            reddit_username="test_user"
        )
        async_session.add(persona)
        await async_session.commit()

        # Create moderation service
        mod_service = ModerationService(async_session)

        # Check default (should be False)
        is_enabled = await mod_service.is_auto_posting_enabled("test_persona")
        assert is_enabled is False

        # Set auto-posting to True
        config = AgentConfig(
            persona_id="test_persona",
            config_key="auto_posting_enabled",
            config_value="true"
        )
        async_session.add(config)
        await async_session.commit()

        # Check again
        is_enabled = await mod_service.is_auto_posting_enabled("test_persona")
        assert is_enabled is True

    @pytest.mark.anyio
    async def test_posting_decision_logic(self, async_session):
        """Test should_post_immediately decision logic."""
        # Create persona
        persona = Persona(
            id="test_persona",
            reddit_username="test_user"
        )
        async_session.add(persona)
        await async_session.commit()

        # Create moderation service
        mod_service = ModerationService(async_session)

        # Test with auto-posting disabled
        evaluation = {"approved": True, "flagged": False, "flags": []}
        should_post = await mod_service.should_post_immediately(
            "test_persona",
            evaluation
        )
        assert should_post is False  # Auto-posting disabled

        # Enable auto-posting
        config = AgentConfig(
            persona_id="test_persona",
            config_key="auto_posting_enabled"
        )
        config.set_value(True)
        async_session.add(config)
        await async_session.commit()

        # Test with approved content
        should_post = await mod_service.should_post_immediately(
            "test_persona",
            evaluation
        )
        assert should_post is True  # Should post immediately

        # Test with flagged content
        evaluation_flagged = {
            "approved": False,
            "flagged": True,
            "flags": ["some_issue"]
        }
        should_post = await mod_service.should_post_immediately(
            "test_persona",
            evaluation_flagged
        )
        assert should_post is False  # Content flagged, requires review


class TestCrossServiceIntegration:
    """Integration tests across multiple services."""

    @pytest.mark.anyio
    async def test_full_content_workflow(self, async_session):
        """Test full workflow: evaluation -> queue -> approval."""
        # Setup persona
        persona = Persona(
            id="test_persona",
            reddit_username="test_user"
        )
        async_session.add(persona)
        await async_session.commit()

        # Create services
        mod_service = ModerationService(async_session)
        memory_store = SQLiteMemoryStore(async_session)

        # Step 1: Evaluate content
        content = "This is a great post about artificial intelligence."
        evaluation = await mod_service.evaluate_content(
            persona_id="test_persona",
            content=content,
            context={"subreddit": "MachineLearning"}
        )

        assert evaluation["approved"] is True

        # Step 2: If not auto-posting, enqueue for review
        item_id = await mod_service.enqueue_for_review(
            persona_id="test_persona",
            content=content,
            metadata={
                "post_type": "comment",
                "target_subreddit": "MachineLearning",
                "evaluation": evaluation
            }
        )

        # Step 3: After approval, log interaction
        interaction_id = await memory_store.log_interaction(
            persona_id="test_persona",
            content=content,
            interaction_type="comment",
            metadata={
                "reddit_id": "t1_posted123",
                "subreddit": "MachineLearning",
                "moderation_item_id": item_id
            }
        )

        assert interaction_id is not None

        # Verify full chain
        from app.models.pending_post import PendingPost
        pending_item = await async_session.get(PendingPost, item_id)
        assert pending_item is not None

        interaction = await async_session.get(Interaction, interaction_id)
        assert interaction is not None
        assert interaction.content == content
