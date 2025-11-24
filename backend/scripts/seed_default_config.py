"""
Seed default configuration for demo persona.

Creates a default persona with initial configuration settings
for testing and development. Run this after seeding admin user.

Usage:
    python scripts/seed_default_config.py
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.persona import Persona
from app.repositories.config import ConfigRepository


async def seed_default_persona_and_config():
    """
    Seed default persona with initial configuration.

    Creates:
    1. A default persona with reddit_username "DemoAgentBot"
    2. Default configuration:
       - target_subreddits: ["test", "bottest"]
       - auto_posting_enabled: false
       - safety_flags: {"require_approval": true}
       - persona_style: {"directness": 0.7, "formality": 0.5}
    """
    async with async_session_maker() as session:
        # Check if default persona already exists
        stmt = select(Persona).where(
            Persona.reddit_username == "DemoAgentBot"
        )
        result = await session.execute(stmt)
        existing_persona = result.scalar_one_or_none()

        if existing_persona:
            print(f"Default persona already exists: {existing_persona.id}")
            persona_id = existing_persona.id
        else:
            # Create default persona
            persona = Persona(
                reddit_username="DemoAgentBot",
                display_name="Demo AI Agent",
                config="{}"  # Empty initial config
            )
            session.add(persona)
            await session.flush()

            print(f"Created default persona: {persona.id}")
            print(f"  Reddit Username: {persona.reddit_username}")
            print(f"  Display Name: {persona.display_name}")

            persona_id = persona.id

        # Create repository for config operations
        repo = ConfigRepository(session)

        # Check if config already exists
        existing_config = await repo.get_all_config(persona_id)
        if existing_config:
            print("\nConfiguration already exists for this persona:")
            for key, value in existing_config.items():
                print(f"  {key}: {value}")
            print("\nSkipping config seeding.")
        else:
            # Seed default configuration
            config_dict = {
                "target_subreddits": ["test", "bottest"],
                "auto_posting_enabled": False,
                "safety_flags": {
                    "require_approval": True,
                    "content_filter": "strict",
                    "max_comment_length": 500
                },
                "persona_style": {
                    "directness": 0.7,
                    "formality": 0.5,
                    "humor": 0.3,
                    "technical_depth": 0.6
                }
            }

            # Bulk set all config values
            await repo.bulk_set_config(persona_id, config_dict)

            print("\nSeeded default configuration:")
            for key, value in config_dict.items():
                print(f"  {key}: {value}")

        # Commit transaction
        await session.commit()

        print(f"\nDefault persona and configuration seeded successfully!")
        print(f"Persona ID: {persona_id}")
        print(f"Reddit Username: DemoAgentBot")


async def main():
    """Main entry point."""
    print("=" * 60)
    print("Seeding Default Persona and Configuration")
    print("=" * 60)
    print()

    try:
        await seed_default_persona_and_config()
        print()
        print("=" * 60)
        print("Seeding completed successfully!")
        print("=" * 60)
    except Exception as e:
        print(f"\nError seeding default config: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
