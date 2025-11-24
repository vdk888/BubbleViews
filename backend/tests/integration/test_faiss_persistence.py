"""
FAISS index persistence and rebuild tests.

Verifies that the FAISS embedding index correctly persists to disk,
reloads after restart, and can be rebuilt if missing.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from app.services.embedding import EmbeddingService
from app.services.memory_store import SQLiteMemoryStore
from app.models.persona import Persona
from app.models.interaction import Interaction


class TestFAISSPersistence:
    """Tests for FAISS index persistence."""

    @pytest.mark.anyio
    async def test_embedding_generation(self):
        """Test embedding generation produces consistent vectors."""
        # Create temporary directory for index
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "test_faiss.index"

            # Create embedding service
            embedding_service = EmbeddingService(index_path=str(index_path))

            # Generate embedding
            text = "This is a test sentence about artificial intelligence."
            embedding = embedding_service.generate_embedding(text)

            # Verify embedding properties
            assert embedding is not None
            assert len(embedding) == 384  # all-MiniLM-L6-v2 dimension
            assert embedding.dtype.name.startswith('float')

            # Verify consistency (same text -> same embedding)
            embedding2 = embedding_service.generate_embedding(text)
            import numpy as np
            assert np.allclose(embedding, embedding2, rtol=1e-5)

    @pytest.mark.anyio
    async def test_index_persistence(self):
        """Test that FAISS index persists to disk and reloads."""
        # Create temporary directory for index
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "test_faiss.index"

            # Create embedding service and add embeddings
            embedding_service = EmbeddingService(index_path=str(index_path))

            # Add some embeddings
            text1 = "Machine learning is a subset of artificial intelligence."
            text2 = "Deep learning uses neural networks with multiple layers."
            text3 = "Natural language processing enables computers to understand text."

            emb1 = embedding_service.generate_embedding(text1)
            emb2 = embedding_service.generate_embedding(text2)
            emb3 = embedding_service.generate_embedding(text3)

            embedding_service.add_to_index(emb1, "interaction_1")
            embedding_service.add_to_index(emb2, "interaction_2")
            embedding_service.add_to_index(emb3, "interaction_3")

            # Save index
            embedding_service.save_index()

            # Verify index file exists
            assert index_path.exists()
            assert index_path.stat().st_size > 0

            # Create new service instance (simulates restart)
            embedding_service2 = EmbeddingService(index_path=str(index_path))

            # Load the index
            embedding_service2.load_index()

            # Verify we can search with the reloaded index
            query_emb = embedding_service2.generate_embedding(
                "Tell me about machine learning"
            )
            results = embedding_service2.search(query_emb, k=2)

            assert len(results) > 0
            # Should find similar interactions
            assert "interaction_1" in [r[0] for r in results]  # Most relevant

    @pytest.mark.anyio
    async def test_index_rebuild(self):
        """Test rebuilding FAISS index from scratch."""
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "test_faiss.index"

            # Create embedding service
            embedding_service = EmbeddingService(index_path=str(index_path))

            # Simulate missing index (don't create one)
            # Verify graceful handling
            assert not index_path.exists()

            # Add embeddings (should work even without existing index)
            text1 = "This is the first document."
            emb1 = embedding_service.generate_embedding(text1)
            embedding_service.add_to_index(emb1, "doc_1")

            # Save and verify
            embedding_service.save_index()
            assert index_path.exists()

    @pytest.mark.anyio
    async def test_memory_store_with_embeddings(self, async_session):
        """Test memory store integrating with embedding service."""
        # Create temporary directory for index
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "test_faiss.index"

            # Create persona
            persona = Persona(
                id="test_persona",
                reddit_username="test_user"
            )
            async_session.add(persona)
            await async_session.commit()

            # Create memory store with embedding service
            memory_store = SQLiteMemoryStore(async_session)
            embedding_service = EmbeddingService(index_path=str(index_path))

            # Log interactions with embeddings
            texts = [
                "I think artificial intelligence will revolutionize healthcare.",
                "Machine learning models need large datasets to train effectively.",
                "Climate change is one of the most pressing issues of our time.",
            ]

            interaction_ids = []
            for i, text in enumerate(texts):
                # Log interaction
                interaction_id = await memory_store.log_interaction(
                    persona_id="test_persona",
                    content=text,
                    interaction_type="comment",
                    metadata={"reddit_id": f"t1_test{i}"}
                )
                interaction_ids.append(interaction_id)

                # Generate and store embedding
                embedding = embedding_service.generate_embedding(text)
                embedding_service.add_to_index(embedding, interaction_id)

            # Save index
            embedding_service.save_index()

            # Search for similar content
            query = "What are your thoughts on AI and machine learning?"
            query_emb = embedding_service.generate_embedding(query)
            results = embedding_service.search(query_emb, k=2)

            # Should find AI/ML related interactions
            assert len(results) > 0
            result_ids = [r[0] for r in results]

            # First two interactions are about AI/ML
            assert interaction_ids[0] in result_ids or interaction_ids[1] in result_ids

    @pytest.mark.anyio
    async def test_search_with_empty_index(self):
        """Test searching with an empty or non-existent index."""
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "test_faiss.index"

            # Create embedding service (no index file exists)
            embedding_service = EmbeddingService(index_path=str(index_path))

            # Try to search (should handle gracefully)
            query_emb = embedding_service.generate_embedding("test query")
            results = embedding_service.search(query_emb, k=5)

            # Should return empty list
            assert results == []

    @pytest.mark.anyio
    async def test_index_survives_restart(self, async_session):
        """
        Full integration test: add interactions with embeddings,
        save index, restart service, verify search still works.
        """
        # Create temporary directory that persists across service restarts
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "test_faiss.index"

            # Setup persona
            persona = Persona(id="test_persona", reddit_username="test_user")
            async_session.add(persona)
            await async_session.commit()

            # Phase 1: Initial setup
            memory_store = SQLiteMemoryStore(async_session)
            embedding_service1 = EmbeddingService(index_path=str(index_path))

            # Add several interactions
            texts_and_topics = [
                ("Python is a great programming language.", "programming"),
                ("JavaScript frameworks are evolving rapidly.", "programming"),
                ("Climate change requires immediate action.", "environment"),
                ("Renewable energy is the future.", "environment"),
            ]

            interaction_ids = []
            for text, topic in texts_and_topics:
                interaction_id = await memory_store.log_interaction(
                    persona_id="test_persona",
                    content=text,
                    interaction_type="comment",
                    metadata={"topic": topic}
                )
                interaction_ids.append(interaction_id)

                embedding = embedding_service1.generate_embedding(text)
                embedding_service1.add_to_index(embedding, interaction_id)

            # Save index
            embedding_service1.save_index()
            assert index_path.exists()

            # Phase 2: Simulate restart (create new service instance)
            embedding_service2 = EmbeddingService(index_path=str(index_path))
            embedding_service2.load_index()

            # Search for programming-related content
            query_prog = "Tell me about coding languages"
            query_emb = embedding_service2.generate_embedding(query_prog)
            results = embedding_service2.search(query_emb, k=2)

            assert len(results) == 2
            # Should find programming-related interactions (first two)
            result_ids = [r[0] for r in results]
            assert interaction_ids[0] in result_ids
            assert interaction_ids[1] in result_ids

            # Search for environment-related content
            query_env = "What about climate and environment?"
            query_emb = embedding_service2.generate_embedding(query_env)
            results = embedding_service2.search(query_emb, k=2)

            assert len(results) == 2
            # Should find environment-related interactions (last two)
            result_ids = [r[0] for r in results]
            assert interaction_ids[2] in result_ids
            assert interaction_ids[3] in result_ids

    @pytest.mark.anyio
    async def test_concurrent_index_updates(self):
        """Test that multiple updates to index work correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "test_faiss.index"
            embedding_service = EmbeddingService(index_path=str(index_path))

            # Add multiple embeddings in sequence
            for i in range(10):
                text = f"This is test document number {i} about topic {i % 3}"
                emb = embedding_service.generate_embedding(text)
                embedding_service.add_to_index(emb, f"doc_{i}")

            # Save
            embedding_service.save_index()

            # Search should work
            query = "Tell me about topic 0"
            query_emb = embedding_service.generate_embedding(query)
            results = embedding_service.search(query_emb, k=5)

            assert len(results) > 0
            # Should find documents about topic 0, 3, 6, 9
            assert any("doc_0" in str(r[0]) for r in results)
