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

    def __init__(self, session_or_maker=None):
        """
        Initialize memory store with embedding service.

        Args:
            session_or_maker: Either an AsyncSession (for tests) or async session factory.
                             Defaults to the global async_session_maker.
        """
        self.embedding_service = get_embedding_service()

        # Handle both session and session_maker
        if session_or_maker is None:
            self.session_maker = async_session_maker
            self.provided_session = None
        elif callable(session_or_maker):
            self.session_maker = session_or_maker
            self.provided_session = None
        else:
            # It's a session object, not a maker
            self.session_maker = None
            self.provided_session = session_or_maker

    def _get_session(self):
        """Get session context manager or provided session."""
        if self.provided_session is not None:
            # Return a no-op context manager that yields the provided session
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def session_context():
                yield self.provided_session

            return session_context()
        else:
            return self.session_maker()

    def _begin_transaction(self, session):
        """Begin transaction if using session_maker, else no-op for provided session."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def transaction_context():
            if self.provided_session is not None:
                # Don't start a new transaction for provided session
                yield
            else:
                # Start transaction for session_maker sessions
                async with session.begin():
                    yield

        return transaction_context()

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

        async with self._get_session() as session:
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
                    "created_at": (
                        node.created_at.isoformat()
                        if hasattr(node.created_at, "isoformat")
                        else node.created_at
                    ),
                    "updated_at": (
                        node.updated_at.isoformat()
                        if hasattr(node.updated_at, "isoformat")
                        else node.updated_at
                    ),
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
                    "created_at": (
                        edge.created_at.isoformat()
                        if hasattr(edge.created_at, "isoformat")
                        else edge.created_at
                    ),
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

        async with self._get_session() as session:
            async with self._begin_transaction(session):
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

                # Find current or locked stance
                current_stance = None
                for stance in belief.stance_versions:
                    if stance.status in ("current", "locked"):
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

                if self.provided_session is None:
                    await session.commit()
                else:
                    await session.flush()

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

        async with self._get_session() as session:
            async with self._begin_transaction(session):
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

                if self.provided_session is None:
                    await session.commit()
                else:
                    await session.flush()

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

        async with self._get_session() as session:
            async with self._begin_transaction(session):
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
                if self.provided_session is None:
                    await session.commit()
                else:
                    await session.flush()
                interaction_id = interaction.id

        # Generate embedding and persist to FAISS outside transaction
        try:
            await self.add_interaction_embedding(
                interaction_id=interaction_id,
                persona_id=persona_id
            )
        except Exception:
            # Do not fail the logging call if embedding generation fails;
            # caller can rebuild the index later via rebuild_faiss_index.
            pass

        return interaction_id

    async def add_interaction_embedding(
        self,
        interaction_id: str,
        persona_id: str
    ) -> None:
        """
        Generate and store embedding for interaction.

        Implements IMemoryStore.add_interaction_embedding.
        """
        async with self._get_session() as session:
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

        async with self._get_session() as session:
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
                        interaction.created_at.isoformat()
                        if hasattr(interaction.created_at, "isoformat")
                        else interaction.created_at
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
        async with self._get_session() as session:
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
        async with self._get_session() as session:
            # Expire cache if using provided session to ensure we see latest data
            if self.provided_session is not None:
                session.expire_all()

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
                "created_at": (
                    belief.created_at.isoformat()
                    if hasattr(belief.created_at, "isoformat")
                    else belief.created_at
                ),
                "updated_at": (
                    belief.updated_at.isoformat()
                    if hasattr(belief.updated_at, "isoformat")
                    else belief.updated_at
                ),
            }

            # Sort and format stances (current first, then by newest)
            # Status priority ensures current stances appear first
            status_priority = {"current": 0, "locked": 1, "deprecated": 2}
            def stance_sort_key(s):
                # Primary: status (current first)
                # Secondary: created_at (newest first, so negate for ascending sort)
                created = s.created_at
                if isinstance(created, str):
                    # For string timestamps, newer = higher string value in ISO format
                    # Negate by reversing to make newer come first
                    return (status_priority.get(s.status, 9), created)
                return (status_priority.get(s.status, 9), created)

            stances = sorted(belief.stance_versions, key=stance_sort_key, reverse=False)
            # But we want newest created_at first within each status, so reverse=True for created_at part
            # Let's use a simpler approach: sort by status ascending, then created_at descending
            stances = sorted(belief.stance_versions, key=lambda s: s.created_at, reverse=True)
            stances = sorted(stances, key=lambda s: status_priority.get(s.status, 9))
            stances_data = [
                {
                    "id": stance.id,
                    "text": stance.text,
                    "confidence": stance.confidence,
                    "status": stance.status,
                    "rationale": stance.rationale,
                    "created_at": (
                        stance.created_at.isoformat()
                        if hasattr(stance.created_at, "isoformat")
                        else stance.created_at
                    ),
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
                    "created_at": (
                        ev.created_at.isoformat()
                        if hasattr(ev.created_at, "isoformat")
                        else ev.created_at
                    ),
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
                    "created_at": (
                        upd.created_at.isoformat()
                        if hasattr(upd.created_at, "isoformat")
                        else upd.created_at
                    ),
                }
                for upd in updates
            ]

            return {
                "belief": belief_data,
                "stances": stances_data,
                "evidence": evidence_data,
                "updates": updates_data,
            }

    async def lock_stance(
        self,
        persona_id: str,
        belief_id: str,
        reason: Optional[str] = None,
        updated_by: str = "admin"
    ) -> None:
        """
        Lock the current stance to prevent automatic updates.

        Args:
            persona_id: UUID of persona
            belief_id: UUID of belief
            reason: Optional reason for locking
            updated_by: Who locked the stance (default: "admin")

        Raises:
            ValueError: If belief not found or no current stance exists
        """
        async with self._get_session() as session:
            async with self._begin_transaction(session):
                # Fetch belief with stances
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

                if not current_stance:
                    raise ValueError(f"No current stance found for belief {belief_id}")

                # Update status to locked
                old_status = current_stance.status
                current_stance.status = "locked"
                session.add(current_stance)

                # Log the action
                lock_reason = reason or "Stance locked to prevent automatic updates"
                update_log = BeliefUpdate(
                    persona_id=persona_id,
                    belief_id=belief_id,
                    old_value=json.dumps({"status": old_status}),
                    new_value=json.dumps({"status": "locked"}),
                    reason=lock_reason,
                    trigger_type="manual",
                    updated_by=updated_by,
                )
                session.add(update_log)

                if self.provided_session is None:
                    await session.commit()

    async def unlock_stance(
        self,
        persona_id: str,
        belief_id: str,
        reason: Optional[str] = None,
        updated_by: str = "admin"
    ) -> None:
        """
        Unlock a locked stance to allow automatic updates.

        Args:
            persona_id: UUID of persona
            belief_id: UUID of belief
            reason: Optional reason for unlocking
            updated_by: Who unlocked the stance (default: "admin")

        Raises:
            ValueError: If belief not found or no locked stance exists
        """
        async with self._get_session() as session:
            async with self._begin_transaction(session):
                # Fetch belief with stances
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

                # Find locked stance
                locked_stance = None
                for stance in belief.stance_versions:
                    if stance.status == "locked":
                        locked_stance = stance
                        break

                if not locked_stance:
                    raise ValueError(f"No locked stance found for belief {belief_id}")

                # Update status back to current
                old_status = locked_stance.status
                locked_stance.status = "current"
                session.add(locked_stance)

                # Log the action
                unlock_reason = reason or "Stance unlocked to allow automatic updates"
                update_log = BeliefUpdate(
                    persona_id=persona_id,
                    belief_id=belief_id,
                    old_value=json.dumps({"status": old_status}),
                    new_value=json.dumps({"status": "current"}),
                    reason=unlock_reason,
                    trigger_type="manual",
                    updated_by=updated_by,
                )
                session.add(update_log)

                if self.provided_session is None:
                    await session.commit()

    async def get_interactions_with_cost(
        self,
        persona_id: str,
        since: Optional[datetime] = None
    ) -> List[Interaction]:
        """
        Get interactions with cost metadata for cost tracking.

        Args:
            persona_id: UUID of the persona
            since: Optional datetime to filter interactions created after this date

        Returns:
            List of Interaction objects with cost metadata
        """
        async with self._get_session() as session:
            # Build query for interactions
            stmt = select(Interaction).where(Interaction.persona_id == persona_id)

            # Apply date filter if provided
            if since:
                stmt = stmt.where(Interaction.created_at >= since)

            # Order by created_at descending (newest first)
            stmt = stmt.order_by(desc(Interaction.created_at))

            result = await session.execute(stmt)
            interactions = result.scalars().all()

            # Filter to only include interactions with cost data in metadata
            return [
                i for i in interactions
                if i.get_metadata() and "cost" in i.get_metadata()
            ]

    async def get_persona(
        self,
        persona_id: str
    ) -> Dict[str, Any]:
        """
        Get persona by ID.

        Implements IMemoryStore.get_persona.
        """
        async with self._get_session() as session:
            # Fetch persona
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            persona = result.scalar_one_or_none()

            if not persona:
                raise ValueError(f"Persona {persona_id} not found")

            # Build persona dict
            return {
                "id": persona.id,
                "reddit_username": persona.reddit_username,
                "display_name": persona.display_name,
                "config": persona.get_config(),
                "created_at": (
                    persona.created_at.isoformat()
                    if hasattr(persona.created_at, "isoformat")
                    else persona.created_at
                ),
                "updated_at": (
                    persona.updated_at.isoformat()
                    if hasattr(persona.updated_at, "isoformat")
                    else persona.updated_at
                ),
            }

    async def search_interactions(
        self,
        persona_id: str,
        reddit_id: str
    ) -> List[Dict[str, Any]]:
        """
        Search for interactions by Reddit ID.

        Implements IMemoryStore.search_interactions.
        """
        async with self._get_session() as session:
            # Verify persona exists
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            persona = result.scalar_one_or_none()

            if not persona:
                raise ValueError(f"Persona {persona_id} not found")

            # Search interactions by reddit_id or parent_id
            stmt = select(Interaction).where(
                and_(
                    Interaction.persona_id == persona_id,
                    or_(
                        Interaction.reddit_id == reddit_id,
                        Interaction.parent_id == reddit_id
                    )
                )
            )

            result = await session.execute(stmt)
            interactions = result.scalars().all()

            # Build result list
            return [
                {
                    "id": interaction.id,
                    "content": interaction.content,
                    "interaction_type": interaction.interaction_type,
                    "reddit_id": interaction.reddit_id,
                    "subreddit": interaction.subreddit,
                    "parent_id": interaction.parent_id,
                    "metadata": interaction.get_metadata(),
                    "created_at": (
                        interaction.created_at.isoformat()
                        if hasattr(interaction.created_at, "isoformat")
                        else interaction.created_at
                    ),
                }
                for interaction in interactions
            ]
