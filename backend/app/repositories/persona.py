"""
Persona repository for persona CRUD operations.

Provides data access layer for Persona model with validation
and conflict checking.
"""

from typing import Optional
from datetime import datetime
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.persona import Persona


class PersonaRepository:
    """
    Repository for persona data access.

    Provides async CRUD operations for persona management.
    Handles username uniqueness validation and config serialization.

    Attributes:
        session: SQLAlchemy async session for database operations
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_persona(
        self,
        reddit_username: str,
        display_name: Optional[str] = None,
        config: Optional[dict] = None
    ) -> Persona:
        """
        Create a new persona.

        Args:
            reddit_username: Reddit account username (must be unique)
            display_name: Human-readable display name (optional)
            config: Persona configuration dict (optional, defaults to empty)

        Returns:
            Created Persona instance with all fields populated

        Raises:
            ValueError: If reddit_username already exists
            IntegrityError: If database constraint is violated

        Example:
            >>> persona = await repo.create_persona(
            ...     reddit_username="AgentBot123",
            ...     display_name="Friendly Agent",
            ...     config={"tone": "friendly", "style": "concise"}
            ... )
            >>> print(persona.id)
            "123e4567-e89b-12d3-a456-426614174000"

        Note:
            - Checks for username conflicts before insert
            - Config is serialized to JSON automatically
            - created_at and updated_at are set by database defaults
        """
        # Check for existing username
        if await self.username_exists(reddit_username):
            raise ValueError(
                f"Persona with reddit_username '{reddit_username}' already exists"
            )

        # Prepare config (default to empty dict if None)
        if config is None:
            config = {}

        # Create persona instance
        persona = Persona(
            reddit_username=reddit_username,
            display_name=display_name
        )

        # Set config using model method (handles JSON serialization)
        persona.set_config(config)

        # Add to session and flush to get ID
        self.session.add(persona)
        await self.session.flush()

        # Refresh to get all generated fields (timestamps)
        await self.session.refresh(persona)

        return persona

    async def get_persona(self, persona_id: str) -> Optional[Persona]:
        """
        Retrieve a persona by ID.

        Args:
            persona_id: UUID of the persona

        Returns:
            Persona instance if found, None otherwise

        Example:
            >>> persona = await repo.get_persona(
            ...     "123e4567-e89b-12d3-a456-426614174000"
            ... )
            >>> print(persona.reddit_username if persona else "Not found")
            "AgentBot123"
        """
        stmt = select(Persona).where(Persona.id == persona_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def username_exists(self, reddit_username: str) -> bool:
        """
        Check if a reddit_username already exists.

        Args:
            reddit_username: Reddit account username to check

        Returns:
            True if username exists, False otherwise

        Example:
            >>> exists = await repo.username_exists("AgentBot123")
            >>> print(exists)
            True

        Note:
            Used for validation before creating a new persona to provide
            better error messages than database constraint violations.
        """
        stmt = select(Persona).where(
            Persona.reddit_username == reddit_username
        )
        result = await self.session.execute(stmt)
        persona = result.scalar_one_or_none()
        return persona is not None

    async def get_all_personas(self) -> list[Persona]:
        """
        Get all personas.

        Returns:
            List of all Persona instances

        Example:
            >>> personas = await repo.get_all_personas()
            >>> print(len(personas))
            3

        Note:
            Used for listing available personas in the dashboard.
        """
        stmt = select(Persona)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
