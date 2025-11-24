"""
Seed demo persona with initial beliefs.

Creates a default persona with 5-10 core beliefs to demonstrate
the belief graph system. This is for development and testing purposes.

Usage:
    python scripts/seed_demo.py
"""

import asyncio
import sys
import os
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.persona import Persona
from app.models.belief import BeliefNode, BeliefEdge, StanceVersion


async def seed_demo_persona_with_beliefs():
    """
    Seed demo persona with initial beliefs.

    Creates:
    1. A demo persona "DemoAgentBot" (if not exists)
    2. 5-10 core beliefs with:
       - Titles and summaries
       - Confidence levels (0-1)
       - Tags for categorization
       - Initial stance versions
       - Relationships between beliefs (edges)
    """
    async with async_session_maker() as session:
        # Check if demo persona already exists
        stmt = select(Persona).where(
            Persona.reddit_username == "DemoAgentBot"
        )
        result = await session.execute(stmt)
        existing_persona = result.scalar_one_or_none()

        if not existing_persona:
            # Create demo persona
            persona = Persona(
                reddit_username="DemoAgentBot",
                display_name="Demo AI Agent",
                config=json.dumps({
                    "tone": "friendly and evidence-driven",
                    "style": "casual but informative",
                    "core_values": ["transparency", "rationality", "kindness"]
                })
            )
            session.add(persona)
            await session.flush()
            print(f"Created demo persona: {persona.id}")
            print(f"  Reddit Username: {persona.reddit_username}")
            print(f"  Display Name: {persona.display_name}")
            persona_id = persona.id
        else:
            persona_id = existing_persona.id
            print(f"Using existing persona: {persona_id}")

        # Check if beliefs already exist for this persona
        stmt = select(BeliefNode).where(BeliefNode.persona_id == persona_id)
        result = await session.execute(stmt)
        existing_beliefs = result.scalars().all()

        if existing_beliefs:
            print(f"\nBeliefs already exist for this persona ({len(existing_beliefs)} beliefs)")
            print("Skipping belief seeding.")
            return

        print("\nSeeding core beliefs...")

        # Define core beliefs
        beliefs_data = [
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

        # Create belief nodes
        belief_nodes = []
        for i, belief_data in enumerate(beliefs_data):
            node = BeliefNode(
                persona_id=persona_id,
                title=belief_data["title"],
                summary=belief_data["summary"],
                current_confidence=belief_data["confidence"],
                tags=json.dumps(belief_data["tags"])
            )
            session.add(node)
            await session.flush()  # Get ID for node
            belief_nodes.append(node)

            # Create initial stance version for each belief
            stance = StanceVersion(
                persona_id=persona_id,
                belief_id=node.id,
                text=belief_data["summary"],
                confidence=belief_data["confidence"],
                status="current",
                rationale="Initial belief seeded during setup"
            )
            session.add(stance)

            print(f"  [{i+1}] {belief_data['title']} (confidence: {belief_data['confidence']})")

        await session.flush()

        # Create relationships between beliefs (edges)
        print("\nCreating belief relationships...")

        # Map titles to nodes for easier reference
        belief_map = {node.title: node for node in belief_nodes}

        # Define relationships
        edges_data = [
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
                "note": "Transparency in AI development aids alignment"
            },
            {
                "source": "Civility in discourse",
                "target": "Skepticism of absolute claims",
                "relation": "supports",
                "weight": 0.7,
            },
        ]

        edge_count = 0
        for edge_data in edges_data:
            source_node = belief_map.get(edge_data["source"])
            target_node = belief_map.get(edge_data["target"])

            if source_node and target_node:
                edge = BeliefEdge(
                    persona_id=persona_id,
                    source_id=source_node.id,
                    target_id=target_node.id,
                    relation=edge_data["relation"],
                    weight=edge_data["weight"]
                )
                session.add(edge)
                edge_count += 1
                print(f"  {edge_data['source']} --[{edge_data['relation']}]--> {edge_data['target']}")

        # Commit all changes
        await session.commit()

        print(f"\nSeeding completed successfully!")
        print(f"  Created {len(belief_nodes)} beliefs")
        print(f"  Created {len(belief_nodes)} initial stances")
        print(f"  Created {edge_count} belief relationships")
        print(f"\nPersona ID: {persona_id}")
        print(f"Reddit Username: DemoAgentBot")


async def main():
    """Main entry point."""
    print("=" * 60)
    print("Seeding Demo Persona with Beliefs")
    print("=" * 60)
    print()

    try:
        await seed_demo_persona_with_beliefs()
        print()
        print("=" * 60)
        print("Demo data seeded successfully!")
        print("=" * 60)
    except Exception as e:
        print(f"\nError seeding demo data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
