"""
End-to-end persona isolation tests.

Verifies that all operations maintain strict isolation between personas,
ensuring no data leakage across persona boundaries.
"""

import pytest

from app.services.memory_store import SQLiteMemoryStore
from app.services.moderation import ModerationService
from app.models.persona import Persona
from app.models.belief import BeliefNode, BeliefEdge, StanceVersion
from app.models.interaction import Interaction
from app.models.pending_post import PendingPost
from app.models.agent_config import AgentConfig


class TestPersonaIsolationEndToEnd:
    """Comprehensive persona isolation tests across all services."""

    @pytest.mark.anyio
    async def test_belief_graph_isolation(self, async_session):
        """Verify persona A cannot access persona B's beliefs."""
        # Create two personas
        persona_a = Persona(
            id="persona_a",
            reddit_username="user_a",
            display_name="User A"
        )
        persona_b = Persona(
            id="persona_b",
            reddit_username="user_b",
            display_name="User B"
        )
        async_session.add_all([persona_a, persona_b])
        await async_session.commit()

        # Create beliefs for each persona
        belief_a = BeliefNode(
            persona_id="persona_a",
            title="Belief A",
            summary="This belongs to persona A",
            current_confidence=0.9
        )
        belief_b = BeliefNode(
            persona_id="persona_b",
            title="Belief B",
            summary="This belongs to persona B",
            current_confidence=0.8
        )
        async_session.add_all([belief_a, belief_b])
        await async_session.commit()

        # Create memory store
        memory_store = SQLiteMemoryStore(async_session)

        # Query persona A's beliefs
        graph_a = await memory_store.query_belief_graph("persona_a")
        assert len(graph_a["nodes"]) == 1
        assert graph_a["nodes"][0]["title"] == "Belief A"

        # Query persona B's beliefs
        graph_b = await memory_store.query_belief_graph("persona_b")
        assert len(graph_b["nodes"]) == 1
        assert graph_b["nodes"][0]["title"] == "Belief B"

        # Verify no cross-contamination
        assert graph_a["nodes"][0]["id"] != graph_b["nodes"][0]["id"]

    @pytest.mark.anyio
    async def test_interaction_history_isolation(self, async_session):
        """Verify persona A cannot see persona B's interactions."""
        # Create two personas
        persona_a = Persona(id="persona_a", reddit_username="user_a")
        persona_b = Persona(id="persona_b", reddit_username="user_b")
        async_session.add_all([persona_a, persona_b])
        await async_session.commit()

        # Create memory store
        memory_store = SQLiteMemoryStore(async_session)

        # Log interactions for each persona
        await memory_store.log_interaction(
            persona_id="persona_a",
            content="Persona A's comment about topic X",
            interaction_type="comment",
            metadata={"reddit_id": "t1_a_123"}
        )

        await memory_store.log_interaction(
            persona_id="persona_b",
            content="Persona B's comment about topic Y",
            interaction_type="comment",
            metadata={"reddit_id": "t1_b_456"}
        )

        # Query interactions via database
        from sqlalchemy import select
        stmt = select(Interaction).where(
            Interaction.persona_id == "persona_a"
        )
        result = await async_session.execute(stmt)
        interactions_a = result.scalars().all()

        stmt = select(Interaction).where(
            Interaction.persona_id == "persona_b"
        )
        result = await async_session.execute(stmt)
        interactions_b = result.scalars().all()

        # Verify isolation
        assert len(interactions_a) == 1
        assert len(interactions_b) == 1
        assert interactions_a[0].content == "Persona A's comment about topic X"
        assert interactions_b[0].content == "Persona B's comment about topic Y"
        assert interactions_a[0].reddit_id != interactions_b[0].reddit_id

    @pytest.mark.anyio
    async def test_moderation_queue_isolation(self, async_session):
        """Verify persona A cannot see persona B's pending posts."""
        # Create two personas
        persona_a = Persona(id="persona_a", reddit_username="user_a")
        persona_b = Persona(id="persona_b", reddit_username="user_b")
        async_session.add_all([persona_a, persona_b])
        await async_session.commit()

        # Create moderation service
        mod_service = ModerationService(async_session)

        # Enqueue posts for each persona
        item_a = await mod_service.enqueue_for_review(
            persona_id="persona_a",
            content="Post from persona A",
            metadata={"post_type": "comment", "target_subreddit": "test"}
        )

        item_b = await mod_service.enqueue_for_review(
            persona_id="persona_b",
            content="Post from persona B",
            metadata={"post_type": "comment", "target_subreddit": "test"}
        )

        # Query pending posts for each persona
        from sqlalchemy import select
        stmt = select(PendingPost).where(
            PendingPost.persona_id == "persona_a",
            PendingPost.status == "pending"
        )
        result = await async_session.execute(stmt)
        pending_a = result.scalars().all()

        stmt = select(PendingPost).where(
            PendingPost.persona_id == "persona_b",
            PendingPost.status == "pending"
        )
        result = await async_session.execute(stmt)
        pending_b = result.scalars().all()

        # Verify isolation
        assert len(pending_a) == 1
        assert len(pending_b) == 1
        assert pending_a[0].content == "Post from persona A"
        assert pending_b[0].content == "Post from persona B"
        assert pending_a[0].id != pending_b[0].id

    @pytest.mark.anyio
    async def test_agent_config_isolation(self, async_session):
        """Verify persona A cannot access persona B's config."""
        # Create two personas
        persona_a = Persona(id="persona_a", reddit_username="user_a")
        persona_b = Persona(id="persona_b", reddit_username="user_b")
        async_session.add_all([persona_a, persona_b])
        await async_session.commit()

        # Set different configs for each persona
        config_a = AgentConfig(
            persona_id="persona_a",
            config_key="auto_posting_enabled"
        )
        config_a.set_value(True)

        config_b = AgentConfig(
            persona_id="persona_b",
            config_key="auto_posting_enabled"
        )
        config_b.set_value(False)

        async_session.add_all([config_a, config_b])
        await async_session.commit()

        # Create moderation service and check configs
        mod_service = ModerationService(async_session)

        is_enabled_a = await mod_service.is_auto_posting_enabled("persona_a")
        is_enabled_b = await mod_service.is_auto_posting_enabled("persona_b")

        # Verify different configs
        assert is_enabled_a is True
        assert is_enabled_b is False

    @pytest.mark.anyio
    async def test_stance_version_isolation(self, async_session):
        """Verify persona A cannot update persona B's stances."""
        # Create two personas
        persona_a = Persona(id="persona_a", reddit_username="user_a")
        persona_b = Persona(id="persona_b", reddit_username="user_b")
        async_session.add_all([persona_a, persona_b])
        await async_session.commit()

        # Create beliefs for each
        belief_a = BeliefNode(
            persona_id="persona_a",
            title="Belief A",
            summary="Persona A's belief",
            current_confidence=0.7
        )
        belief_b = BeliefNode(
            persona_id="persona_b",
            title="Belief B",
            summary="Persona B's belief",
            current_confidence=0.6
        )
        async_session.add_all([belief_a, belief_b])
        await async_session.commit()

        # Create memory store
        memory_store = SQLiteMemoryStore(async_session)

        # Update stance for persona A
        await memory_store.update_stance_version(
            persona_id="persona_a",
            belief_id=belief_a.id,
            text="Updated stance for A",
            confidence=0.85,
            rationale="New evidence"
        )

        # Verify only persona A's belief was updated
        from sqlalchemy import select
        stmt = select(StanceVersion).where(
            StanceVersion.persona_id == "persona_a"
        )
        result = await async_session.execute(stmt)
        stances_a = result.scalars().all()

        stmt = select(StanceVersion).where(
            StanceVersion.persona_id == "persona_b"
        )
        result = await async_session.execute(stmt)
        stances_b = result.scalars().all()

        # Persona A should have stance versions, persona B should not
        assert len(stances_a) >= 1
        assert len(stances_b) == 0

    @pytest.mark.anyio
    async def test_cross_persona_operations_fail(self, async_session):
        """Verify operations with wrong persona_id fail or return empty."""
        # Create two personas
        persona_a = Persona(id="persona_a", reddit_username="user_a")
        persona_b = Persona(id="persona_b", reddit_username="user_b")
        async_session.add_all([persona_a, persona_b])
        await async_session.commit()

        # Create belief for persona B
        belief_b = BeliefNode(
            persona_id="persona_b",
            title="Belief B",
            summary="Belongs to B",
            current_confidence=0.8
        )
        async_session.add(belief_b)
        await async_session.commit()

        # Create memory store
        memory_store = SQLiteMemoryStore(async_session)

        # Try to query persona A (should get empty result)
        graph_a = await memory_store.query_belief_graph("persona_a")
        assert len(graph_a["nodes"]) == 0  # No beliefs for persona A

        # Query persona B (should get belief)
        graph_b = await memory_store.query_belief_graph("persona_b")
        assert len(graph_b["nodes"]) == 1

    @pytest.mark.anyio
    async def test_full_workflow_isolation(self, async_session):
        """
        Test complete workflow for two personas in parallel.

        Ensures all operations maintain isolation throughout:
        - Belief creation
        - Interaction logging
        - Content moderation
        - Config management
        """
        # Setup two personas
        persona_a = Persona(id="persona_a", reddit_username="user_a")
        persona_b = Persona(id="persona_b", reddit_username="user_b")
        async_session.add_all([persona_a, persona_b])
        await async_session.commit()

        # Create services
        memory_store = SQLiteMemoryStore(async_session)
        mod_service = ModerationService(async_session)

        # Persona A workflow
        # 1. Create belief
        belief_a = BeliefNode(
            persona_id="persona_a",
            title="AI is beneficial",
            summary="Persona A believes AI is beneficial",
            current_confidence=0.9
        )
        async_session.add(belief_a)
        await async_session.commit()

        # 2. Log interaction
        interaction_a_id = await memory_store.log_interaction(
            persona_id="persona_a",
            content="Persona A's comment on AI",
            interaction_type="comment",
            metadata={"reddit_id": "t1_a"}
        )

        # 3. Evaluate and enqueue content
        eval_a = await mod_service.evaluate_content(
            persona_id="persona_a",
            content="Persona A posting about AI benefits",
            context={}
        )
        item_a_id = await mod_service.enqueue_for_review(
            persona_id="persona_a",
            content="Persona A posting about AI benefits",
            metadata={"evaluation": eval_a}
        )

        # Persona B workflow (same operations)
        belief_b = BeliefNode(
            persona_id="persona_b",
            title="AI is risky",
            summary="Persona B is cautious about AI",
            current_confidence=0.8
        )
        async_session.add(belief_b)
        await async_session.commit()

        interaction_b_id = await memory_store.log_interaction(
            persona_id="persona_b",
            content="Persona B's comment on AI risks",
            interaction_type="comment",
            metadata={"reddit_id": "t1_b"}
        )

        eval_b = await mod_service.evaluate_content(
            persona_id="persona_b",
            content="Persona B posting about AI risks",
            context={}
        )
        item_b_id = await mod_service.enqueue_for_review(
            persona_id="persona_b",
            content="Persona B posting about AI risks",
            metadata={"evaluation": eval_b}
        )

        # Verify complete isolation
        # 1. Beliefs
        graph_a = await memory_store.query_belief_graph("persona_a")
        graph_b = await memory_store.query_belief_graph("persona_b")
        assert len(graph_a["nodes"]) == 1
        assert len(graph_b["nodes"]) == 1
        assert graph_a["nodes"][0]["title"] == "AI is beneficial"
        assert graph_b["nodes"][0]["title"] == "AI is risky"

        # 2. Interactions
        from sqlalchemy import select
        stmt = select(Interaction).where(
            Interaction.persona_id == "persona_a"
        )
        result = await async_session.execute(stmt)
        assert len(result.scalars().all()) == 1

        stmt = select(Interaction).where(
            Interaction.persona_id == "persona_b"
        )
        result = await async_session.execute(stmt)
        assert len(result.scalars().all()) == 1

        # 3. Pending posts
        stmt = select(PendingPost).where(
            PendingPost.persona_id == "persona_a"
        )
        result = await async_session.execute(stmt)
        assert len(result.scalars().all()) == 1

        stmt = select(PendingPost).where(
            PendingPost.persona_id == "persona_b"
        )
        result = await async_session.execute(stmt)
        assert len(result.scalars().all()) == 1

        # Ensure IDs are all different
        assert interaction_a_id != interaction_b_id
        assert item_a_id != item_b_id
