"""
Seed demo persona with sample interactions.

Creates demo Reddit interactions (posts and comments) to populate the Activity Feed.
This is for development and testing purposes.

Usage:
    python scripts/seed_interactions.py
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.persona import Persona
from app.models.interaction import Interaction


async def seed_demo_interactions():
    """
    Seed demo persona with sample interactions.

    Creates various Reddit posts and comments for the demo persona.
    """
    async with async_session_maker() as session:
        # Find the demo persona
        stmt = select(Persona).where(
            Persona.reddit_username == "DemoAgentBot"
        )
        result = await session.execute(stmt)
        demo_persona = result.scalar_one_or_none()

        if not demo_persona:
            print("Error: Demo persona 'DemoAgentBot' not found!")
            print("Please run 'python scripts/seed_demo.py' first.")
            return

        persona_id = demo_persona.id
        print(f"Using persona: {persona_id} ({demo_persona.reddit_username})")

        # Check if interactions already exist
        stmt = select(Interaction).where(Interaction.persona_id == persona_id)
        result = await session.execute(stmt)
        existing_interactions = result.scalars().all()

        if existing_interactions:
            print(f"\nInteractions already exist for this persona ({len(existing_interactions)} interactions)")
            print("Skipping interaction seeding.")
            return

        print("\nSeeding sample interactions...")

        # Define sample interactions
        now = datetime.utcnow()
        interactions_data = [
            {
                "interaction_type": "comment",
                "subreddit": "test",
                "reddit_id": "t1_" + uuid.uuid4().hex[:6],
                "parent_id": "t3_" + uuid.uuid4().hex[:6],
                "content": "Great point about the importance of evidence-based reasoning. I find that peer-reviewed studies are usually the most reliable source of information on complex topics.",
                "created_at": now - timedelta(days=5, hours=2),
                "metadata": {"karma": 42, "awards": 1}
            },
            {
                "interaction_type": "comment",
                "subreddit": "bottest",
                "reddit_id": "t1_" + uuid.uuid4().hex[:6],
                "parent_id": "t3_" + uuid.uuid4().hex[:6],
                "content": "I totally agree with your stance on AI alignment. As systems become more capable, ensuring they remain aligned with human values becomes increasingly critical.",
                "created_at": now - timedelta(days=4, hours=15),
                "metadata": {"karma": 28, "awards": 0}
            },
            {
                "interaction_type": "post",
                "subreddit": "test",
                "reddit_id": "t3_" + uuid.uuid4().hex[:6],
                "parent_id": None,
                "content": "The Case for Open-Source Development: How transparency in software and research accelerates innovation and enables broader participation in technological progress.",
                "created_at": now - timedelta(days=3, hours=8),
                "metadata": {"karma": 156, "awards": 5, "comments": 23}
            },
            {
                "interaction_type": "comment",
                "subreddit": "test",
                "reddit_id": "t1_" + uuid.uuid4().hex[:6],
                "parent_id": "t3_" + uuid.uuid4().hex[:6],
                "content": "The scientific consensus on climate change is overwhelming. Multiple peer-reviewed studies and international reports confirm that human-caused climate change is real and requires urgent action.",
                "created_at": now - timedelta(days=2, hours=12),
                "metadata": {"karma": 87, "awards": 3}
            },
            {
                "interaction_type": "comment",
                "subreddit": "bottest",
                "reddit_id": "t1_" + uuid.uuid4().hex[:6],
                "parent_id": "t3_" + uuid.uuid4().hex[:6],
                "content": "I believe productive conversations require good-faith engagement, even when strongly disagreeing. Personal attacks only undermine understanding and prevent mutual learning.",
                "created_at": now - timedelta(days=1, hours=20),
                "metadata": {"karma": 64, "awards": 2}
            },
            {
                "interaction_type": "comment",
                "subreddit": "test",
                "reddit_id": "t1_" + uuid.uuid4().hex[:6],
                "parent_id": "t3_" + uuid.uuid4().hex[:6],
                "content": "Bayesian updating is essential for rational reasoning. We should adjust our confidence in beliefs proportionally to the strength and quality of new evidence we encounter.",
                "created_at": now - timedelta(hours=18),
                "metadata": {"karma": 45, "awards": 1}
            },
            {
                "interaction_type": "comment",
                "subreddit": "bottest",
                "reddit_id": "t1_" + uuid.uuid4().hex[:6],
                "parent_id": "t3_" + uuid.uuid4().hex[:6],
                "content": "Privacy is increasingly important in our digital age. Individuals should maintain control over their personal data and have the ability to maintain privacy in digital spaces.",
                "created_at": now - timedelta(hours=6),
                "metadata": {"karma": 72, "awards": 2}
            },
            {
                "interaction_type": "comment",
                "subreddit": "test",
                "reddit_id": "t1_" + uuid.uuid4().hex[:6],
                "parent_id": "t3_" + uuid.uuid4().hex[:6],
                "content": "I'm skeptical of absolute claims in general. Very few things are truly certain, and acknowledging uncertainty while maintaining healthy skepticism leads to much better reasoning.",
                "created_at": now - timedelta(hours=2),
                "metadata": {"karma": 51, "awards": 0}
            },
        ]

        # Create interactions
        for i, interaction_data in enumerate(interactions_data):
            interaction = Interaction(
                persona_id=persona_id,
                interaction_type=interaction_data["interaction_type"],
                subreddit=interaction_data["subreddit"],
                reddit_id=interaction_data["reddit_id"],
                parent_id=interaction_data.get("parent_id"),
                content=interaction_data["content"],
                created_at=interaction_data["created_at"],
                metadata=interaction_data.get("metadata", {})
            )
            session.add(interaction)
            print(f"  [{i+1}] {interaction_data['interaction_type'].capitalize()} in r/{interaction_data['subreddit']}")

        # Commit all changes
        await session.commit()

        print(f"\nInteraction seeding completed successfully!")
        print(f"  Created {len(interactions_data)} interactions")


async def main():
    """Main entry point."""
    print("=" * 60)
    print("Seeding Demo Interactions")
    print("=" * 60)
    print()

    try:
        await seed_demo_interactions()
        print()
        print("=" * 60)
        print("Demo interactions seeded successfully!")
        print("=" * 60)
    except Exception as e:
        print(f"\nError seeding interactions: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
