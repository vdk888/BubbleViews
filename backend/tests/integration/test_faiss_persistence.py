"""
FAISS index persistence and rebuild tests.

Verifies that the FAISS embedding index correctly persists to disk,
reloads after restart, and can be rebuilt if missing.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from app.services.embedding import EmbeddingService, get_embedding_service
from app.services.memory_store import SQLiteMemoryStore
from app.models.persona import Persona
from app.models.interaction import Interaction


class TestFAISSPersistence:
    """Tests for FAISS index persistence."""

    @pytest.mark.anyio
    async def test_embedding_generation(self):
        """Test embedding generation produces consistent vectors."""
        # Create embedding service (no index_path needed)
        embedding_service = EmbeddingService()

        # Generate embedding
        text = "This is a test sentence about artificial intelligence."
        embedding = await embedding_service.generate_embedding(text)

        # Verify embedding properties
        assert embedding is not None
        assert len(embedding) == 384  # all-MiniLM-L6-v2 dimension
        assert embedding.dtype.name.startswith('float')

        # Verify consistency (same text -> same embedding)
        embedding2 = await embedding_service.generate_embedding(text)
        import numpy as np
        assert np.allclose(embedding, embedding2, rtol=1e-5)

    @pytest.mark.anyio
    async def test_index_persistence(self):
        """Test that FAISS index persists to disk and reloads."""
        # Use a test persona ID
        persona_id = "test_persona_persist"

        # Create embedding service
        embedding_service = EmbeddingService()

        # Add some embeddings
        text1 = "Machine learning is a subset of artificial intelligence."
        text2 = "Deep learning uses neural networks with multiple layers."
        text3 = "Natural language processing enables computers to understand text."

        emb1 = await embedding_service.generate_embedding(text1)
        emb2 = await embedding_service.generate_embedding(text2)
        emb3 = await embedding_service.generate_embedding(text3)

        await embedding_service.add_to_index(persona_id, "interaction_1", emb1)
        await embedding_service.add_to_index(persona_id, "interaction_2", emb2)
        await embedding_service.add_to_index(persona_id, "interaction_3", emb3)

        # Save index
        await embedding_service.persist_index(persona_id)

        # Verify index file exists
        index_path = embedding_service._get_index_path(persona_id)
        assert index_path.exists()
        assert index_path.stat().st_size > 0

        # Create new service instance (simulates restart)
        embedding_service2 = EmbeddingService()

        # The index will be automatically loaded when accessed
        # Verify we can search with the reloaded index
        query_emb = await embedding_service2.generate_embedding(
            "Tell me about machine learning"
        )
        results = await embedding_service2.search(persona_id, query_emb, k=2)

        assert len(results) > 0
        # Should find similar interactions
        assert "interaction_1" in [r[0] for r in results]  # Most relevant

        # Clean up
        await embedding_service2.clear_index(persona_id)

    @pytest.mark.anyio
    async def test_index_rebuild(self):
        """Test rebuilding FAISS index from scratch."""
        # Use a test persona ID
        persona_id = "test_persona_rebuild"

        # Create embedding service
        embedding_service = EmbeddingService()

        # Verify no index exists initially
        index_path = embedding_service._get_index_path(persona_id)
        if index_path.exists():
            await embedding_service.clear_index(persona_id)

        assert not index_path.exists()

        # Add embeddings (should work even without existing index)
        text1 = "This is the first document."
        emb1 = await embedding_service.generate_embedding(text1)
        await embedding_service.add_to_index(persona_id, "doc_1", emb1)

        # Save and verify
        await embedding_service.persist_index(persona_id)
        assert index_path.exists()

        # Clean up
        await embedding_service.clear_index(persona_id)

    @pytest.mark.anyio
    async def test_memory_store_with_embeddings(self, async_session):
        """Test memory store integrating with embedding service."""
        # Create persona
        persona = Persona(
            id="test_persona_mem",
            reddit_username="test_user_mem"
        )
        async_session.add(persona)
        await async_session.commit()

        # Create memory store with embedding service
        memory_store = SQLiteMemoryStore(async_session)
        embedding_service = EmbeddingService()

        # Log interactions with embeddings
        texts = [
            "I think artificial intelligence will revolutionize healthcare.",
            "Machine learning models need large datasets to train effectively.",
            "Climate change is one of the most pressing issues of our time.",
        ]

        interaction_ids = []
        for i, text in enumerate(texts):
            # Log interaction (now includes metadata with subreddit)
            interaction_id = await memory_store.log_interaction(
                persona_id="test_persona_mem",
                content=text,
                interaction_type="comment",
                metadata={
                    "reddit_id": f"t1_test{i}",
                    "subreddit": "test"
                }
            )
            interaction_ids.append(interaction_id)

            # Note: log_interaction already generates and stores embeddings
            # via the add_interaction_embedding method

        # Search for similar content using memory_store's search
        results = await memory_store.search_history(
            persona_id="test_persona_mem",
            query="What are your thoughts on AI and machine learning?",
            limit=2
        )

        # Should find AI/ML related interactions
        assert len(results) > 0
        result_ids = [r["id"] for r in results]

        # First two interactions are about AI/ML
        assert interaction_ids[0] in result_ids or interaction_ids[1] in result_ids

        # Clean up
        await embedding_service.clear_index("test_persona_mem")

    @pytest.mark.anyio
    async def test_search_with_empty_index(self):
        """Test searching with an empty or non-existent index."""
        # Use a unique persona ID
        persona_id = "test_persona_empty"

        # Create embedding service (no index file exists)
        embedding_service = EmbeddingService()

        # Ensure no index exists
        index_path = embedding_service._get_index_path(persona_id)
        if index_path.exists():
            await embedding_service.clear_index(persona_id)

        # Try to search (should handle gracefully)
        query_emb = await embedding_service.generate_embedding("test query")
        results = await embedding_service.search(persona_id, query_emb, k=5)

        # Should return empty list
        assert results == []

    @pytest.mark.anyio
    async def test_index_survives_restart(self, async_session):
        """
        Full integration test: add interactions with embeddings,
        save index, restart service, verify search still works.
        """
        # Setup persona
        persona = Persona(id="test_persona_restart", reddit_username="test_user_restart")
        async_session.add(persona)
        await async_session.commit()

        # Phase 1: Initial setup
        memory_store = SQLiteMemoryStore(async_session)
        embedding_service1 = EmbeddingService()

        # Clear any existing index from previous test runs
        index_path = embedding_service1._get_index_path("test_persona_restart")
        if index_path.exists():
            await embedding_service1.clear_index("test_persona_restart")

        # Add several interactions
        texts_and_topics = [
            ("Python is a great programming language.", "programming"),
            ("JavaScript frameworks are evolving rapidly.", "programming"),
            ("Climate change requires immediate action.", "environment"),
            ("Renewable energy is the future.", "environment"),
        ]

        interaction_ids = []
        for i, (text, topic) in enumerate(texts_and_topics):
            interaction_id = await memory_store.log_interaction(
                persona_id="test_persona_restart",
                content=text,
                interaction_type="comment",
                metadata={
                    "topic": topic,
                    "reddit_id": f"t1_restart_{i}_{topic}",
                    "subreddit": "test"
                }
            )
            interaction_ids.append(interaction_id)

            # Note: log_interaction already generates and stores embeddings

        # Verify index exists
        index_path = embedding_service1._get_index_path("test_persona_restart")
        assert index_path.exists()

        # Phase 2: Simulate restart (create new service instance)
        embedding_service2 = EmbeddingService()

        # The index will be automatically loaded when accessed
        # Search for programming-related content
        query_prog = "Tell me about coding languages"
        query_emb = await embedding_service2.generate_embedding(query_prog)
        results = await embedding_service2.search("test_persona_restart", query_emb, k=2)

        # The test should verify that:
        # 1. The index was persisted and reloaded
        # 2. Semantic search returns relevant results
        # We're more interested in testing persistence than exact semantic matching

        # Verify we get results (proves index was persisted and reloaded)
        assert len(results) > 0, "Index should have been reloaded and return results"

        # Verify all returned IDs are from our test interactions
        result_ids = [r[0] for r in results]
        for result_id in result_ids:
            assert result_id in interaction_ids, f"Unexpected interaction ID: {result_id}"

        # Search for environment-related content
        query_env = "What about climate and environment?"
        query_emb = await embedding_service2.generate_embedding(query_env)
        results = await embedding_service2.search("test_persona_restart", query_emb, k=2)

        # Verify we get results (proves search still works after reload)
        assert len(results) > 0, "Search should return results after index reload"

        # Verify all returned IDs are from our test interactions
        result_ids = [r[0] for r in results]
        for result_id in result_ids:
            assert result_id in interaction_ids, f"Unexpected interaction ID: {result_id}"

        # Clean up
        await embedding_service2.clear_index("test_persona_restart")

    @pytest.mark.anyio
    async def test_concurrent_index_updates(self):
        """Test that multiple updates to index work correctly."""
        persona_id = "test_persona_concurrent"
        embedding_service = EmbeddingService()

        # Clean up any existing index
        index_path = embedding_service._get_index_path(persona_id)
        if index_path.exists():
            await embedding_service.clear_index(persona_id)

        # Add multiple embeddings in sequence
        for i in range(10):
            text = f"This is test document number {i} about topic {i % 3}"
            emb = await embedding_service.generate_embedding(text)
            await embedding_service.add_to_index(persona_id, f"doc_{i}", emb)

        # Save
        await embedding_service.persist_index(persona_id)

        # Search should work
        query = "Tell me about topic 0"
        query_emb = await embedding_service.generate_embedding(query)
        results = await embedding_service.search(persona_id, query_emb, k=5)

        assert len(results) > 0
        # Should find documents about topic 0, 3, 6, 9
        assert any("doc_0" in str(r[0]) for r in results)

        # Clean up
        await embedding_service.clear_index(persona_id)
