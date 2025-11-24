"""
Tests for SSE streaming endpoint and event publisher.

Tests cover:
- Event publisher pub/sub functionality
- SSE endpoint streaming and format
- Connection management and cleanup
- Event delivery to multiple subscribers
"""

import asyncio
import pytest
from fastapi.testclient import TestClient

from app.services.event_publisher import EventPublisher, Event, EventType


class TestEventPublisher:
    """Tests for EventPublisher service."""

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test that EventPublisher is a singleton."""
        publisher1 = EventPublisher()
        publisher2 = EventPublisher()
        assert publisher1 is publisher2

    @pytest.mark.asyncio
    async def test_publish_without_subscribers(self):
        """Test publishing when no subscribers exist."""
        publisher = EventPublisher()

        event = Event(
            type=EventType.NEW_INTERACTION,
            persona_id="test-persona",
            data={"content": "Test"}
        )

        count = await publisher.publish(event)
        assert count == 0

    @pytest.mark.asyncio
    async def test_publish_with_subscriber(self):
        """Test publishing to a single subscriber."""
        publisher = EventPublisher()

        events_received = []

        async def subscriber():
            async for event in publisher.subscribe("test-persona"):
                events_received.append(event)
                break  # Exit after first event

        # Start subscriber in background
        task = asyncio.create_task(subscriber())

        # Give subscriber time to connect
        await asyncio.sleep(0.1)

        # Publish event
        event = Event(
            type=EventType.NEW_INTERACTION,
            persona_id="test-persona",
            data={"content": "Test interaction"}
        )
        count = await publisher.publish(event)

        # Wait for subscriber to receive
        await asyncio.wait_for(task, timeout=1.0)

        assert count == 1
        assert len(events_received) == 1
        assert events_received[0].type == EventType.NEW_INTERACTION
        assert events_received[0].data["content"] == "Test interaction"

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_persona(self):
        """Test publishing to multiple subscribers for same persona."""
        publisher = EventPublisher()

        events_received_1 = []
        events_received_2 = []

        async def subscriber_1():
            async for event in publisher.subscribe("test-persona"):
                events_received_1.append(event)
                break

        async def subscriber_2():
            async for event in publisher.subscribe("test-persona"):
                events_received_2.append(event)
                break

        # Start both subscribers
        task1 = asyncio.create_task(subscriber_1())
        task2 = asyncio.create_task(subscriber_2())

        await asyncio.sleep(0.1)

        # Publish event
        event = Event(
            type=EventType.PENDING_POST_ADDED,
            persona_id="test-persona",
            data={"id": "post123"}
        )
        count = await publisher.publish(event)

        # Wait for both to receive
        await asyncio.wait_for(asyncio.gather(task1, task2), timeout=1.0)

        assert count == 2
        assert len(events_received_1) == 1
        assert len(events_received_2) == 1
        assert events_received_1[0].data["id"] == "post123"
        assert events_received_2[0].data["id"] == "post123"

    @pytest.mark.asyncio
    async def test_subscribers_different_personas(self):
        """Test that events only go to subscribers of correct persona."""
        publisher = EventPublisher()

        events_persona_a = []
        events_persona_b = []

        async def subscriber_a():
            async for event in publisher.subscribe("persona-a"):
                events_persona_a.append(event)
                break

        async def subscriber_b():
            async for event in publisher.subscribe("persona-b"):
                events_persona_b.append(event)
                # This will timeout since we only publish to persona-a
                await asyncio.sleep(0.5)
                break

        task_a = asyncio.create_task(subscriber_a())
        task_b = asyncio.create_task(subscriber_b())

        await asyncio.sleep(0.1)

        # Publish only to persona-a
        event = Event(
            type=EventType.BELIEF_UPDATED,
            persona_id="persona-a",
            data={"belief_id": "belief123"}
        )
        count = await publisher.publish(event)

        # Wait for persona-a subscriber
        await asyncio.wait_for(task_a, timeout=1.0)

        assert count == 1
        assert len(events_persona_a) == 1
        assert len(events_persona_b) == 0

        # Cancel persona-b task
        task_b.cancel()
        try:
            await task_b
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_subscriber_cleanup(self):
        """Test that subscribers are cleaned up on disconnect."""
        publisher = EventPublisher()

        async def subscriber():
            async for event in publisher.subscribe("test-persona"):
                await asyncio.sleep(0.01)

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        # Should have 1 subscriber
        assert publisher.get_subscriber_count("test-persona") == 1

        # Cancel task (simulates disconnect)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        await asyncio.sleep(0.1)

        # Subscriber should be cleaned up
        assert publisher.get_subscriber_count("test-persona") == 0

    @pytest.mark.asyncio
    async def test_convenience_methods(self):
        """Test convenience publishing methods."""
        publisher = EventPublisher()

        events_received = []

        async def subscriber():
            count = 0
            async for event in publisher.subscribe("test-persona"):
                events_received.append(event)
                count += 1
                if count >= 4:  # Expect 4 different event types
                    break

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        # Test all convenience methods
        await publisher.publish_new_interaction(
            "test-persona",
            {"content": "New post"}
        )
        await publisher.publish_pending_post_added(
            "test-persona",
            {"id": "pending123"}
        )
        await publisher.publish_belief_updated(
            "test-persona",
            {"belief_id": "belief123"}
        )
        await publisher.publish_agent_status_changed(
            "test-persona",
            {"status": "running"}
        )

        await asyncio.wait_for(task, timeout=1.0)

        assert len(events_received) == 4
        assert events_received[0].type == EventType.NEW_INTERACTION
        assert events_received[1].type == EventType.PENDING_POST_ADDED
        assert events_received[2].type == EventType.BELIEF_UPDATED
        assert events_received[3].type == EventType.AGENT_STATUS_CHANGED


class TestEventFormatting:
    """Tests for Event formatting methods."""

    def test_event_to_dict(self):
        """Test Event.to_dict() serialization."""
        event = Event(
            type=EventType.NEW_INTERACTION,
            persona_id="test-persona",
            data={"content": "Test"}
        )

        event_dict = event.to_dict()

        assert event_dict["type"] == "new_interaction"
        assert event_dict["persona_id"] == "test-persona"
        assert event_dict["data"]["content"] == "Test"
        assert "timestamp" in event_dict
        assert isinstance(event_dict["timestamp"], str)  # ISO format

    def test_event_to_sse_format(self):
        """Test Event.to_sse_format() SSE formatting."""
        event = Event(
            type=EventType.PENDING_POST_ADDED,
            persona_id="test-persona",
            data={"id": "post123"}
        )

        sse_text = event.to_sse_format()

        # SSE format: event: <type>\ndata: <json>\n\n
        assert sse_text.startswith("event: pending_post_added\n")
        assert "data: {" in sse_text
        assert '"persona_id": "test-persona"' in sse_text
        assert sse_text.endswith("\n\n")


class TestSSEEndpoint:
    """Tests for /api/v1/stream endpoint."""

    def test_stream_status_no_subscribers(self, client: TestClient):
        """Test /stream/status with no active subscribers."""
        response = client.get("/api/v1/stream/status")
        assert response.status_code == 200

        data = response.json()
        assert data["total_subscribers"] == 0
        assert data["personas"] == {}

    def test_stream_status_with_persona(self, client: TestClient):
        """Test /stream/status for specific persona."""
        response = client.get("/api/v1/stream/status?persona_id=test-persona")
        assert response.status_code == 200

        data = response.json()
        assert data["persona_id"] == "test-persona"
        assert data["subscriber_count"] == 0

    @pytest.mark.asyncio
    async def test_stream_endpoint_requires_persona_id(self, client: TestClient):
        """Test /stream endpoint requires persona_id query parameter."""
        response = client.get("/api/v1/stream")
        assert response.status_code == 422  # Validation error

    # Note: Testing actual SSE streaming is complex with TestClient
    # Would require async httpx client or manual EventSource testing
    # Manual testing preferred for full SSE flow


# Integration test (requires running server)
@pytest.mark.integration
class TestSSEIntegration:
    """
    Integration tests for SSE streaming.

    These tests require a running server and are marked with @pytest.mark.integration.
    Run with: pytest -m integration
    """

    @pytest.mark.asyncio
    async def test_full_sse_flow(self):
        """
        Full SSE flow test (requires manual verification).

        To test manually:
        1. Start server: uvicorn app.main:app --reload
        2. curl -N http://localhost:8000/api/v1/stream?persona_id=test
        3. In another terminal, trigger events via API calls
        4. Verify events appear in curl output
        """
        pytest.skip("Manual integration test - requires running server")
