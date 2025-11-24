"""
Unit tests for PersonaRepository.

Tests CRUD operations with AAA pattern (Arrange, Act, Assert).
Follows 0_dev.md quality standards: >80% coverage, isolation, contract testing.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.persona import PersonaRepository


class TestPersonaRepository:
    """
    Test suite for PersonaRepository.

    Tests persona creation, retrieval, and validation.
    Each test follows AAA pattern: Arrange, Act, Assert.
    """

    @pytest.mark.anyio
    async def test_create_persona_success(self, async_session: AsyncSession):
        """
        Test successful persona creation with all fields.

        Arrange: Initialize repository and prepare test data
        Act: Create persona with full config
        Assert: Persona created with correct fields and generated ID
        """
        # Arrange
        repo = PersonaRepository(async_session)
        test_config = {
            "tone": "friendly",
            "style": "concise",
            "core_values": ["honesty", "evidence-based reasoning"],
            "target_subreddits": ["test"]
        }

        # Act
        persona = await repo.create_persona(
            reddit_username="TestBot1",
            display_name="Test Agent",
            config=test_config
        )

        # Assert
        assert persona.id is not None
        assert persona.reddit_username == "TestBot1"
        assert persona.display_name == "Test Agent"
        assert persona.created_at is not None
        assert persona.updated_at is not None

        # Verify config serialization
        stored_config = persona.get_config()
        assert stored_config == test_config

    @pytest.mark.anyio
    async def test_create_persona_minimal(self, async_session: AsyncSession):
        """
        Test persona creation with minimal required fields.

        Arrange: Initialize repository
        Act: Create persona with only username (no display_name or config)
        Assert: Persona created with defaults
        """
        # Arrange
        repo = PersonaRepository(async_session)

        # Act
        persona = await repo.create_persona(
            reddit_username="MinimalBot"
        )

        # Assert
        assert persona.id is not None
        assert persona.reddit_username == "MinimalBot"
        assert persona.display_name is None
        assert persona.created_at is not None

        # Config should be empty dict
        stored_config = persona.get_config()
        assert stored_config == {}

    @pytest.mark.anyio
    async def test_create_persona_duplicate_username(
        self,
        async_session: AsyncSession
    ):
        """
        Test persona creation fails with duplicate username.

        Arrange: Create first persona
        Act: Attempt to create second persona with same username
        Assert: Raises ValueError with appropriate message
        """
        # Arrange
        repo = PersonaRepository(async_session)
        await repo.create_persona(reddit_username="DuplicateBot")

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await repo.create_persona(reddit_username="DuplicateBot")

        assert "already exists" in str(exc_info.value)
        assert "DuplicateBot" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_username_exists_true(self, async_session: AsyncSession):
        """
        Test username_exists returns True for existing username.

        Arrange: Create persona
        Act: Check if username exists
        Assert: Returns True
        """
        # Arrange
        repo = PersonaRepository(async_session)
        await repo.create_persona(reddit_username="ExistingBot")

        # Act
        exists = await repo.username_exists("ExistingBot")

        # Assert
        assert exists is True

    @pytest.mark.anyio
    async def test_username_exists_false(self, async_session: AsyncSession):
        """
        Test username_exists returns False for non-existent username.

        Arrange: Initialize repository (no personas)
        Act: Check if username exists
        Assert: Returns False
        """
        # Arrange
        repo = PersonaRepository(async_session)

        # Act
        exists = await repo.username_exists("NonExistentBot")

        # Assert
        assert exists is False

    @pytest.mark.anyio
    async def test_get_persona_success(self, async_session: AsyncSession):
        """
        Test successful persona retrieval by ID.

        Arrange: Create persona
        Act: Retrieve persona by ID
        Assert: Returns correct persona
        """
        # Arrange
        repo = PersonaRepository(async_session)
        created = await repo.create_persona(reddit_username="GetBot")

        # Act
        retrieved = await repo.get_persona(created.id)

        # Assert
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.reddit_username == "GetBot"

    @pytest.mark.anyio
    async def test_get_persona_not_found(self, async_session: AsyncSession):
        """
        Test get_persona returns None for non-existent ID.

        Arrange: Initialize repository (no personas)
        Act: Attempt to retrieve persona with fake ID
        Assert: Returns None
        """
        # Arrange
        repo = PersonaRepository(async_session)
        fake_id = "00000000-0000-0000-0000-000000000000"

        # Act
        retrieved = await repo.get_persona(fake_id)

        # Assert
        assert retrieved is None

    @pytest.mark.anyio
    async def test_get_all_personas_empty(self, async_session: AsyncSession):
        """
        Test get_all_personas returns empty list when no personas exist.

        Arrange: Initialize repository (no personas)
        Act: Get all personas
        Assert: Returns empty list
        """
        # Arrange
        repo = PersonaRepository(async_session)

        # Act
        personas = await repo.get_all_personas()

        # Assert
        assert personas == []

    @pytest.mark.anyio
    async def test_get_all_personas_multiple(self, async_session: AsyncSession):
        """
        Test get_all_personas returns all created personas.

        Arrange: Create multiple personas
        Act: Get all personas
        Assert: Returns all personas in list
        """
        # Arrange
        repo = PersonaRepository(async_session)
        persona1 = await repo.create_persona(reddit_username="Bot1")
        persona2 = await repo.create_persona(reddit_username="Bot2")
        persona3 = await repo.create_persona(reddit_username="Bot3")

        # Act
        personas = await repo.get_all_personas()

        # Assert
        assert len(personas) == 3
        persona_ids = {p.id for p in personas}
        assert {persona1.id, persona2.id, persona3.id} == persona_ids

    @pytest.mark.anyio
    async def test_config_serialization_complex(
        self,
        async_session: AsyncSession
    ):
        """
        Test complex config structure is correctly serialized and deserialized.

        Arrange: Prepare complex config with nested structures
        Act: Create persona and retrieve config
        Assert: Config matches original structure
        """
        # Arrange
        repo = PersonaRepository(async_session)
        complex_config = {
            "tone": "analytical",
            "style": "detailed",
            "core_values": ["accuracy", "clarity", "depth"],
            "target_subreddits": ["science", "technology", "programming"],
            "nested_object": {
                "key1": "value1",
                "key2": ["list", "of", "items"],
                "key3": {"deep": "nesting"}
            }
        }

        # Act
        persona = await repo.create_persona(
            reddit_username="ComplexBot",
            config=complex_config
        )
        retrieved_config = persona.get_config()

        # Assert
        assert retrieved_config == complex_config
        assert isinstance(retrieved_config["nested_object"], dict)
        assert isinstance(retrieved_config["core_values"], list)

    @pytest.mark.anyio
    async def test_persona_isolation(self, async_session: AsyncSession):
        """
        Test that personas are isolated from each other.

        Arrange: Create two personas with different configs
        Act: Retrieve both personas
        Assert: Each has its own config, no cross-contamination
        """
        # Arrange
        repo = PersonaRepository(async_session)
        config1 = {"tone": "formal"}
        config2 = {"tone": "casual"}

        persona1 = await repo.create_persona(
            reddit_username="FormalBot",
            config=config1
        )
        persona2 = await repo.create_persona(
            reddit_username="CasualBot",
            config=config2
        )

        # Act
        retrieved1 = await repo.get_persona(persona1.id)
        retrieved2 = await repo.get_persona(persona2.id)

        # Assert
        assert retrieved1.get_config() == config1
        assert retrieved2.get_config() == config2
        assert retrieved1.get_config() != retrieved2.get_config()
