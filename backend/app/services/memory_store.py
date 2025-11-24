"""
SQLite implementation of the Memory Store interface.

Provides concrete implementation of IMemoryStore using SQLAlchemy async
with SQLite backend and FAISS for semantic search.
"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import numpy as np
from sqlalchemy import select, and_, or_, update, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.interfaces.memory_store import IMemoryStore
from app.services.embedding import get_embedding_service
from app.models.belief import (
    BeliefNode,
    BeliefEdge,
    StanceVersion,
    EvidenceLink,
    BeliefUpdate,
)
from app.models.interaction import Interaction
from app.models.persona import Persona
from app.core.database import async_session_maker


# Validation constants
VALID_SOURCE_TYPES = {"reddit_comment", "external_link", "note"}
VALID_EVIDENCE_STRENGTHS = {"weak", "moderate", "strong"}
VALID_INTERACTION_TYPES = {"post", "comment", "reply"}
VALID_STANCE_STATUSES = {"current", "deprecated", "locked"}


class SQLiteMemoryStore(IMemoryStore):
    """
    SQLite implementation of IMemoryStore using SQLAlchemy async.

    Provides full memory management including belief graph, stance versioning,
    evidence linking, interaction logging, and semantic search via FAISS.

    All operations enforce persona isolation and include proper error handling.
    """

    def __init__(self):
        """Initialize memory store with embedding service."""
        self.embedding_service = get_embedding_service()

    async def query_belief_graph(
        self,
        persona_id: str,
        tags: Optional[List[str]] = None,
        min_confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Query the belief graph for a persona.

        Implements IMemoryStore.query_belief_graph with optional filtering.
        """
        # Validate min_confidence
        if min_confidence is not None and not (0.0 <= min_confidence <= 1.0):
            raise ValueError(f"min_confidence must be between 0.0 and 1.0, got {min_confidence}")

        async with async_session_maker() as session:
            # Build query for belief nodes
            stmt = select(BeliefNode).where(BeliefNode.persona_id == persona_id)

            # Apply confidence filter
            if min_confidence is not None:
                stmt = stmt.where(BeliefNode.current_confidence >= min_confidence)

            # Execute node query
            result = await session.execute(stmt)
            nodes = result.scalars().all()

            # Filter by tags if provided
            if tags:
                tags_lower = [t.lower() for t in tags]
                filtered_nodes = []
                for node in nodes:
                    node_tags = node.get_tags()
                    node_tags_lower = [t.lower() for t in node_tags]
                    if any(tag in node_tags_lower for tag in tags_lower):
                        filtered_nodes.append(node)
                nodes = filtered_nodes

            # Query edges for this persona
            edge_stmt = select(BeliefEdge).where(BeliefEdge.persona_id == persona_id)
            edge_result = await session.execute(edge_stmt)
            edges = edge_result.scalars().all()

            # Build response
            nodes_data = [
                {
                    "id": node.id,
                    "title": node.title,
                    "summary": node.summary,
                    "confidence": node.current_confidence,
                    "tags": node.get_tags(),
                    "created_at": node.created_at.isoformat() if node.created_at else None,
                    "updated_at": node.updated_at.isoformat() if node.updated_at else None,
                }
                for node in nodes
            ]

            edges_data = [
                {
                    "id": edge.id,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "relation": edge.relation,
                    "weight": edge.weight,
                    "created_at": edge.created_at.isoformat() if edge.created_at else None,
                }
                for edge in edges
            ]

            return {
                "nodes": nodes_data,
                "edges": edges_data,
            }

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
        Update belief stance with lock enforcement.

        Implements IMemoryStore.update_stance_version with full atomicity.
        """
        # Validate confidence range
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")

        async with async_session_maker() as session:
            async with session.begin():
                # Fetch belief with current stance
                stmt = (
                    select(BeliefNode)
                    .where(
                        and_(
                            BeliefNode.id == belief_id,
                            BeliefNode.persona_id == persona_id
                        )
                    )
                    .options(selectinload(BeliefNode.stance_versions))
                )
                result = await session.execute(stmt)
                belief = result.scalar_one_or_none()

                if not belief:
                    raise ValueError(f"Belief {belief_id} not found for persona {persona_id}")

                # Find current stance
                current_stance = None
                for stance in belief.stance_versions:
                    if stance.status == "current":
                        current_stance = stance
                        break

                # Check if locked
                if current_stance and current_stance.status == "locked":
                    raise PermissionError(
                        f"Stance for belief {belief_id} is locked and cannot be updated automatically"
                    )

                # Capture old value for audit log
                old_value = {}
                if current_stance:
                    old_value = {
                        "text": current_stance.text,
                        "confidence": current_stance.confidence,
                        "status": current_stance.status,
                    }

                # Mark current stance as deprecated (if exists)
                if current_stance:
                    current_stance.status = "deprecated"
                    session.add(current_stance)

                # Create new stance version
                new_stance = StanceVersion(
                    persona_id=persona_id,
                    belief_id=belief_id,
                    text=text,
                    confidence=confidence,
                    status="current",
                    rationale=rationale,
                )
                session.add(new_stance)
                await session.flush()  # Get new_stance.id

                # Update belief node's current_confidence
                belief.current_confidence = confidence
                session.add(belief)

                # Log update to belief_updates
                new_value = {
                    "text": text,
                    "confidence": confidence,
                    "status": "current",
                }

                update_log = BeliefUpdate(
                    persona_id=persona_id,
                    belief_id=belief_id,
                    old_value=json.dumps(old_value),
                    new_value=json.dumps(new_value),
                    reason=rationale,
                    trigger_type="agent",
                    updated_by=updated_by,
                )
                session.add(update_log)

                await session.commit()

                return new_stance.id

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

        Implements IMemoryStore.append_evidence with validation.
        """
        # Validate enums
        if source_type not in VALID_SOURCE_TYPES:
            raise ValueError(
                f"Invalid source_type: {source_type}. Must be one of {VALID_SOURCE_TYPES}"
            )

        if strength not in VALID_EVIDENCE_STRENGTHS:
            raise ValueError(
                f"Invalid strength: {strength}. Must be one of {VALID_EVIDENCE_STRENGTHS}"
            )

        async with async_session_maker() as session:
            async with session.begin():
                # Verify belief exists and belongs to persona
                stmt = select(BeliefNode).where(
                    and_(
                        BeliefNode.id == belief_id,
                        BeliefNode.persona_id == persona_id
                    )
                )
                result = await session.execute(stmt)
                belief = result.scalar_one_or_none()

                if not belief:
                    raise ValueError(f"Belief {belief_id} not found for persona {persona_id}")

                # Create evidence link
                evidence = EvidenceLink(
                    persona_id=persona_id,
                    belief_id=belief_id,
                    source_type=source_type,
                    source_ref=source_ref,
                    strength=strength,
                )
                session.add(evidence)

                # Update belief's updated_at timestamp
                belief.updated_at = datetime.utcnow()
                session.add(belief)

                await session.commit()

                return evidence.id

    async def log_interaction(
        self,
        persona_id: str,
        content: str,
        interaction_type: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Log Reddit interaction to episodic memory.

        Implements IMemoryStore.log_interaction.
        """
        # Validate interaction type
        if interaction_type not in VALID_INTERACTION_TYPES:
            raise ValueError(
                f"Invalid interaction_type: {interaction_type}. "
                f"Must be one of {VALID_INTERACTION_TYPES}"
            )

        # Validate required metadata fields
        if "reddit_id" not in metadata:
            raise ValueError("metadata must contain 'reddit_id'")
        if "subreddit" not in metadata:
            raise ValueError("metadata must contain 'subreddit'")

        async with async_session_maker() as session:
            async with session.begin():
                # Verify persona exists
                stmt = select(Persona).where(Persona.id == persona_id)
                result = await session.execute(stmt)
                persona = result.scalar_one_or_none()

                if not persona:
                    raise ValueError(f"Persona {persona_id} not found")

                # Extract fields from metadata
                reddit_id = metadata["reddit_id"]
                subreddit = metadata["subreddit"]
                parent_id = metadata.get("parent_id")

                # Create interaction
                interaction = Interaction(
                    persona_id=persona_id,
                    content=content,
                    interaction_type=interaction_type,
                    reddit_id=reddit_id,
                    subreddit=subreddit,
                    parent_id=parent_id,
                )

                # Store full metadata as JSON
                interaction.set_metadata(metadata)

                session.add(interaction)
                await session.commit()

                return interaction.id

    async def add_interaction_embedding(
        self,
        interaction_id: str,
        persona_id: str
    ) -> None:
        """
        Generate and store embedding for interaction.

        Implements IMemoryStore.add_interaction_embedding.
        """
        async with async_session_maker() as session:
            # Fetch interaction
            stmt = select(Interaction).where(
                and_(
                    Interaction.id == interaction_id,
                    Interaction.persona_id == persona_id
                )
            )
            result = await session.execute(stmt)
            interaction = result.scalar_one_or_none()

            if not interaction:
                raise ValueError(
                    f"Interaction {interaction_id} not found for persona {persona_id}"
                )

            # Generate embedding
            embedding = await self.embedding_service.generate_embedding(interaction.content)

            # Add to FAISS index
            await self.embedding_service.add_to_index(
                persona_id=persona_id,
                interaction_id=interaction_id,
                embedding=embedding
            )

            # Persist index to disk
            await self.embedding_service.persist_index(persona_id)

    async def search_history(
        self,
        persona_id: str,
        query: str,
        limit: int = 5,
        subreddit: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search interaction history using semantic similarity.

        Implements IMemoryStore.search_history with FAISS.
        """
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")

        # Generate query embedding
        query_embedding = await self.embedding_service.generate_embedding(query)

        # Search FAISS index
        search_results = await self.embedding_service.search(
            persona_id=persona_id,
            query_embedding=query_embedding,
            k=limit * 2  # Get more to allow for subreddit filtering
        )

        if not search_results:
            return []

        # Fetch interactions from database
        interaction_ids = [int_id for int_id, _ in search_results]

        async with async_session_maker() as session:
            stmt = select(Interaction).where(
                and_(
                    Interaction.id.in_(interaction_ids),
                    Interaction.persona_id == persona_id
                )
            )

            # Apply subreddit filter if provided
            if subreddit:
                stmt = stmt.where(
                    func.lower(Interaction.subreddit) == subreddit.lower()
                )

            result = await session.execute(stmt)
            interactions = result.scalars().all()

            # Build result dict keyed by interaction_id
            interaction_dict = {i.id: i for i in interactions}

            # Match with search results and compute similarity scores
            results = []
            for int_id, distance in search_results:
                if int_id not in interaction_dict:
                    continue

                interaction = interaction_dict[int_id]

                # Convert L2 distance to similarity score (0-1, higher is better)
                # Using simple inverse: similarity = 1 / (1 + distance)
                similarity_score = 1.0 / (1.0 + distance)

                results.append({
                    "id": interaction.id,
                    "content": interaction.content,
                    "interaction_type": interaction.interaction_type,
                    "reddit_id": interaction.reddit_id,
                    "subreddit": interaction.subreddit,
                    "parent_id": interaction.parent_id,
                    "metadata": interaction.get_metadata(),
                    "similarity_score": similarity_score,
                    "created_at": (
                        interaction.created_at.isoformat() if interaction.created_at else None
                    ),
                })

                # Stop once we have enough results
                if len(results) >= limit:
                    break

            return results

    async def rebuild_faiss_index(
        self,
        persona_id: str
    ) -> int:
        """
        Rebuild FAISS index from all interactions.

        Implements IMemoryStore.rebuild_faiss_index.
        """
        async with async_session_maker() as session:
            # Verify persona exists
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            persona = result.scalar_one_or_none()

            if not persona:
                raise ValueError(f"Persona {persona_id} not found")

            # Fetch all interactions for persona
            stmt = select(Interaction).where(Interaction.persona_id == persona_id)
            result = await session.execute(stmt)
            interactions = result.scalars().all()

            if not interactions:
                # Empty index
                await self.embedding_service.clear_index(persona_id)
                return 0

            # Generate embeddings for all interactions
            interaction_embeddings = []
            for interaction in interactions:
                embedding = await self.embedding_service.generate_embedding(interaction.content)
                interaction_embeddings.append((interaction.id, embedding))

            # Rebuild index
            count = await self.embedding_service.rebuild_index(
                persona_id=persona_id,
                interactions=interaction_embeddings
            )

            return count

    async def get_belief_with_stances(
        self,
        persona_id: str,
        belief_id: str
    ) -> Dict[str, Any]:
        """
        Get belief with full stance history, evidence, and updates.

        Implements IMemoryStore.get_belief_with_stances.
        """
        async with async_session_maker() as session:
            # Fetch belief with relationships
            stmt = (
                select(BeliefNode)
                .where(
                    and_(
                        BeliefNode.id == belief_id,
                        BeliefNode.persona_id == persona_id
                    )
                )
                .options(
                    selectinload(BeliefNode.stance_versions),
                    selectinload(BeliefNode.evidence_links),
                    selectinload(BeliefNode.belief_updates),
                )
            )
            result = await session.execute(stmt)
            belief = result.scalar_one_or_none()

            if not belief:
                raise ValueError(f"Belief {belief_id} not found for persona {persona_id}")

            # Build belief data
            belief_data = {
                "id": belief.id,
                "title": belief.title,
                "summary": belief.summary,
                "current_confidence": belief.current_confidence,
                "tags": belief.get_tags(),
                "created_at": belief.created_at.isoformat() if belief.created_at else None,
                "updated_at": belief.updated_at.isoformat() if belief.updated_at else None,
            }

            # Sort and format stances (newest first)
            stances = sorted(belief.stance_versions, key=lambda s: s.created_at, reverse=True)
            stances_data = [
                {
                    "id": stance.id,
                    "text": stance.text,
                    "confidence": stance.confidence,
                    "status": stance.status,
                    "rationale": stance.rationale,
                    "created_at": stance.created_at.isoformat() if stance.created_at else None,
                }
                for stance in stances
            ]

            # Sort and format evidence (newest first)
            evidence = sorted(belief.evidence_links, key=lambda e: e.created_at, reverse=True)
            evidence_data = [
                {
                    "id": ev.id,
                    "source_type": ev.source_type,
                    "source_ref": ev.source_ref,
                    "strength": ev.strength,
                    "created_at": ev.created_at.isoformat() if ev.created_at else None,
                }
                for ev in evidence
            ]

            # Sort and format updates (newest first)
            updates = sorted(belief.belief_updates, key=lambda u: u.created_at, reverse=True)
            updates_data = [
                {
                    "id": upd.id,
                    "old_value": upd.get_old_value(),
                    "new_value": upd.get_new_value(),
                    "reason": upd.reason,
                    "trigger_type": upd.trigger_type,
                    "updated_by": upd.updated_by,
                    "created_at": upd.created_at.isoformat() if upd.created_at else None,
                }
                for upd in updates
            ]

            return {
                "belief": belief_data,
                "stances": stances_data,
                "evidence": evidence_data,
                "updates": updates_data,
            }
