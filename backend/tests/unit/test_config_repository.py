"""
Unit tests for ConfigRepository.

Tests CRUD operations with in-memory database following AAA pattern.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
import json

from app.models.base import Base
from app.models.persona import Persona
from app.models.agent_config import AgentConfig
from app.repositories.config import ConfigRepository


@pytest.fixture
async def async_session():
    """
    Create an in-memory SQLite database session for testing.

    Yields:
        AsyncSession for testing
    """
    # Create in-memory async engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    # Cleanup
    await engine.dispose()


@pytest.fixture
async def test_persona(async_session: AsyncSession):
    """
    Create a test persona.

    Args:
        async_session: Database session fixture

    Returns:
        Persona instance
    """
    persona = Persona(
        reddit_username="TestBot",
        display_name="Test Agent",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()
    await async_session.refresh(persona)
    return persona


@pytest.fixture
async def repo(async_session: AsyncSession):
    """
    Create ConfigRepository instance.

    Args:
        async_session: Database session fixture

    Returns:
        ConfigRepository instance
    """
    return ConfigRepository(async_session)


class TestGetConfig:
    """Test suite for get_config method."""

    async def test_get_existing_config(self, repo, test_persona, async_session):
        """
        Test retrieving an existing configuration value.

        Arrange: Create a config entry
        Act: Retrieve it using get_config
        Assert: Correct value is returned
        """
        # Arrange
        config = AgentConfig(
            persona_id=test_persona.id,
            config_key="test_key",
            config_value=json.dumps({"value": "test"})
        )
        async_session.add(config)
        await async_session.commit()

        # Act
        result = await repo.get_config(test_persona.id, "test_key")

        # Assert
        assert result is not None
        assert result["key"] == "test_key"
        assert result["value"] == {"value": "test"}
        assert "updated_at" in result

    async def test_get_nonexistent_config(self, repo, test_persona):
        """
        Test retrieving a non-existent configuration.

        Arrange: No config exists
        Act: Try to retrieve it
        Assert: None is returned
        """
        # Act
        result = await repo.get_config(test_persona.id, "nonexistent")

        # Assert
        assert result is None

    async def test_get_config_json_parse_error(self, repo, test_persona, async_session):
        """
        Test handling of invalid JSON in config value.

        Arrange: Create config with invalid JSON
        Act: Retrieve it
        Assert: Returns raw string value
        """
        # Arrange
        config = AgentConfig(
            persona_id=test_persona.id,
            config_key="bad_json",
            config_value="not valid json {[}"
        )
        async_session.add(config)
        await async_session.commit()

        # Act
        result = await repo.get_config(test_persona.id, "bad_json")

        # Assert
        assert result is not None
        assert result["value"] == "not valid json {[}"


class TestGetAllConfig:
    """Test suite for get_all_config method."""

    async def test_get_all_config_empty(self, repo, test_persona):
        """
        Test retrieving config when none exists.

        Arrange: No config entries
        Act: Retrieve all config
        Assert: Empty dict is returned
        """
        # Act
        result = await repo.get_all_config(test_persona.id)

        # Assert
        assert result == {}

    async def test_get_all_config_multiple(self, repo, test_persona, async_session):
        """
        Test retrieving multiple config entries.

        Arrange: Create multiple config entries
        Act: Retrieve all config
        Assert: All entries are returned correctly
        """
        # Arrange
        configs = [
            AgentConfig(
                persona_id=test_persona.id,
                config_key="key1",
                config_value=json.dumps("value1")
            ),
            AgentConfig(
                persona_id=test_persona.id,
                config_key="key2",
                config_value=json.dumps(["list", "value"])
            ),
            AgentConfig(
                persona_id=test_persona.id,
                config_key="key3",
                config_value=json.dumps({"nested": "dict"})
            ),
        ]
        for config in configs:
            async_session.add(config)
        await async_session.commit()

        # Act
        result = await repo.get_all_config(test_persona.id)

        # Assert
        assert len(result) == 3
        assert result["key1"] == "value1"
        assert result["key2"] == ["list", "value"]
        assert result["key3"] == {"nested": "dict"}

    async def test_get_all_config_persona_isolation(self, repo, async_session):
        """
        Test that get_all_config respects persona isolation.

        Arrange: Create two personas with different configs
        Act: Retrieve config for one persona
        Assert: Only that persona's config is returned
        """
        # Arrange
        persona1 = Persona(reddit_username="Bot1", display_name="Bot 1", config="{}")
        persona2 = Persona(reddit_username="Bot2", display_name="Bot 2", config="{}")
        async_session.add_all([persona1, persona2])
        await async_session.commit()

        config1 = AgentConfig(
            persona_id=persona1.id,
            config_key="key1",
            config_value=json.dumps("persona1_value")
        )
        config2 = AgentConfig(
            persona_id=persona2.id,
            config_key="key1",
            config_value=json.dumps("persona2_value")
        )
        async_session.add_all([config1, config2])
        await async_session.commit()

        # Act
        result1 = await repo.get_all_config(persona1.id)
        result2 = await repo.get_all_config(persona2.id)

        # Assert
        assert result1["key1"] == "persona1_value"
        assert result2["key1"] == "persona2_value"


class TestSetConfig:
    """Test suite for set_config method."""

    async def test_set_config_new(self, repo, test_persona):
        """
        Test creating a new config entry.

        Arrange: No existing config
        Act: Set a config value
        Assert: Config is created successfully
        """
        # Act
        result = await repo.set_config(
            persona_id=test_persona.id,
            key="new_key",
            value={"test": "value"}
        )

        # Assert
        assert result["key"] == "new_key"
        assert result["value"] == {"test": "value"}
        assert result["updated"] is True

        # Verify it was persisted
        retrieved = await repo.get_config(test_persona.id, "new_key")
        assert retrieved["value"] == {"test": "value"}

    async def test_set_config_update_existing(self, repo, test_persona, async_session):
        """
        Test updating an existing config entry.

        Arrange: Create existing config
        Act: Update it with new value
        Assert: Value is updated correctly
        """
        # Arrange
        config = AgentConfig(
            persona_id=test_persona.id,
            config_key="update_key",
            config_value=json.dumps("old_value")
        )
        async_session.add(config)
        await async_session.commit()

        # Act
        result = await repo.set_config(
            persona_id=test_persona.id,
            key="update_key",
            value="new_value"
        )

        # Assert
        assert result["key"] == "update_key"
        assert result["value"] == "new_value"
        assert result["updated"] is True

    async def test_set_config_various_types(self, repo, test_persona):
        """
        Test setting config with various JSON-serializable types.

        Arrange: Various value types
        Act: Set each type
        Assert: All are serialized and deserialized correctly
        """
        # Test data
        test_cases = [
            ("string_key", "string_value"),
            ("int_key", 42),
            ("float_key", 3.14),
            ("bool_key", True),
            ("list_key", [1, 2, 3]),
            ("dict_key", {"nested": {"deep": "value"}}),
            ("null_key", None),
        ]

        # Act & Assert
        for key, value in test_cases:
            result = await repo.set_config(test_persona.id, key, value)
            assert result["value"] == value

            # Verify retrieval
            retrieved = await repo.get_config(test_persona.id, key)
            assert retrieved["value"] == value

    async def test_set_config_invalid_persona(self, repo, async_session):
        """
        Test setting config for non-existent persona.

        Arrange: Invalid persona_id
        Act: Try to set config
        Assert: Operation completes (FK validation happens in endpoint via persona_exists)
        """
        # Note: SQLite may not enforce FK constraints in test environment
        # In production, persona_exists check in endpoint prevents this scenario

        # Act - this should complete without error at repository level
        result = await repo.set_config(
            persona_id="nonexistent-id",
            key="test_key",
            value="test_value"
        )

        # Assert - repository doesn't validate FK, that's endpoint's job
        assert result["key"] == "test_key"
        assert result["value"] == "test_value"

    async def test_set_config_not_json_serializable(self, repo, test_persona):
        """
        Test setting config with non-JSON-serializable value.

        Arrange: Non-serializable value (e.g., function)
        Act: Try to set config
        Assert: TypeError is raised
        """
        # Act & Assert
        with pytest.raises(TypeError):
            await repo.set_config(
                persona_id=test_persona.id,
                key="bad_key",
                value=lambda x: x  # Function is not JSON-serializable
            )


class TestDeleteConfig:
    """Test suite for delete_config method."""

    async def test_delete_existing_config(self, repo, test_persona, async_session):
        """
        Test deleting an existing config entry.

        Arrange: Create a config entry
        Act: Delete it
        Assert: Entry is removed successfully
        """
        # Arrange
        config = AgentConfig(
            persona_id=test_persona.id,
            config_key="delete_key",
            config_value=json.dumps("value")
        )
        async_session.add(config)
        await async_session.commit()

        # Act
        result = await repo.delete_config(test_persona.id, "delete_key")

        # Assert
        assert result is True

        # Verify it's gone
        retrieved = await repo.get_config(test_persona.id, "delete_key")
        assert retrieved is None

    async def test_delete_nonexistent_config(self, repo, test_persona):
        """
        Test deleting a non-existent config entry.

        Arrange: No config exists
        Act: Try to delete it
        Assert: False is returned
        """
        # Act
        result = await repo.delete_config(test_persona.id, "nonexistent")

        # Assert
        assert result is False


class TestPersonaExists:
    """Test suite for persona_exists method."""

    async def test_persona_exists_true(self, repo, test_persona):
        """
        Test checking for existing persona.

        Arrange: Persona exists
        Act: Check if it exists
        Assert: True is returned
        """
        # Act
        result = await repo.persona_exists(test_persona.id)

        # Assert
        assert result is True

    async def test_persona_exists_false(self, repo):
        """
        Test checking for non-existent persona.

        Arrange: Persona doesn't exist
        Act: Check if it exists
        Assert: False is returned
        """
        # Act
        result = await repo.persona_exists("nonexistent-id")

        # Assert
        assert result is False


class TestBulkSetConfig:
    """Test suite for bulk_set_config method."""

    async def test_bulk_set_config(self, repo, test_persona):
        """
        Test setting multiple config values at once.

        Arrange: Multiple key-value pairs
        Act: Bulk set them
        Assert: All are set correctly
        """
        # Arrange
        config_dict = {
            "key1": "value1",
            "key2": [1, 2, 3],
            "key3": {"nested": "dict"},
        }

        # Act
        result = await repo.bulk_set_config(test_persona.id, config_dict)

        # Assert
        assert len(result) == 3
        assert result["key1"] == "value1"
        assert result["key2"] == [1, 2, 3]
        assert result["key3"] == {"nested": "dict"}

        # Verify retrieval
        retrieved = await repo.get_all_config(test_persona.id)
        assert retrieved == config_dict

    async def test_bulk_set_config_empty(self, repo, test_persona):
        """
        Test bulk setting with empty dict.

        Arrange: Empty config dict
        Act: Bulk set
        Assert: No error, empty result
        """
        # Act
        result = await repo.bulk_set_config(test_persona.id, {})

        # Assert
        assert result == {}
