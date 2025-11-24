"""
Memory Store Interface (IMemoryStore)

Abstract base class defining the contract for the agent's memory system.
Provides methods for belief graph queries, stance updates, evidence linking,
interaction logging, and semantic history search.

Implementation guide:
- All methods must be async
- All operations must enforce persona isolation
- Lock enforcement is mandatory for stance updates
- FAISS index operations must be atomic
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class IMemoryStore(ABC):
    """
    Abstract interface for agent memory and belief graph operations.

    The memory store manages:
    1. Belief graph (nodes + edges)
    2. Stance versions with lock enforcement
    3. Evidence links to support beliefs
    4. Interaction history (episodic memory)
    5. Semantic search via FAISS

    All operations are scoped by persona_id to ensure multi-persona isolation.
    """

    @abstractmethod
    async def query_belief_graph(
        self,
        persona_id: str,
        tags: Optional[List[str]] = None,
        min_confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Query the belief graph for a persona.

        Returns the complete belief graph structure with nodes and edges,
        optionally filtered by tags or minimum confidence level.

        Args:
            persona_id: UUID of the persona
            tags: Optional list of tags to filter beliefs
            min_confidence: Optional minimum confidence threshold (0.0-1.0)

        Returns:
            Dictionary with structure:
            {
                "nodes": [
                    {
                        "id": "belief-uuid",
                        "title": "Belief title",
                        "summary": "Detailed description",
                        "confidence": 0.85,
                        "tags": ["tag1", "tag2"],
                        "created_at": "2025-11-24T...",
                        "updated_at": "2025-11-24T..."
                    },
                    ...
                ],
                "edges": [
                    {
                        "id": "edge-uuid",
                        "source_id": "belief-uuid-1",
                        "target_id": "belief-uuid-2",
                        "relation": "supports",  # or contradicts, depends_on, evidence_for
                        "weight": 0.7,
                        "created_at": "2025-11-24T..."
                    },
                    ...
                ]
            }

        Raises:
            ValueError: If persona_id is invalid or min_confidence out of range

        Note:
            - All nodes and edges belong to the specified persona
            - Confidence filtering applies to current_confidence in belief nodes
            - Tag filtering is case-insensitive and matches any tag in the list
        """
        pass

    @abstractmethod
    async def update_stance_version(
        self,
        persona_id: str,
        belief_id: str,
        text: str,
        confidence: float,
        rationale: str,
        updated_by: str = "agent"
    ) -> str:
        """
        Update a belief's stance to a new version.

        Creates a new stance version and marks the current one as deprecated.
        Enforces lock checking: if current stance is locked, update is rejected.
        Logs the update to belief_updates table for audit trail.

        Args:
            persona_id: UUID of the persona
            belief_id: UUID of the belief to update
            text: New stance text
            confidence: New confidence level (0.0-1.0)
            rationale: Explanation for the update
            updated_by: Who/what triggered the update (default: "agent")

        Returns:
            UUID of the newly created stance version

        Raises:
            ValueError: If belief not found, persona mismatch, or confidence out of range
            PermissionError: If current stance is locked

        Note:
            - Operation is atomic (uses transaction)
            - Current stance status changed from "current" to "deprecated"
            - New stance created with status "current"
            - Belief node's current_confidence updated
            - Update logged to belief_updates with old/new value snapshots
            - Lock enforcement: status="locked" prevents automatic updates
        """
        pass

    @abstractmethod
    async def append_evidence(
        self,
        persona_id: str,
        belief_id: str,
        source_type: str,
        source_ref: str,
        strength: str
    ) -> str:
        """
        Link evidence to a belief.

        Creates an evidence link record connecting external sources to beliefs.
        Valid source types and strength levels are validated.

        Args:
            persona_id: UUID of the persona
            belief_id: UUID of the belief
            source_type: Type of evidence source
                Must be one of: "reddit_comment", "external_link", "note"
            source_ref: Reference to the source
                - For reddit_comment: reddit ID (e.g., "t1_abc123")
                - For external_link: full URL
                - For note: freeform text
            strength: Strength of the evidence
                Must be one of: "weak", "moderate", "strong"

        Returns:
            UUID of the created evidence link

        Raises:
            ValueError: If belief not found, persona mismatch, or invalid enum values

        Note:
            - Updates belief node's updated_at timestamp
            - Source type and strength are validated against allowed values
            - Evidence links are immutable once created
            - Use for Bayesian updates: weak=0.05, moderate=0.10, strong=0.20 delta
        """
        pass

    @abstractmethod
    async def log_interaction(
        self,
        persona_id: str,
        content: str,
        interaction_type: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Log a Reddit interaction to episodic memory.

        Stores interaction details and optionally generates embedding for semantic search.
        Interaction is indexed for retrieval and added to FAISS for vector search.

        Args:
            persona_id: UUID of the persona
            content: Text content of the interaction
            interaction_type: Type of interaction
                Must be one of: "post", "comment", "reply"
            metadata: Dictionary with interaction details:
                Required fields:
                    - reddit_id: Reddit's unique ID (e.g., "t1_abc123", "t3_def456")
                    - subreddit: Subreddit name (without r/ prefix)
                Optional fields:
                    - parent_id: Parent reddit ID if reply/comment
                    - score: Reddit karma score
                    - author: Original author username
                    - timestamp: Reddit creation timestamp
                    - url: Direct link to Reddit item

        Returns:
            UUID of the created interaction record

        Raises:
            ValueError: If persona not found, invalid interaction_type, or missing required metadata

        Note:
            - reddit_id must be unique across all interactions
            - Embedding generation is deferred (see add_interaction_embedding)
            - Interaction ID returned can be used to associate embedding later
            - parent_id should be null for top-level posts
        """
        pass

    @abstractmethod
    async def search_history(
        self,
        persona_id: str,
        query: str,
        limit: int = 5,
        subreddit: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search interaction history using semantic similarity.

        Generates embedding for query and searches FAISS index for similar
        past interactions. Optionally filters by subreddit.

        Args:
            persona_id: UUID of the persona
            query: Natural language query (e.g., "my views on climate change")
            limit: Maximum number of results to return (default: 5)
            subreddit: Optional subreddit filter (exact match, case-insensitive)

        Returns:
            List of matching interactions, ordered by similarity:
            [
                {
                    "id": "interaction-uuid",
                    "content": "The interaction text",
                    "interaction_type": "comment",
                    "reddit_id": "t1_abc123",
                    "subreddit": "AskReddit",
                    "parent_id": "t3_def456",
                    "metadata": {...},
                    "similarity_score": 0.87,
                    "created_at": "2025-11-24T..."
                },
                ...
            ]

        Raises:
            ValueError: If persona not found or limit < 1

        Note:
            - Returns empty list if FAISS index is empty or not built
            - Similarity scores range from 0.0 (dissimilar) to 1.0 (identical)
            - Subreddit filter applied after similarity search
            - If limit exceeds available interactions, returns all matches
            - Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384 dim)
        """
        pass

    @abstractmethod
    async def add_interaction_embedding(
        self,
        interaction_id: str,
        persona_id: str
    ) -> None:
        """
        Generate and store embedding for an interaction.

        Generates embedding vector from interaction content and adds to FAISS index.
        Called after log_interaction to decouple embedding generation from logging.

        Args:
            interaction_id: UUID of the interaction
            persona_id: UUID of the persona (for validation)

        Raises:
            ValueError: If interaction not found or persona mismatch

        Note:
            - Uses sentence-transformers/all-MiniLM-L6-v2
            - Embedding stored in interactions table (optional BLOB backup)
            - Primary storage in FAISS index with interaction_id as key
            - FAISS index persisted to data/faiss_index_{persona_id}.bin
            - Safe to call multiple times (overwrites existing embedding)
        """
        pass

    @abstractmethod
    async def rebuild_faiss_index(
        self,
        persona_id: str
    ) -> int:
        """
        Rebuild FAISS index from all interactions for a persona.

        Useful when index file is missing, corrupted, or after bulk imports.
        Regenerates embeddings for all interactions and rebuilds index.

        Args:
            persona_id: UUID of the persona

        Returns:
            Number of interactions indexed

        Raises:
            ValueError: If persona not found

        Note:
            - Drops existing index and rebuilds from scratch
            - Generates embeddings for interactions without them
            - Can be slow for large histories (100+ interactions)
            - Index saved to data/faiss_index_{persona_id}.bin
            - Safe to call concurrently (per-persona locks)
        """
        pass

    @abstractmethod
    async def get_belief_with_stances(
        self,
        persona_id: str,
        belief_id: str
    ) -> Dict[str, Any]:
        """
        Get a belief with its full stance history.

        Retrieves belief node with all stance versions, evidence links,
        and update audit log.

        Args:
            persona_id: UUID of the persona
            belief_id: UUID of the belief

        Returns:
            Dictionary with structure:
            {
                "belief": {
                    "id": "belief-uuid",
                    "title": "Belief title",
                    "summary": "Description",
                    "current_confidence": 0.85,
                    "tags": ["tag1", "tag2"],
                    "created_at": "...",
                    "updated_at": "..."
                },
                "stances": [
                    {
                        "id": "stance-uuid",
                        "text": "Stance description",
                        "confidence": 0.85,
                        "status": "current",
                        "rationale": "Why this stance",
                        "created_at": "..."
                    },
                    ...
                ],
                "evidence": [
                    {
                        "id": "evidence-uuid",
                        "source_type": "reddit_comment",
                        "source_ref": "t1_abc123",
                        "strength": "strong",
                        "created_at": "..."
                    },
                    ...
                ],
                "updates": [
                    {
                        "id": "update-uuid",
                        "old_value": {...},
                        "new_value": {...},
                        "reason": "New evidence from r/science",
                        "trigger_type": "evidence",
                        "updated_by": "agent",
                        "created_at": "..."
                    },
                    ...
                ]
            }

        Raises:
            ValueError: If belief not found or persona mismatch

        Note:
            - Stances ordered by created_at DESC (newest first)
            - Evidence ordered by created_at DESC
            - Updates ordered by created_at DESC
            - Useful for dashboard belief detail view
        """
        pass
