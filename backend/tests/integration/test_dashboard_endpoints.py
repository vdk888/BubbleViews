import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.security import User
from app.api.dependencies import get_current_user
from app.core.database import engine, async_session_maker
from app.models import Base, Persona, Interaction, PendingPost, BeliefNode, StanceVersion


@pytest.fixture(autouse=True)
async def setup_db():
    # create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: User(username="admin", full_name="Admin", disabled=False)
    yield
    app.dependency_overrides.clear()


async def seed_persona():
    async with async_session_maker() as session:
        persona = Persona(reddit_username="tester", display_name="Tester", config="{}")
        session.add(persona)
        await session.commit()
        return persona.id


@pytest.mark.anyio
async def test_personas_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        persona_id = await seed_persona()
        resp = await client.get("/api/v1/personas")
        assert resp.status_code == 200
        data = resp.json()
        assert any(item["id"] == persona_id for item in data)


@pytest.mark.anyio
async def test_activity_endpoint():
    persona_id = await seed_persona()
    async with async_session_maker() as session:
        interaction = Interaction(
            persona_id=persona_id,
            content="hello world",
            interaction_type="comment",
            reddit_id="t1_test",
            subreddit="testsub",
        )
        session.add(interaction)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/activity?persona_id={persona_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body and body[0]["reddit_id"] == "t1_test"


@pytest.mark.anyio
@patch('app.api.v1.moderation.AsyncPRAWClient')
async def test_moderation_pending_and_approve(mock_reddit_client):
    # Mock the Reddit client to avoid actual API calls
    mock_instance = AsyncMock()
    mock_instance.reply = AsyncMock(return_value="t1_mockcomment123")
    mock_instance.close = AsyncMock()
    mock_reddit_client.return_value = mock_instance

    persona_id = await seed_persona()
    async with async_session_maker() as session:
        pending = PendingPost(
            persona_id=persona_id,
            content="draft",
            post_type="comment",
            target_subreddit="testsub",
            parent_id="t3_testpost123",  # Add parent_id for comment type
            status="pending",
        )
        session.add(pending)
        await session.commit()
        pending_id = pending.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pending_resp = await client.get(f"/api/v1/moderation/pending?persona_id={persona_id}")
        assert pending_resp.status_code == 200
        assert len(pending_resp.json()) == 1

        approve_resp = await client.post(
            "/api/v1/moderation/approve",
            json={"item_id": pending_id, "persona_id": persona_id},
            headers={"Authorization": "Bearer dummy"},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"


@pytest.mark.anyio
async def test_belief_graph_and_history():
    persona_id = await seed_persona()
    async with async_session_maker() as session:
        belief = BeliefNode(
            persona_id=persona_id,
            title="Test belief",
            summary="Summary",
            current_confidence=0.8,
            tags="[]",
        )
        session.add(belief)
        await session.flush()
        stance = StanceVersion(
            persona_id=persona_id,
            belief_id=belief.id,
            text="Initial",
            confidence=0.8,
            status="current",
        )
        session.add(stance)
        await session.commit()
        belief_id = belief.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        graph_resp = await client.get(f"/api/v1/beliefs?persona_id={persona_id}")
        assert graph_resp.status_code == 200
        assert graph_resp.json()["nodes"][0]["id"] == belief_id

        hist_resp = await client.get(f"/api/v1/beliefs/{belief_id}/history?persona_id={persona_id}")
        assert hist_resp.status_code == 200
        assert hist_resp.json()["belief"]["id"] == belief_id


@pytest.mark.anyio
async def test_belief_manual_update():
    """Test manual belief update endpoint (PUT /beliefs/{id})."""
    persona_id = await seed_persona()
    async with async_session_maker() as session:
        belief = BeliefNode(
            persona_id=persona_id,
            title="Test belief",
            summary="Summary",
            current_confidence=0.6,
            tags="[]",
        )
        session.add(belief)
        await session.flush()
        stance = StanceVersion(
            persona_id=persona_id,
            belief_id=belief.id,
            text="Initial stance",
            confidence=0.6,
            status="current",
        )
        session.add(stance)
        await session.commit()
        belief_id = belief.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Update belief confidence
        update_resp = await client.put(
            f"/api/v1/beliefs/{belief_id}",
            json={
                "persona_id": persona_id,
                "confidence": 0.85,
                "rationale": "Manual update from admin"
            }
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["belief_id"] == belief_id
        assert data["old_confidence"] == 0.6
        assert data["new_confidence"] == 0.85
        assert data["status"] == "updated"


@pytest.mark.anyio
async def test_belief_lock_unlock():
    """Test belief lock/unlock endpoints."""
    persona_id = await seed_persona()
    async with async_session_maker() as session:
        belief = BeliefNode(
            persona_id=persona_id,
            title="Test belief",
            summary="Summary",
            current_confidence=0.7,
            tags="[]",
        )
        session.add(belief)
        await session.flush()
        stance = StanceVersion(
            persona_id=persona_id,
            belief_id=belief.id,
            text="Initial stance",
            confidence=0.7,
            status="current",
        )
        session.add(stance)
        await session.commit()
        belief_id = belief.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Lock the belief
        lock_resp = await client.post(
            f"/api/v1/beliefs/{belief_id}/lock",
            json={
                "persona_id": persona_id,
                "reason": "Locking for testing"
            }
        )
        assert lock_resp.status_code == 200
        assert lock_resp.json()["status"] == "locked"

        # Verify stance is locked by trying to update (should fail)
        update_resp = await client.put(
            f"/api/v1/beliefs/{belief_id}",
            json={
                "persona_id": persona_id,
                "confidence": 0.9,
                "rationale": "Should fail"
            }
        )
        assert update_resp.status_code == 403  # Permission error

        # Unlock the belief
        unlock_resp = await client.post(
            f"/api/v1/beliefs/{belief_id}/unlock",
            json={
                "persona_id": persona_id,
                "reason": "Unlocking for testing"
            }
        )
        assert unlock_resp.status_code == 200
        assert unlock_resp.json()["status"] == "unlocked"

        # Now update should work
        update_resp = await client.put(
            f"/api/v1/beliefs/{belief_id}",
            json={
                "persona_id": persona_id,
                "confidence": 0.9,
                "rationale": "Should work now"
            }
        )
        assert update_resp.status_code == 200


@pytest.mark.anyio
async def test_belief_nudge():
    """Test belief nudge endpoint."""
    persona_id = await seed_persona()
    async with async_session_maker() as session:
        belief = BeliefNode(
            persona_id=persona_id,
            title="Test belief",
            summary="Summary",
            current_confidence=0.5,
            tags="[]",
        )
        session.add(belief)
        await session.flush()
        stance = StanceVersion(
            persona_id=persona_id,
            belief_id=belief.id,
            text="Initial stance",
            confidence=0.5,
            status="current",
        )
        session.add(stance)
        await session.commit()
        belief_id = belief.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Nudge confidence up
        nudge_resp = await client.post(
            f"/api/v1/beliefs/{belief_id}/nudge",
            json={
                "persona_id": persona_id,
                "direction": "more_confident",
                "amount": 0.1
            }
        )
        assert nudge_resp.status_code == 200
        data = nudge_resp.json()
        assert data["belief_id"] == belief_id
        assert data["old_confidence"] == 0.5
        assert data["new_confidence"] > 0.5  # Should be increased
        assert data["status"] == "nudged"

        # Nudge confidence down
        old_conf = data["new_confidence"]
        nudge_resp = await client.post(
            f"/api/v1/beliefs/{belief_id}/nudge",
            json={
                "persona_id": persona_id,
                "direction": "less_confident",
                "amount": 0.05
            }
        )
        assert nudge_resp.status_code == 200
        data = nudge_resp.json()
        assert data["new_confidence"] < old_conf  # Should be decreased


@pytest.mark.anyio
async def test_belief_nudge_with_locked_stance():
    """Test that nudging a locked belief fails."""
    persona_id = await seed_persona()
    async with async_session_maker() as session:
        belief = BeliefNode(
            persona_id=persona_id,
            title="Test belief",
            summary="Summary",
            current_confidence=0.5,
            tags="[]",
        )
        session.add(belief)
        await session.flush()
        stance = StanceVersion(
            persona_id=persona_id,
            belief_id=belief.id,
            text="Initial stance",
            confidence=0.5,
            status="locked",  # Already locked
        )
        session.add(stance)
        await session.commit()
        belief_id = belief.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Try to nudge (should fail)
        nudge_resp = await client.post(
            f"/api/v1/beliefs/{belief_id}/nudge",
            json={
                "persona_id": persona_id,
                "direction": "more_confident",
                "amount": 0.1
            }
        )
        assert nudge_resp.status_code == 403  # Permission error
