import asyncio
import pytest
from httpx import AsyncClient

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
    async with AsyncClient(app=app, base_url="http://test") as client:
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

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/activity?persona_id={persona_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body and body[0]["reddit_id"] == "t1_test"


@pytest.mark.anyio
async def test_moderation_pending_and_approve():
    persona_id = await seed_persona()
    async with async_session_maker() as session:
        pending = PendingPost(
            persona_id=persona_id,
            content="draft",
            post_type="comment",
            target_subreddit="testsub",
            status="pending",
        )
        session.add(pending)
        await session.commit()
        pending_id = pending.id

    async with AsyncClient(app=app, base_url="http://test") as client:
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

    async with AsyncClient(app=app, base_url="http://test") as client:
        graph_resp = await client.get(f"/api/v1/beliefs?persona_id={persona_id}")
        assert graph_resp.status_code == 200
        assert graph_resp.json()["nodes"][0]["id"] == belief_id

        hist_resp = await client.get(f"/api/v1/beliefs/{belief_id}/history?persona_id={persona_id}")
        assert hist_resp.status_code == 200
        assert hist_resp.json()["belief"]["id"] == belief_id
