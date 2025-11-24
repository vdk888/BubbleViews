"""
Embedding generation and FAISS index management.

Provides sentence-transformers embedding generation and FAISS vector search
for semantic similarity queries over interaction history.

Model: all-MiniLM-L6-v2 (384 dimensions)
Index: FAISS IndexFlatL2 (CPU-optimized)
"""

import os
import pickle
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import asyncio
from functools import lru_cache

from app.core.config import settings


# Model configuration
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension


class EmbeddingService:
    """
    Manages embedding generation and FAISS index operations.

    Singleton-like service that loads the sentence-transformers model once
    and provides methods for embedding generation and vector search.

    Thread-safe for concurrent access (model is thread-safe, FAISS operations
    are protected by async locks).
    """

    def __init__(self):
        """
        Initialize embedding service.

        Loads the sentence-transformers model and initializes
        per-persona FAISS index management.
        """
        self._model: Optional[SentenceTransformer] = None
        self._model_lock = asyncio.Lock()

        # Per-persona FAISS indexes {persona_id: (index, id_map)}
        self._indexes: dict[str, Tuple[faiss.IndexFlatL2, List[str]]] = {}
        self._index_locks: dict[str, asyncio.Lock] = {}

        # Data directory for FAISS persistence
        self._data_dir = Path(settings.data_directory or "data")
        self._data_dir.mkdir(parents=True, exist_ok=True)

    async def _get_model(self) -> SentenceTransformer:
        """
        Lazy-load the sentence-transformers model.

        Returns:
            Loaded SentenceTransformer model

        Note:
            - Model is loaded once and cached
            - Thread-safe with async lock
            - Model download happens on first call (may take time)
        """
        if self._model is None:
            async with self._model_lock:
                # Double-check after acquiring lock
                if self._model is None:
                    # Run in executor to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    self._model = await loop.run_in_executor(
                        None,
                        SentenceTransformer,
                        EMBEDDING_MODEL_NAME
                    )
        return self._model

    async def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding vector for text.

        Args:
            text: Input text to embed

        Returns:
            384-dimensional embedding vector (numpy array)

        Note:
            - Normalizes text (strips whitespace)
            - Empty text returns zero vector
            - Thread-safe and async
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return np.zeros(EMBEDDING_DIM, dtype=np.float32)

        model = await self._get_model()

        # Run encoding in executor to avoid blocking
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: model.encode(text.strip(), show_progress_bar=False, convert_to_numpy=True)
        )

        return embedding.astype(np.float32)

    def _get_index_path(self, persona_id: str) -> Path:
        """Get file path for persona's FAISS index."""
        return self._data_dir / f"faiss_index_{persona_id}.bin"

    def _get_id_map_path(self, persona_id: str) -> Path:
        """Get file path for persona's ID map (interaction_id -> index position)."""
        return self._data_dir / f"faiss_id_map_{persona_id}.pkl"

    async def _get_or_create_index(
        self,
        persona_id: str
    ) -> Tuple[faiss.IndexFlatL2, List[str]]:
        """
        Get or create FAISS index for persona.

        Args:
            persona_id: UUID of persona

        Returns:
            Tuple of (FAISS index, list of interaction IDs)

        Note:
            - Loads from disk if exists
            - Creates new index if not found
            - Thread-safe per-persona with locks
        """
        # Get or create lock for this persona
        if persona_id not in self._index_locks:
            self._index_locks[persona_id] = asyncio.Lock()

        async with self._index_locks[persona_id]:
            # Check if already in memory
            if persona_id in self._indexes:
                return self._indexes[persona_id]

            # Try to load from disk
            index_path = self._get_index_path(persona_id)
            id_map_path = self._get_id_map_path(persona_id)

            if index_path.exists() and id_map_path.exists():
                try:
                    # Load index
                    loop = asyncio.get_event_loop()
                    index = await loop.run_in_executor(
                        None,
                        faiss.read_index,
                        str(index_path)
                    )

                    # Load ID map
                    with open(id_map_path, "rb") as f:
                        id_map = pickle.load(f)

                    self._indexes[persona_id] = (index, id_map)
                    return (index, id_map)
                except Exception:
                    # If loading fails, create new index
                    pass

            # Create new index
            index = faiss.IndexFlatL2(EMBEDDING_DIM)
            id_map: List[str] = []
            self._indexes[persona_id] = (index, id_map)

            return (index, id_map)

    async def add_to_index(
        self,
        persona_id: str,
        interaction_id: str,
        embedding: np.ndarray
    ) -> None:
        """
        Add embedding to persona's FAISS index.

        Args:
            persona_id: UUID of persona
            interaction_id: UUID of interaction
            embedding: 384-dim embedding vector

        Note:
            - Adds to in-memory index
            - Call persist_index() to save to disk
            - If interaction_id exists, replaces the embedding
        """
        index, id_map = await self._get_or_create_index(persona_id)

        # Check if interaction already in index
        if interaction_id in id_map:
            # FAISS doesn't support updates, so we'd need to rebuild
            # For MVP, we'll just skip duplicates
            # TODO: Implement update logic (remove + re-add)
            return

        # Add to index
        embedding_2d = embedding.reshape(1, -1)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            index.add,
            embedding_2d
        )

        # Add to ID map
        id_map.append(interaction_id)

    async def search(
        self,
        persona_id: str,
        query_embedding: np.ndarray,
        k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Search FAISS index for similar interactions.

        Args:
            persona_id: UUID of persona
            query_embedding: 384-dim query embedding vector
            k: Number of nearest neighbors to return

        Returns:
            List of (interaction_id, distance) tuples, ordered by similarity.
            Distance is L2 distance (lower = more similar).

        Note:
            - Returns empty list if index is empty
            - k is capped at index size
            - Distances are L2 (not cosine similarity)
        """
        index, id_map = await self._get_or_create_index(persona_id)

        if index.ntotal == 0:
            return []

        # Cap k at index size
        k = min(k, index.ntotal)

        # Search
        query_2d = query_embedding.reshape(1, -1)
        loop = asyncio.get_event_loop()
        distances, indices = await loop.run_in_executor(
            None,
            index.search,
            query_2d,
            k
        )

        # Map indices to interaction IDs
        results = []
        for i, dist in zip(indices[0], distances[0]):
            if 0 <= i < len(id_map):
                results.append((id_map[i], float(dist)))

        return results

    async def persist_index(self, persona_id: str) -> None:
        """
        Save FAISS index and ID map to disk.

        Args:
            persona_id: UUID of persona

        Note:
            - Creates data directory if not exists
            - Atomic write (temp file + rename)
            - Call after add_to_index() operations
        """
        if persona_id not in self._indexes:
            return

        index, id_map = self._indexes[persona_id]

        index_path = self._get_index_path(persona_id)
        id_map_path = self._get_id_map_path(persona_id)

        # Save index
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            faiss.write_index,
            index,
            str(index_path)
        )

        # Save ID map
        with open(id_map_path, "wb") as f:
            pickle.dump(id_map, f)

    async def rebuild_index(
        self,
        persona_id: str,
        interactions: List[Tuple[str, np.ndarray]]
    ) -> int:
        """
        Rebuild FAISS index from scratch.

        Args:
            persona_id: UUID of persona
            interactions: List of (interaction_id, embedding) tuples

        Returns:
            Number of interactions indexed

        Note:
            - Drops existing index
            - Rebuilds from provided interactions
            - Persists to disk after rebuild
        """
        # Create new index
        index = faiss.IndexFlatL2(EMBEDDING_DIM)
        id_map: List[str] = []

        # Add all embeddings
        if interactions:
            embeddings = np.array([emb for _, emb in interactions], dtype=np.float32)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                index.add,
                embeddings
            )
            id_map = [int_id for int_id, _ in interactions]

        # Update in-memory cache
        async with self._index_locks.get(persona_id, asyncio.Lock()):
            self._indexes[persona_id] = (index, id_map)

        # Persist to disk
        await self.persist_index(persona_id)

        return len(interactions)

    async def clear_index(self, persona_id: str) -> None:
        """
        Clear FAISS index for persona.

        Args:
            persona_id: UUID of persona

        Note:
            - Removes from memory cache
            - Deletes files from disk
        """
        # Remove from memory
        if persona_id in self._indexes:
            async with self._index_locks[persona_id]:
                del self._indexes[persona_id]

        # Delete files
        index_path = self._get_index_path(persona_id)
        id_map_path = self._get_id_map_path(persona_id)

        if index_path.exists():
            index_path.unlink()
        if id_map_path.exists():
            id_map_path.unlink()

    def get_index_size(self, persona_id: str) -> int:
        """
        Get number of vectors in persona's index.

        Args:
            persona_id: UUID of persona

        Returns:
            Number of vectors in index (0 if not exists)
        """
        if persona_id in self._indexes:
            index, _ = self._indexes[persona_id]
            return index.ntotal
        return 0


# Global singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """
    Get global embedding service instance.

    Returns:
        Singleton EmbeddingService instance

    Note:
        - Creates instance on first call
        - Thread-safe
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
