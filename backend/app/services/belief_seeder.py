"""
Belief seeding service for initializing personas with core beliefs.

Provides functionality to seed personas with initial conviction sets
and belief graph relationships. Follows quality patterns from 0_dev.md:
- Separation of responsibilities via dependency injection
- Explicit interfaces and error handling
- Auditable state transitions with full logging
"""

import json
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.belief import BeliefNode, BeliefEdge, StanceVersion
from app.models.persona import Persona

logger = logging.getLogger(__name__)


# Default core beliefs for new personas
DEFAULT_BELIEFS = [
    {
        "title": "Evidence-based reasoning",
        "summary": "Strong claims require strong evidence. I prefer empirical data and peer-reviewed sources over anecdotes.",
        "confidence": 0.95,
        "tags": ["epistemology", "core-value", "reasoning"],
    },
    {
        "title": "AI alignment is important",
        "summary": "As AI systems become more capable, ensuring they remain aligned with human values is crucial for long-term safety.",
        "confidence": 0.82,
        "tags": ["AI", "safety", "technology"],
    },
    {
        "title": "Open-source benefits society",
        "summary": "Open-source software and transparent research accelerate innovation and enable broader participation in technological progress.",
        "confidence": 0.78,
        "tags": ["technology", "society", "policy"],
    },
    {
        "title": "Climate change requires action",
        "summary": "Scientific consensus strongly supports that human-caused climate change is real and requires urgent mitigation efforts.",
        "confidence": 0.91,
        "tags": ["science", "environment", "policy"],
    },
    {
        "title": "Civility in discourse",
        "summary": "Productive conversations require good-faith engagement, even when disagreeing. Personal attacks undermine understanding.",
        "confidence": 0.88,
        "tags": ["core-value", "communication", "ethics"],
    },
    {
        "title": "Bayesian updating",
        "summary": "Beliefs should be updated proportionally to the strength and quality of new evidence encountered.",
        "confidence": 0.85,
        "tags": ["epistemology", "reasoning", "core-value"],
    },
    {
        "title": "Privacy is a right",
        "summary": "Individuals should have control over their personal data and the ability to maintain privacy in digital spaces.",
        "confidence": 0.80,
        "tags": ["ethics", "technology", "policy"],
    },
    {
        "title": "Skepticism of absolute claims",
        "summary": "Very few things are absolutely certain. Healthy skepticism and acknowledgment of uncertainty lead to better reasoning.",
        "confidence": 0.87,
        "tags": ["epistemology", "reasoning", "core-value"],
    },
]

# Default relationships between beliefs
DEFAULT_EDGES = [
    {
        "source": "Evidence-based reasoning",
        "target": "Bayesian updating",
        "relation": "supports",
        "weight": 0.9,
    },
    {
        "source": "Evidence-based reasoning",
        "target": "Skepticism of absolute claims",
        "relation": "supports",
        "weight": 0.85,
    },
    {
        "source": "Bayesian updating",
        "target": "Skepticism of absolute claims",
        "relation": "supports",
        "weight": 0.75,
    },
    {
        "source": "Evidence-based reasoning",
        "target": "Climate change requires action",
        "relation": "evidence_for",
        "weight": 0.95,
    },
    {
        "source": "Open-source benefits society",
        "target": "AI alignment is important",
        "relation": "depends_on",
        "weight": 0.6,
    },
    {
        "source": "Civility in discourse",
        "target": "Skepticism of absolute claims",
        "relation": "supports",
        "weight": 0.7,
    },
]


class BeliefSeeder:
    """
    Service for seeding personas with initial beliefs.

    Encapsulates belief initialization logic following interface-first design
    and dependency injection patterns from engineering standards.
    """

    async def seed_persona_beliefs(
        self,
        session: AsyncSession,
        persona_id: str,
        beliefs: Optional[list[dict]] = None,
        edges: Optional[list[dict]] = None,
    ) -> tuple[int, int]:
        """
        Seed a persona with initial beliefs and relationships.

        Args:
            session: Database session for transaction management
            persona_id: UUID of persona to seed
            beliefs: List of belief definitions (uses defaults if None)
            edges: List of belief edge definitions (uses defaults if None)

        Returns:
            Tuple of (beliefs_created, edges_created)

        Raises:
            ValueError: If persona not found or beliefs already exist
        """
        # Use defaults if not provided
        beliefs_to_create = beliefs or DEFAULT_BELIEFS
        edges_to_create = edges or DEFAULT_EDGES

        # Verify persona exists
        stmt = select(Persona).where(Persona.id == persona_id)
        result = await session.execute(stmt)
        persona = result.scalar_one_or_none()

        if not persona:
            raise ValueError(f"Persona not found: {persona_id}")

        # Check if beliefs already exist
        stmt = select(BeliefNode).where(BeliefNode.persona_id == persona_id)
        result = await session.execute(stmt)
        existing_beliefs = result.scalars().all()

        if existing_beliefs:
            logger.info(
                f"Beliefs already exist for persona {persona_id}, skipping seeding",
                extra={"persona_id": persona_id, "belief_count": len(existing_beliefs)}
            )
            return (0, 0)

        logger.info(
            f"Seeding beliefs for persona {persona_id}",
            extra={"persona_id": persona_id, "belief_count": len(beliefs_to_create)}
        )

        # Create belief nodes
        belief_nodes = []
        for belief_data in beliefs_to_create:
            node = BeliefNode(
                persona_id=persona_id,
                title=belief_data["title"],
                summary=belief_data["summary"],
                current_confidence=belief_data["confidence"],
                tags=json.dumps(belief_data["tags"]),
            )
            session.add(node)
            await session.flush()  # Get ID for relationships
            belief_nodes.append(node)

            # Create initial stance version
            stance = StanceVersion(
                persona_id=persona_id,
                belief_id=node.id,
                text=belief_data["summary"],
                confidence=belief_data["confidence"],
                status="current",
                rationale="Initial belief seeded during persona creation"
            )
            session.add(stance)

            logger.debug(
                f"Created belief: {belief_data['title']}",
                extra={"belief_id": node.id, "confidence": belief_data["confidence"]}
            )

        await session.flush()

        # Create belief relationships
        belief_map = {node.title: node for node in belief_nodes}
        edges_created = 0

        for edge_data in edges_to_create:
            source_node = belief_map.get(edge_data["source"])
            target_node = belief_map.get(edge_data["target"])

            if source_node and target_node:
                edge = BeliefEdge(
                    persona_id=persona_id,
                    source_id=source_node.id,
                    target_id=target_node.id,
                    relation=edge_data["relation"],
                    weight=edge_data.get("weight", 0.5),
                )
                session.add(edge)
                edges_created += 1

                logger.debug(
                    f"Created belief edge: {edge_data['source']} --[{edge_data['relation']}]--> {edge_data['target']}",
                    extra={
                        "source_id": source_node.id,
                        "target_id": target_node.id,
                        "relation": edge_data["relation"],
                    }
                )

        await session.flush()

        logger.info(
            f"Belief seeding completed for persona {persona_id}",
            extra={
                "persona_id": persona_id,
                "beliefs_created": len(belief_nodes),
                "edges_created": edges_created,
            }
        )

        return (len(belief_nodes), edges_created)
