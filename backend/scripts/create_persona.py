"""
Create a new persona interactively.

Usage:
    python scripts/create_persona.py
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


async def create_persona():
    """
    Create a new persona interactively.
    """
    print("=" * 60)
    print("Create New Persona")
    print("=" * 60)
    print()

    # Get persona details from user
    reddit_username = input("Reddit username: ").strip()
    if not reddit_username:
        print("Error: Reddit username is required")
        sys.exit(1)

    display_name = input("Display name (optional, defaults to username): ").strip()
    if not display_name:
        display_name = reddit_username

    # Get persona configuration
    print("\nPersona Configuration (optional):")
    print("Enter tone (default: 'friendly and balanced'): ", end="")
    tone = input().strip() or "friendly and balanced"

    print("Enter style (default: 'conversational'): ", end="")
    style = input().strip() or "conversational"

    print("Enter core values (comma-separated, default: 'honesty, curiosity, respect'): ", end="")
    values_input = input().strip()
    if values_input:
        core_values = [v.strip() for v in values_input.split(",")]
    else:
        core_values = ["honesty", "curiosity", "respect"]

    config = {
        "tone": tone,
        "style": style,
        "core_values": core_values
    }

    # Create persona in database
    async with async_session_maker() as session:
        # Check if username already exists
        stmt = select(Persona).where(Persona.reddit_username == reddit_username)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            print(f"\nError: Persona with username '{reddit_username}' already exists")
            print(f"Existing persona ID: {existing.id}")
            sys.exit(1)

        # Create new persona
        persona = Persona(
            reddit_username=reddit_username,
            display_name=display_name,
            config=json.dumps(config)
        )
        session.add(persona)
        await session.commit()
        await session.refresh(persona)

        print("\n" + "=" * 60)
        print("Persona created successfully!")
        print("=" * 60)
        print(f"Persona ID: {persona.id}")
        print(f"Reddit Username: {persona.reddit_username}")
        print(f"Display Name: {persona.display_name}")
        print(f"Config: {json.dumps(config, indent=2)}")
        print()
        print(f"You can now select this persona in the dashboard.")
        print()


async def main():
    """Main entry point."""
    try:
        await create_persona()
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError creating persona: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
