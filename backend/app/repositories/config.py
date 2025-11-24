"""
Configuration repository for agent config CRUD operations.

Provides data access layer for AgentConfig model with persona isolation
and JSON value handling.
"""

from typing import Optional, Dict, Any, List
import json

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.agent_config import AgentConfig
from app.models.persona import Persona


class ConfigRepository:
    """
    Repository for agent configuration data access.

    Provides async CRUD operations for per-persona configuration storage.
    All operations are persona-scoped to ensure data isolation.

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

    async def get_config(
        self,
        persona_id: str,
        key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single configuration value by persona and key.

        Args:
            persona_id: UUID of the persona
            key: Configuration key name

        Returns:
            Dictionary with the parsed config value, or None if not found

        Example:
            >>> config = await repo.get_config(
            ...     persona_id="123e4567-e89b-12d3-a456-426614174000",
            ...     key="target_subreddits"
            ... )
            >>> print(config)
            {"key": "target_subreddits", "value": ["test", "bottest"]}

        Note:
            Returns None if persona or key doesn't exist.
            JSON parsing errors are handled gracefully.
        """
        stmt = select(AgentConfig).where(
            AgentConfig.persona_id == persona_id,
            AgentConfig.config_key == key
        )

        result = await self.session.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None:
            return None

        # Parse JSON value
        try:
            value = json.loads(config.config_value)
        except json.JSONDecodeError:
            # If not valid JSON, return as-is
            value = config.config_value

        return {
            "key": config.config_key,
            "value": value,
            "updated_at": config.updated_at
        }

    async def get_all_config(
        self,
        persona_id: str
    ) -> Dict[str, Any]:
        """
        Retrieve all configuration key-value pairs for a persona.

        Args:
            persona_id: UUID of the persona

        Returns:
            Dictionary mapping config keys to their values

        Example:
            >>> config = await repo.get_all_config(
            ...     persona_id="123e4567-e89b-12d3-a456-426614174000"
            ... )
            >>> print(config)
            {
                "target_subreddits": ["test", "bottest"],
                "auto_posting_enabled": False,
                "safety_flags": {"require_approval": True}
            }

        Note:
            Returns empty dict if persona has no configuration.
            Persona existence is not validated (returns empty dict for non-existent persona).
        """
        stmt = select(AgentConfig).where(
            AgentConfig.persona_id == persona_id
        )

        result = await self.session.execute(stmt)
        configs = result.scalars().all()

        # Build dictionary from all config entries
        config_dict = {}
        for config in configs:
            try:
                value = json.loads(config.config_value)
            except json.JSONDecodeError:
                value = config.config_value

            config_dict[config.config_key] = value

        return config_dict

    async def set_config(
        self,
        persona_id: str,
        key: str,
        value: Any
    ) -> Dict[str, Any]:
        """
        Set or update a configuration value.

        Creates a new config entry or updates existing one (upsert).
        Automatically serializes value to JSON.

        Args:
            persona_id: UUID of the persona
            key: Configuration key name
            value: Configuration value (JSON-serializable)

        Returns:
            Dictionary with the updated config

        Raises:
            IntegrityError: If persona_id doesn't exist (foreign key constraint)
            TypeError: If value is not JSON-serializable

        Example:
            >>> config = await repo.set_config(
            ...     persona_id="123e4567-e89b-12d3-a456-426614174000",
            ...     key="auto_posting_enabled",
            ...     value=True
            ... )
            >>> print(config)
            {
                "key": "auto_posting_enabled",
                "value": True,
                "updated": True
            }

        Note:
            Uses database-level unique constraint (persona_id, config_key)
            to prevent duplicates. On conflict, updates the existing row.
        """
        # Serialize value to JSON
        try:
            if isinstance(value, str):
                # Check if already JSON
                try:
                    json.loads(value)
                    json_value = value
                except json.JSONDecodeError:
                    # Not JSON, so serialize it
                    json_value = json.dumps(value)
            else:
                json_value = json.dumps(value)
        except (TypeError, ValueError) as e:
            raise TypeError(f"Value is not JSON-serializable: {e}")

        # Check if config already exists
        stmt = select(AgentConfig).where(
            AgentConfig.persona_id == persona_id,
            AgentConfig.config_key == key
        )

        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing config
            existing.config_value = json_value
            # Don't set updated_at to None - let the onupdate handler work
            await self.session.flush()
            config = existing
        else:
            # Create new config
            config = AgentConfig(
                persona_id=persona_id,
                config_key=key,
                config_value=json_value
            )
            self.session.add(config)
            await self.session.flush()

        # Parse back to return
        try:
            parsed_value = json.loads(config.config_value)
        except json.JSONDecodeError:
            parsed_value = config.config_value

        return {
            "key": config.config_key,
            "value": parsed_value,
            "updated": True,
            "updated_at": config.updated_at
        }

    async def delete_config(
        self,
        persona_id: str,
        key: str
    ) -> bool:
        """
        Delete a configuration entry.

        Args:
            persona_id: UUID of the persona
            key: Configuration key name

        Returns:
            True if config was deleted, False if not found

        Example:
            >>> deleted = await repo.delete_config(
            ...     persona_id="123e4567-e89b-12d3-a456-426614174000",
            ...     key="deprecated_setting"
            ... )
            >>> print(deleted)
            True

        Note:
            Deletion is persona-scoped. Will not delete configs from other personas.
        """
        stmt = delete(AgentConfig).where(
            AgentConfig.persona_id == persona_id,
            AgentConfig.config_key == key
        )

        result = await self.session.execute(stmt)
        await self.session.flush()

        return result.rowcount > 0

    async def persona_exists(self, persona_id: str) -> bool:
        """
        Check if a persona exists in the database.

        Args:
            persona_id: UUID of the persona

        Returns:
            True if persona exists, False otherwise

        Example:
            >>> exists = await repo.persona_exists(
            ...     persona_id="123e4567-e89b-12d3-a456-426614174000"
            ... )
            >>> print(exists)
            True

        Note:
            This is a helper method for validation before setting config.
            Used to provide better error messages than FK constraint violations.
        """
        stmt = select(Persona).where(Persona.id == persona_id)
        result = await self.session.execute(stmt)
        persona = result.scalar_one_or_none()

        return persona is not None

    async def get_all_personas(self) -> List[Dict[str, Any]]:
        """
        Get all personas with their basic information.

        Returns:
            List of persona dictionaries with id, reddit_username, display_name

        Example:
            >>> personas = await repo.get_all_personas()
            >>> print(personas)
            [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "reddit_username": "AgentBot1",
                    "display_name": "Demo Agent"
                }
            ]

        Note:
            Used for persona selection and validation in the dashboard.
        """
        stmt = select(Persona)
        result = await self.session.execute(stmt)
        personas = result.scalars().all()

        return [
            {
                "id": persona.id,
                "reddit_username": persona.reddit_username,
                "display_name": persona.display_name
            }
            for persona in personas
        ]

    async def bulk_set_config(
        self,
        persona_id: str,
        config_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Set multiple configuration values at once.

        Efficiently updates multiple config keys in a single transaction.

        Args:
            persona_id: UUID of the persona
            config_dict: Dictionary of key-value pairs to set

        Returns:
            Dictionary with all updated configurations

        Raises:
            IntegrityError: If persona_id doesn't exist
            TypeError: If any value is not JSON-serializable

        Example:
            >>> config = await repo.bulk_set_config(
            ...     persona_id="123e4567-e89b-12d3-a456-426614174000",
            ...     config_dict={
            ...         "target_subreddits": ["test", "bottest"],
            ...         "auto_posting_enabled": False,
            ...         "safety_flags": {"require_approval": True}
            ...     }
            ... )
            >>> print(config)
            {
                "target_subreddits": ["test", "bottest"],
                "auto_posting_enabled": False,
                "safety_flags": {"require_approval": True}
            }

        Note:
            This is more efficient than calling set_config multiple times.
            All updates happen in a single database transaction.
        """
        result_dict = {}

        for key, value in config_dict.items():
            config = await self.set_config(persona_id, key, value)
            result_dict[key] = config["value"]

        return result_dict
