"""
Database setup and CRUD operation tests.

Tests database creation, model CRUD operations, relationships,
JSON queries, and foreign key constraints.
"""

import asyncio
import json
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models import (
    Base,
    Persona,
    BeliefNode,
    BeliefEdge,
    StanceVersion,
    EvidenceLink,
    BeliefUpdate,
    Interaction,
    PendingPost,
    AgentConfig,
)


# Test database URL (in-memory for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def async_session():
    """Create a test database session."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Provide session for tests
    async with async_session_maker() as session:
        yield session

    # Cleanup
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_persona(async_session: AsyncSession):
    """Test creating a persona."""
    persona = Persona(
        reddit_username="test_user",
        display_name="Test User",
        config=json.dumps({"target_subreddits": ["test", "bottest"]})
    )

    async_session.add(persona)
    await async_session.commit()

    # Verify persona was created
    result = await async_session.execute(
        select(Persona).where(Persona.reddit_username == "test_user")
    )
    saved_persona = result.scalar_one()

    assert saved_persona.reddit_username == "test_user"
    assert saved_persona.display_name == "Test User"
    assert saved_persona.id is not None
    assert saved_persona.created_at is not None
    assert saved_persona.updated_at is not None

    # Test config JSON parsing
    config = saved_persona.get_config()
    assert config["target_subreddits"] == ["test", "bottest"]


@pytest.mark.asyncio
async def test_create_belief_node(async_session: AsyncSession):
    """Test creating a belief node with tags."""
    # Create persona first
    persona = Persona(
        reddit_username="test_user",
        display_name="Test User",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()

    # Create belief node
    belief = BeliefNode(
        persona_id=persona.id,
        title="Climate Change",
        summary="Climate change is a significant global issue",
        current_confidence=0.85,
        tags=json.dumps(["climate", "environment", "science"])
    )

    async_session.add(belief)
    await async_session.commit()

    # Verify belief was created
    result = await async_session.execute(
        select(BeliefNode).where(BeliefNode.title == "Climate Change")
    )
    saved_belief = result.scalar_one()

    assert saved_belief.title == "Climate Change"
    assert saved_belief.current_confidence == 0.85
    assert saved_belief.persona_id == persona.id

    # Test tags JSON parsing
    tags = saved_belief.get_tags()
    assert "climate" in tags
    assert "science" in tags


@pytest.mark.asyncio
async def test_create_belief_edge(async_session: AsyncSession):
    """Test creating belief edges (relationships)."""
    # Create persona
    persona = Persona(
        reddit_username="test_user",
        display_name="Test User",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()

    # Create two belief nodes
    belief1 = BeliefNode(
        persona_id=persona.id,
        title="Climate Change is Real",
        summary="Climate change is supported by scientific evidence",
        current_confidence=0.9,
    )
    belief2 = BeliefNode(
        persona_id=persona.id,
        title="Reduce Carbon Emissions",
        summary="We should reduce carbon emissions",
        current_confidence=0.85,
    )

    async_session.add_all([belief1, belief2])
    await async_session.commit()

    # Create edge: belief2 depends on belief1
    edge = BeliefEdge(
        persona_id=persona.id,
        source_id=belief2.id,
        target_id=belief1.id,
        relation="depends_on",
        weight=0.8
    )

    async_session.add(edge)
    await async_session.commit()

    # Verify edge was created
    result = await async_session.execute(
        select(BeliefEdge).where(BeliefEdge.relation == "depends_on")
    )
    saved_edge = result.scalar_one()

    assert saved_edge.source_id == belief2.id
    assert saved_edge.target_id == belief1.id
    assert saved_edge.weight == 0.8


@pytest.mark.asyncio
async def test_create_interaction(async_session: AsyncSession):
    """Test creating an interaction (episodic memory)."""
    # Create persona
    persona = Persona(
        reddit_username="test_user",
        display_name="Test User",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()

    # Create interaction
    interaction = Interaction(
        persona_id=persona.id,
        content="This is a test comment about climate change",
        interaction_type="comment",
        reddit_id="t1_abc123",
        subreddit="test",
        parent_id="t3_xyz789",
    )

    # Set metadata
    interaction.set_metadata({
        "score": 10,
        "author": "test_user",
        "timestamp": "2025-01-15T10:30:00"
    })

    async_session.add(interaction)
    await async_session.commit()

    # Verify interaction was created
    result = await async_session.execute(
        select(Interaction).where(Interaction.reddit_id == "t1_abc123")
    )
    saved_interaction = result.scalar_one()

    assert saved_interaction.content == "This is a test comment about climate change"
    assert saved_interaction.interaction_type == "comment"
    assert saved_interaction.subreddit == "test"

    # Test metadata JSON parsing
    metadata = saved_interaction.get_metadata()
    assert metadata["score"] == 10
    assert metadata["author"] == "test_user"


@pytest.mark.asyncio
async def test_create_pending_post(async_session: AsyncSession):
    """Test creating a pending post (moderation queue)."""
    # Create persona
    persona = Persona(
        reddit_username="test_user",
        display_name="Test User",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()

    # Create pending post
    pending_post = PendingPost(
        persona_id=persona.id,
        content="This is a draft comment",
        post_type="comment",
        target_subreddit="test",
        status="pending"
    )

    # Set draft metadata
    pending_post.set_draft_metadata({
        "context": "Responding to post about climate",
        "confidence": 0.75
    })

    async_session.add(pending_post)
    await async_session.commit()

    # Verify pending post was created
    result = await async_session.execute(
        select(PendingPost).where(PendingPost.status == "pending")
    )
    saved_post = result.scalar_one()

    assert saved_post.content == "This is a draft comment"
    assert saved_post.status == "pending"
    assert saved_post.reviewed_by is None

    # Test approval
    saved_post.approve("admin")
    await async_session.commit()

    assert saved_post.status == "approved"
    assert saved_post.reviewed_by == "admin"
    assert saved_post.reviewed_at is not None


@pytest.mark.asyncio
async def test_foreign_key_cascade(async_session: AsyncSession):
    """Test foreign key cascade deletion."""
    # Create persona with belief
    persona = Persona(
        reddit_username="test_user",
        display_name="Test User",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()

    belief = BeliefNode(
        persona_id=persona.id,
        title="Test Belief",
        summary="Test",
        current_confidence=0.5,
    )
    async_session.add(belief)
    await async_session.commit()

    # Delete persona
    await async_session.delete(persona)
    await async_session.commit()

    # Verify belief was cascaded
    result = await async_session.execute(
        select(BeliefNode).where(BeliefNode.id == belief.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_belief_update_audit_log(async_session: AsyncSession):
    """Test belief update audit logging."""
    # Create persona and belief
    persona = Persona(
        reddit_username="test_user",
        display_name="Test User",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()

    belief = BeliefNode(
        persona_id=persona.id,
        title="Test Belief",
        summary="Original summary",
        current_confidence=0.5,
    )
    async_session.add(belief)
    await async_session.commit()

    # Create belief update audit entry
    update = BeliefUpdate(
        persona_id=persona.id,
        belief_id=belief.id,
        reason="New evidence found",
        trigger_type="evidence",
        updated_by="system"
    )

    update.set_old_value({"confidence": 0.5, "summary": "Original summary"})
    update.set_new_value({"confidence": 0.75, "summary": "Updated summary"})

    async_session.add(update)
    await async_session.commit()

    # Verify audit log
    result = await async_session.execute(
        select(BeliefUpdate).where(BeliefUpdate.belief_id == belief.id)
    )
    saved_update = result.scalar_one()

    assert saved_update.reason == "New evidence found"
    assert saved_update.trigger_type == "evidence"
    assert saved_update.get_old_value()["confidence"] == 0.5
    assert saved_update.get_new_value()["confidence"] == 0.75


@pytest.mark.asyncio
async def test_agent_config_key_value(async_session: AsyncSession):
    """Test agent configuration key-value storage."""
    # Create persona
    persona = Persona(
        reddit_username="test_user",
        display_name="Test User",
        config="{}"
    )
    async_session.add(persona)
    await async_session.commit()

    # Create config entries
    config1 = AgentConfig(
        persona_id=persona.id,
        config_key="auto_posting_enabled",
    )
    config1.set_value(False)

    config2 = AgentConfig(
        persona_id=persona.id,
        config_key="response_style",
    )
    config2.set_value({"tone": "friendly", "formality": "casual"})

    async_session.add_all([config1, config2])
    await async_session.commit()

    # Verify config entries
    result = await async_session.execute(
        select(AgentConfig).where(AgentConfig.persona_id == persona.id)
    )
    configs = result.scalars().all()

    assert len(configs) == 2

    # Test value retrieval
    for config in configs:
        if config.config_key == "auto_posting_enabled":
            assert config.get_value() is False
        elif config.config_key == "response_style":
            value = config.get_value()
            assert value["tone"] == "friendly"


if __name__ == "__main__":
    # Run tests directly
    async def main():
        print("Running database tests...")

        # Create async session for manual testing
        engine = create_async_engine(TEST_DATABASE_URL, echo=True)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session_maker() as session:
            print("\n✓ Test 1: Creating persona...")
            await test_create_persona(session)

            print("\n✓ Test 2: Creating belief node...")
            await test_create_belief_node(session)

            print("\n✓ Test 3: Creating belief edge...")
            await test_create_belief_edge(session)

            print("\n✓ Test 4: Creating interaction...")
            await test_create_interaction(session)

            print("\n✓ Test 5: Creating pending post...")
            await test_create_pending_post(session)

            print("\n✓ Test 6: Foreign key cascade...")
            await test_foreign_key_cascade(session)

            print("\n✓ Test 7: Belief update audit log...")
            await test_belief_update_audit_log(session)

            print("\n✓ Test 8: Agent config key-value...")
            await test_agent_config_key_value(session)

        await engine.dispose()
        print("\n✅ All database tests passed!")

    asyncio.run(main())
