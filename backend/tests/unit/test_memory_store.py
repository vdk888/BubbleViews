"""
Unit tests for Memory Store implementation.

Tests all memory store operations including belief graph queries,
stance updates, evidence linking, interaction logging, and semantic search.
"""

import pytest
from datetime import datetime
from sqlalchemy import select
from app.services.memory_store import SQLiteMemoryStore
from app.models.persona import Persona
from app.models.belief import BeliefNode, BeliefEdge, StanceVersion, EvidenceLink
from app.models.interaction import Interaction


@pytest.fixture
async def memory_store():
    """Create memory store instance."""
    return SQLiteMemoryStore()


@pytest.fixture
async def test_persona(async_session):
    """Create a test persona."""
    persona = Persona(
        reddit_username="test_agent",
        display_name="Test Agent",
    )
    persona.set_config({
        "auto_posting_enabled": False,
        "target_subreddits": ["test"]
    })
    async_session.add(persona)
    await async_session.commit()
    await async_session.refresh(persona)
    return persona


@pytest.fixture
async def test_persona_2(async_session):
    """Create a second test persona for isolation tests."""
    persona = Persona(
        reddit_username="test_agent_2",
        display_name="Test Agent 2",
    )
    persona.set_config({
        "auto_posting_enabled": False,
        "target_subreddits": ["test2"]
    })
    async_session.add(persona)
    await async_session.commit()
    await async_session.refresh(persona)
    return persona


@pytest.fixture
async def test_belief(async_session, test_persona):
    """Create a test belief node."""
    belief = BeliefNode(
        persona_id=test_persona.id,
        title="Test Belief",
        summary="This is a test belief for unit testing",
        current_confidence=0.8,
    )
    belief.set_tags(["test", "unit"])
    async_session.add(belief)
    await async_session.commit()
    await async_session.refresh(belief)
    return belief


class TestQueryBeliefGraph:
    """Test belief graph query operations."""

    async def test_query_empty_graph(self, memory_store, test_persona):
        """Test querying belief graph with no beliefs."""
        # Arrange & Act
        graph = await memory_store.query_belief_graph(test_persona.id)

        # Assert
        assert graph["nodes"] == []
        assert graph["edges"] == []

    async def test_query_basic_graph(self, memory_store, test_persona, test_belief):
        """Test querying belief graph with one belief."""
        # Arrange & Act
        graph = await memory_store.query_belief_graph(test_persona.id)

        # Assert
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["id"] == test_belief.id
        assert graph["nodes"][0]["title"] == "Test Belief"
        assert graph["nodes"][0]["confidence"] == 0.8
        assert "test" in graph["nodes"][0]["tags"]

    async def test_query_with_tag_filter(
        self, memory_store, async_session, test_persona
    ):
        """Test querying beliefs filtered by tags."""
        # Arrange
        belief1 = BeliefNode(
            persona_id=test_persona.id,
            title="Belief 1",
            summary="Tagged with science",
            current_confidence=0.7,
        )
        belief1.set_tags(["science", "climate"])

        belief2 = BeliefNode(
            persona_id=test_persona.id,
            title="Belief 2",
            summary="Tagged with politics",
            current_confidence=0.6,
        )
        belief2.set_tags(["politics", "economy"])

        async_session.add_all([belief1, belief2])
        await async_session.commit()

        # Act
        graph = await memory_store.query_belief_graph(
            test_persona.id,
            tags=["science"]
        )

        # Assert
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["title"] == "Belief 1"

    async def test_query_with_confidence_filter(
        self, memory_store, async_session, test_persona
    ):
        """Test querying beliefs filtered by minimum confidence."""
        # Arrange
        belief1 = BeliefNode(
            persona_id=test_persona.id,
            title="High Confidence",
            summary="High confidence belief",
            current_confidence=0.9,
        )

        belief2 = BeliefNode(
            persona_id=test_persona.id,
            title="Low Confidence",
            summary="Low confidence belief",
            current_confidence=0.3,
        )

        async_session.add_all([belief1, belief2])
        await async_session.commit()

        # Act
        graph = await memory_store.query_belief_graph(
            test_persona.id,
            min_confidence=0.7
        )

        # Assert
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["title"] == "High Confidence"

    async def test_query_invalid_confidence(self, memory_store, test_persona):
        """Test querying with invalid confidence raises error."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            await memory_store.query_belief_graph(
                test_persona.id,
                min_confidence=1.5
            )


class TestUpdateStanceVersion:
    """Test stance version update operations."""

    async def test_update_stance_first_version(
        self, memory_store, test_persona, test_belief
    ):
        """Test creating first stance version for a belief."""
        # Arrange & Act
        stance_id = await memory_store.update_stance_version(
            persona_id=test_persona.id,
            belief_id=test_belief.id,
            text="Initial stance on this belief",
            confidence=0.85,
            rationale="Based on initial research",
            updated_by="test"
        )

        # Assert
        assert stance_id is not None

        # Verify stance was created
        result = await memory_store.get_belief_with_stances(
            test_persona.id,
            test_belief.id
        )
        assert len(result["stances"]) == 1
        assert result["stances"][0]["status"] == "current"
        assert result["stances"][0]["confidence"] == 0.85

    async def test_update_stance_second_version(
        self, memory_store, async_session, test_persona, test_belief
    ):
        """Test updating stance marks previous as deprecated."""
        # Arrange - Create first stance
        first_stance = StanceVersion(
            persona_id=test_persona.id,
            belief_id=test_belief.id,
            text="First stance",
            confidence=0.7,
            status="current",
            rationale="Initial"
        )
        async_session.add(first_stance)
        await async_session.commit()

        # Act - Update stance
        await memory_store.update_stance_version(
            persona_id=test_persona.id,
            belief_id=test_belief.id,
            text="Updated stance",
            confidence=0.9,
            rationale="New evidence",
            updated_by="test"
        )

        # Assert
        result = await memory_store.get_belief_with_stances(
            test_persona.id,
            test_belief.id
        )
        assert len(result["stances"]) == 2

        # Current stance is the new one
        assert result["stances"][0]["text"] == "Updated stance"
        assert result["stances"][0]["status"] == "current"

        # Old stance is deprecated
        assert result["stances"][1]["text"] == "First stance"
        assert result["stances"][1]["status"] == "deprecated"

    async def test_update_locked_stance_raises_error(
        self, memory_store, async_session, test_persona, test_belief
    ):
        """Test updating locked stance raises PermissionError."""
        # Arrange - Create locked stance
        locked_stance = StanceVersion(
            persona_id=test_persona.id,
            belief_id=test_belief.id,
            text="Locked stance",
            confidence=0.8,
            status="locked",
            rationale="Manually locked"
        )
        async_session.add(locked_stance)
        await async_session.commit()

        # Act & Assert
        with pytest.raises(PermissionError, match="locked"):
            await memory_store.update_stance_version(
                persona_id=test_persona.id,
                belief_id=test_belief.id,
                text="Try to update",
                confidence=0.9,
                rationale="Should fail"
            )

    async def test_update_invalid_confidence_raises_error(
        self, memory_store, test_persona, test_belief
    ):
        """Test updating with invalid confidence raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            await memory_store.update_stance_version(
                persona_id=test_persona.id,
                belief_id=test_belief.id,
                text="Test",
                confidence=2.0,
                rationale="Invalid"
            )

    async def test_update_nonexistent_belief_raises_error(
        self, memory_store, test_persona
    ):
        """Test updating nonexistent belief raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await memory_store.update_stance_version(
                persona_id=test_persona.id,
                belief_id="nonexistent-id",
                text="Test",
                confidence=0.5,
                rationale="Should fail"
            )


class TestAppendEvidence:
    """Test evidence linking operations."""

    async def test_append_reddit_comment_evidence(
        self, memory_store, test_persona, test_belief
    ):
        """Test appending Reddit comment as evidence."""
        # Arrange & Act
        evidence_id = await memory_store.append_evidence(
            persona_id=test_persona.id,
            belief_id=test_belief.id,
            source_type="reddit_comment",
            source_ref="t1_abc123",
            strength="strong"
        )

        # Assert
        assert evidence_id is not None

        result = await memory_store.get_belief_with_stances(
            test_persona.id,
            test_belief.id
        )
        assert len(result["evidence"]) == 1
        assert result["evidence"][0]["source_type"] == "reddit_comment"
        assert result["evidence"][0]["source_ref"] == "t1_abc123"
        assert result["evidence"][0]["strength"] == "strong"

    async def test_append_external_link_evidence(
        self, memory_store, test_persona, test_belief
    ):
        """Test appending external link as evidence."""
        # Arrange & Act
        evidence_id = await memory_store.append_evidence(
            persona_id=test_persona.id,
            belief_id=test_belief.id,
            source_type="external_link",
            source_ref="https://example.com/article",
            strength="moderate"
        )

        # Assert
        assert evidence_id is not None

    async def test_append_invalid_source_type_raises_error(
        self, memory_store, test_persona, test_belief
    ):
        """Test appending evidence with invalid source type raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Invalid source_type"):
            await memory_store.append_evidence(
                persona_id=test_persona.id,
                belief_id=test_belief.id,
                source_type="invalid_type",
                source_ref="test",
                strength="weak"
            )

    async def test_append_invalid_strength_raises_error(
        self, memory_store, test_persona, test_belief
    ):
        """Test appending evidence with invalid strength raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Invalid strength"):
            await memory_store.append_evidence(
                persona_id=test_persona.id,
                belief_id=test_belief.id,
                source_type="note",
                source_ref="test note",
                strength="invalid_strength"
            )


class TestLogInteraction:
    """Test interaction logging operations."""

    async def test_log_comment_interaction(self, memory_store, test_persona):
        """Test logging a Reddit comment."""
        # Arrange
        metadata = {
            "reddit_id": "t1_test123",
            "subreddit": "AskReddit",
            "parent_id": "t3_post456",
            "score": 42,
            "author": "test_user"
        }

        # Act
        interaction_id = await memory_store.log_interaction(
            persona_id=test_persona.id,
            content="This is a test comment",
            interaction_type="comment",
            metadata=metadata
        )

        # Assert
        assert interaction_id is not None

    async def test_log_post_interaction(self, memory_store, test_persona):
        """Test logging a Reddit post."""
        # Arrange
        metadata = {
            "reddit_id": "t3_post789",
            "subreddit": "test",
            "score": 100
        }

        # Act
        interaction_id = await memory_store.log_interaction(
            persona_id=test_persona.id,
            content="This is a test post",
            interaction_type="post",
            metadata=metadata
        )

        # Assert
        assert interaction_id is not None

    async def test_log_missing_reddit_id_raises_error(
        self, memory_store, test_persona
    ):
        """Test logging without reddit_id raises ValueError."""
        # Arrange
        metadata = {"subreddit": "test"}  # Missing reddit_id

        # Act & Assert
        with pytest.raises(ValueError, match="reddit_id"):
            await memory_store.log_interaction(
                persona_id=test_persona.id,
                content="Test",
                interaction_type="comment",
                metadata=metadata
            )

    async def test_log_invalid_type_raises_error(self, memory_store, test_persona):
        """Test logging with invalid interaction type raises ValueError."""
        # Arrange
        metadata = {
            "reddit_id": "t1_test",
            "subreddit": "test"
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid interaction_type"):
            await memory_store.log_interaction(
                persona_id=test_persona.id,
                content="Test",
                interaction_type="invalid_type",
                metadata=metadata
            )


class TestSearchHistory:
    """Test semantic history search operations."""

    async def test_search_empty_history(self, memory_store, test_persona):
        """Test searching with no interactions returns empty list."""
        # Arrange & Act
        results = await memory_store.search_history(
            persona_id=test_persona.id,
            query="test query"
        )

        # Assert
        assert results == []

    async def test_search_with_interactions(
        self, memory_store, async_session, test_persona
    ):
        """Test searching interactions with semantic similarity."""
        # Arrange - Create interactions
        interaction1 = Interaction(
            persona_id=test_persona.id,
            content="I love Python programming and machine learning",
            interaction_type="comment",
            reddit_id="t1_prog1",
            subreddit="programming"
        )
        interaction1.set_metadata({
            "reddit_id": "t1_prog1",
            "subreddit": "programming"
        })

        interaction2 = Interaction(
            persona_id=test_persona.id,
            content="Pizza is the best food ever",
            interaction_type="comment",
            reddit_id="t1_food1",
            subreddit="food"
        )
        interaction2.set_metadata({
            "reddit_id": "t1_food1",
            "subreddit": "food"
        })

        async_session.add_all([interaction1, interaction2])
        await async_session.commit()
        await async_session.refresh(interaction1)
        await async_session.refresh(interaction2)

        # Add embeddings
        await memory_store.add_interaction_embedding(interaction1.id, test_persona.id)
        await memory_store.add_interaction_embedding(interaction2.id, test_persona.id)

        # Act - Search for programming-related content
        results = await memory_store.search_history(
            persona_id=test_persona.id,
            query="What are your thoughts on coding?",
            limit=2
        )

        # Assert
        assert len(results) >= 1
        # First result should be about programming (higher similarity)
        assert "Python" in results[0]["content"] or "programming" in results[0]["content"]
        assert results[0]["similarity_score"] > 0.0

    async def test_search_with_subreddit_filter(
        self, memory_store, async_session, test_persona
    ):
        """Test searching interactions filtered by subreddit."""
        # Arrange - Create interactions in different subreddits
        interaction1 = Interaction(
            persona_id=test_persona.id,
            content="Science is awesome",
            interaction_type="comment",
            reddit_id="t1_sci1",
            subreddit="science"
        )
        interaction1.set_metadata({"reddit_id": "t1_sci1", "subreddit": "science"})

        interaction2 = Interaction(
            persona_id=test_persona.id,
            content="Technology is great",
            interaction_type="comment",
            reddit_id="t1_tech1",
            subreddit="technology"
        )
        interaction2.set_metadata({"reddit_id": "t1_tech1", "subreddit": "technology"})

        async_session.add_all([interaction1, interaction2])
        await async_session.commit()
        await async_session.refresh(interaction1)
        await async_session.refresh(interaction2)

        # Add embeddings
        await memory_store.add_interaction_embedding(interaction1.id, test_persona.id)
        await memory_store.add_interaction_embedding(interaction2.id, test_persona.id)

        # Act
        results = await memory_store.search_history(
            persona_id=test_persona.id,
            query="What do you think?",
            limit=5,
            subreddit="science"
        )

        # Assert
        assert len(results) >= 1
        assert all(r["subreddit"].lower() == "science" for r in results)

    async def test_search_invalid_limit_raises_error(
        self, memory_store, test_persona
    ):
        """Test searching with invalid limit raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="limit must be >= 1"):
            await memory_store.search_history(
                persona_id=test_persona.id,
                query="test",
                limit=0
            )


class TestPersonaIsolation:
    """Test persona isolation across all operations."""

    async def test_belief_graph_isolation(
        self, memory_store, async_session, test_persona, test_persona_2
    ):
        """Test belief graphs are isolated per persona."""
        # Arrange - Create beliefs for both personas
        belief1 = BeliefNode(
            persona_id=test_persona.id,
            title="Persona 1 Belief",
            summary="Only for persona 1",
            current_confidence=0.8
        )

        belief2 = BeliefNode(
            persona_id=test_persona_2.id,
            title="Persona 2 Belief",
            summary="Only for persona 2",
            current_confidence=0.9
        )

        async_session.add_all([belief1, belief2])
        await async_session.commit()

        # Act - Query each persona's graph
        graph1 = await memory_store.query_belief_graph(test_persona.id)
        graph2 = await memory_store.query_belief_graph(test_persona_2.id)

        # Assert - Each persona only sees their own beliefs
        assert len(graph1["nodes"]) == 1
        assert graph1["nodes"][0]["title"] == "Persona 1 Belief"

        assert len(graph2["nodes"]) == 1
        assert graph2["nodes"][0]["title"] == "Persona 2 Belief"

    async def test_interaction_history_isolation(
        self, memory_store, async_session, test_persona, test_persona_2
    ):
        """Test interactions are isolated per persona."""
        # Arrange - Create interactions for both personas
        int1 = Interaction(
            persona_id=test_persona.id,
            content="Persona 1 comment",
            interaction_type="comment",
            reddit_id="t1_p1",
            subreddit="test"
        )
        int1.set_metadata({"reddit_id": "t1_p1", "subreddit": "test"})

        int2 = Interaction(
            persona_id=test_persona_2.id,
            content="Persona 2 comment",
            interaction_type="comment",
            reddit_id="t1_p2",
            subreddit="test"
        )
        int2.set_metadata({"reddit_id": "t1_p2", "subreddit": "test"})

        async_session.add_all([int1, int2])
        await async_session.commit()
        await async_session.refresh(int1)
        await async_session.refresh(int2)

        # Add embeddings
        await memory_store.add_interaction_embedding(int1.id, test_persona.id)
        await memory_store.add_interaction_embedding(int2.id, test_persona_2.id)

        # Act - Search each persona's history
        results1 = await memory_store.search_history(
            persona_id=test_persona.id,
            query="comment"
        )
        results2 = await memory_store.search_history(
            persona_id=test_persona_2.id,
            query="comment"
        )

        # Assert - Each persona only sees their own interactions
        assert len(results1) >= 1
        assert all("Persona 1" in r["content"] for r in results1)

        assert len(results2) >= 1
        assert all("Persona 2" in r["content"] for r in results2)

    async def test_cross_persona_stance_update_fails(
        self, memory_store, async_session, test_persona, test_persona_2
    ):
        """Test cannot update belief from different persona."""
        # Arrange - Create belief for persona 2
        belief = BeliefNode(
            persona_id=test_persona_2.id,
            title="Persona 2 Belief",
            summary="Owned by persona 2",
            current_confidence=0.7
        )
        async_session.add(belief)
        await async_session.commit()
        await async_session.refresh(belief)

        # Act & Assert - Persona 1 cannot update persona 2's belief
        with pytest.raises(ValueError, match="not found"):
            await memory_store.update_stance_version(
                persona_id=test_persona.id,  # Wrong persona
                belief_id=belief.id,
                text="Try to update",
                confidence=0.9,
                rationale="Should fail"
            )

    async def test_cross_persona_evidence_append_fails(
        self, memory_store, async_session, test_persona, test_persona_2
    ):
        """Test cannot append evidence to belief from different persona."""
        # Arrange - Create belief for persona 2
        belief = BeliefNode(
            persona_id=test_persona_2.id,
            title="Persona 2 Belief",
            summary="Owned by persona 2",
            current_confidence=0.7
        )
        async_session.add(belief)
        await async_session.commit()
        await async_session.refresh(belief)

        # Act & Assert - Persona 1 cannot append evidence to persona 2's belief
        with pytest.raises(ValueError, match="not found"):
            await memory_store.append_evidence(
                persona_id=test_persona.id,  # Wrong persona
                belief_id=belief.id,
                source_type="note",
                source_ref="test",
                strength="weak"
            )


class TestFAISSIndexOperations:
    """Test FAISS index persistence and rebuild."""

    async def test_rebuild_empty_index(self, memory_store, test_persona):
        """Test rebuilding index with no interactions."""
        # Arrange & Act
        count = await memory_store.rebuild_faiss_index(test_persona.id)

        # Assert
        assert count == 0

    async def test_rebuild_with_interactions(
        self, memory_store, async_session, test_persona
    ):
        """Test rebuilding index from existing interactions."""
        # Arrange - Create interactions
        interactions = []
        for i in range(3):
            interaction = Interaction(
                persona_id=test_persona.id,
                content=f"Test interaction {i}",
                interaction_type="comment",
                reddit_id=f"t1_test{i}",
                subreddit="test"
            )
            interaction.set_metadata({
                "reddit_id": f"t1_test{i}",
                "subreddit": "test"
            })
            interactions.append(interaction)

        async_session.add_all(interactions)
        await async_session.commit()

        # Act - Rebuild index
        count = await memory_store.rebuild_faiss_index(test_persona.id)

        # Assert
        assert count == 3

        # Verify search works after rebuild
        results = await memory_store.search_history(
            persona_id=test_persona.id,
            query="test",
            limit=5
        )
        assert len(results) == 3

    async def test_rebuild_invalid_persona_raises_error(self, memory_store):
        """Test rebuilding index for nonexistent persona raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await memory_store.rebuild_faiss_index("nonexistent-persona-id")
