"""
Event Publisher Service for real-time dashboard updates.

This module provides a pub/sub system for broadcasting events to connected
SSE clients. Events are published when:
- Agent posts new interactions (new_interaction)
- New posts are queued for moderation (pending_post_added)
- Beliefs are updated (belief_updated)
- Agent status changes (agent_status_changed)

Uses asyncio.Queue for in-memory event distribution (MVP approach).
Can be upgraded to Redis pub/sub for multi-instance deployments.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Event types for real-time updates."""
    NEW_INTERACTION = "new_interaction"
    PENDING_POST_ADDED = "pending_post_added"
    BELIEF_UPDATED = "belief_updated"
    AGENT_STATUS_CHANGED = "agent_status_changed"


@dataclass
class Event:
    """
    Event data structure for SSE streaming.

    Attributes:
        type: Event type (see EventType enum)
        persona_id: Persona ID this event belongs to
        data: Event payload (JSON-serializable dict)
        timestamp: Event creation timestamp
    """
    type: EventType
    persona_id: str
    data: Dict[str, Any]
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert event to dictionary for JSON serialization.

        Returns:
            Dict with event data suitable for SSE transmission
        """
        event_dict = asdict(self)
        # Convert datetime to ISO format string
        if isinstance(event_dict.get("timestamp"), datetime):
            event_dict["timestamp"] = event_dict["timestamp"].isoformat()
        # Convert enum to string
        if isinstance(event_dict.get("type"), EventType):
            event_dict["type"] = event_dict["type"].value
        return event_dict

    def to_sse_format(self) -> str:
        """
        Format event for Server-Sent Events transmission.

        SSE format:
            event: <event_type>
            data: <json_payload>

        Returns:
            SSE-formatted string
        """
        event_dict = self.to_dict()
        # SSE format requires "data: " prefix and double newline terminator
        return f"event: {self.type.value}\ndata: {json.dumps(event_dict)}\n\n"


class EventPublisher:
    """
    In-memory event publisher using asyncio.Queue.

    This is a singleton service that manages event subscriptions and
    publishing. Clients subscribe to events for a specific persona_id
    and receive all events for that persona via SSE.

    Thread-safe for concurrent access via asyncio primitives.
    """

    _instance: Optional['EventPublisher'] = None

    def __new__(cls):
        """Singleton pattern to ensure one publisher instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the event publisher."""
        if self._initialized:
            return

        # Store active subscriber queues keyed by persona_id
        # Each persona can have multiple subscribers (multiple browser tabs)
        self._subscribers: Dict[str, list[asyncio.Queue]] = {}

        # Lock for thread-safe subscriber management
        self._lock = asyncio.Lock()

        self._initialized = True
        logger.info("EventPublisher initialized")

    async def subscribe(self, persona_id: str) -> AsyncGenerator[Event, None]:
        """
        Subscribe to events for a specific persona.

        Creates an asyncio.Queue for this subscriber and yields events
        as they are published. Automatically cleans up on disconnect.

        Args:
            persona_id: Persona ID to subscribe to

        Yields:
            Event objects published for this persona

        Example:
            async for event in publisher.subscribe("persona_123"):
                print(f"Received: {event.type}")
        """
        # Create a queue for this subscriber
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)

        async with self._lock:
            if persona_id not in self._subscribers:
                self._subscribers[persona_id] = []
            self._subscribers[persona_id].append(queue)

        logger.info(f"New subscriber for persona_id={persona_id}. "
                   f"Total subscribers: {len(self._subscribers[persona_id])}")

        try:
            # Keep yielding events from the queue until client disconnects
            while True:
                # Wait for next event (blocks until available)
                # Use timeout to allow periodic health checks
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    # SSE spec: lines starting with ':' are comments
                    continue
        except asyncio.CancelledError:
            # Client disconnected
            logger.info(f"Subscriber disconnected for persona_id={persona_id}")
        finally:
            # Clean up subscriber queue
            async with self._lock:
                if persona_id in self._subscribers:
                    try:
                        self._subscribers[persona_id].remove(queue)
                        if not self._subscribers[persona_id]:
                            # No more subscribers for this persona
                            del self._subscribers[persona_id]
                        logger.info(f"Removed subscriber for persona_id={persona_id}. "
                                   f"Remaining: {len(self._subscribers.get(persona_id, []))}")
                    except ValueError:
                        # Queue already removed (race condition)
                        pass

    async def publish(self, event: Event) -> int:
        """
        Publish an event to all subscribers of a persona.

        Sends the event to all active subscriber queues for the given
        persona_id. Non-blocking; if a queue is full, the event is dropped
        for that subscriber (prevents slow clients from blocking others).

        Args:
            event: Event to publish

        Returns:
            Number of subscribers that received the event

        Example:
            event = Event(
                type=EventType.NEW_INTERACTION,
                persona_id="persona_123",
                data={"content": "New post", "reddit_id": "abc123"}
            )
            count = await publisher.publish(event)
            logger.info(f"Event sent to {count} subscribers")
        """
        persona_id = event.persona_id

        async with self._lock:
            subscribers = self._subscribers.get(persona_id, [])

            if not subscribers:
                logger.debug(f"No subscribers for persona_id={persona_id}, event dropped")
                return 0

        # Publish to all subscribers (outside lock to avoid blocking)
        delivered = 0
        for queue in subscribers:
            try:
                # Non-blocking put; drop event if queue is full
                # This prevents slow clients from blocking the publisher
                queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                logger.warning(
                    f"Subscriber queue full for persona_id={persona_id}, "
                    f"event dropped (type={event.type})"
                )

        logger.debug(
            f"Published event type={event.type} to {delivered} subscribers "
            f"for persona_id={persona_id}"
        )
        return delivered

    async def publish_new_interaction(
        self,
        persona_id: str,
        interaction_data: Dict[str, Any]
    ) -> int:
        """
        Convenience method to publish new_interaction event.

        Args:
            persona_id: Persona ID
            interaction_data: Interaction details (content, reddit_id, etc.)

        Returns:
            Number of subscribers that received the event
        """
        event = Event(
            type=EventType.NEW_INTERACTION,
            persona_id=persona_id,
            data=interaction_data
        )
        return await self.publish(event)

    async def publish_pending_post_added(
        self,
        persona_id: str,
        pending_post_data: Dict[str, Any]
    ) -> int:
        """
        Convenience method to publish pending_post_added event.

        Args:
            persona_id: Persona ID
            pending_post_data: Pending post details (id, content, etc.)

        Returns:
            Number of subscribers that received the event
        """
        event = Event(
            type=EventType.PENDING_POST_ADDED,
            persona_id=persona_id,
            data=pending_post_data
        )
        return await self.publish(event)

    async def publish_belief_updated(
        self,
        persona_id: str,
        belief_update_data: Dict[str, Any]
    ) -> int:
        """
        Convenience method to publish belief_updated event.

        Args:
            persona_id: Persona ID
            belief_update_data: Belief update details (belief_id, old/new confidence)

        Returns:
            Number of subscribers that received the event
        """
        event = Event(
            type=EventType.BELIEF_UPDATED,
            persona_id=persona_id,
            data=belief_update_data
        )
        return await self.publish(event)

    async def publish_agent_status_changed(
        self,
        persona_id: str,
        status_data: Dict[str, Any]
    ) -> int:
        """
        Convenience method to publish agent_status_changed event.

        Args:
            persona_id: Persona ID
            status_data: Agent status details (status, last_activity, etc.)

        Returns:
            Number of subscribers that received the event
        """
        event = Event(
            type=EventType.AGENT_STATUS_CHANGED,
            persona_id=persona_id,
            data=status_data
        )
        return await self.publish(event)

    def get_subscriber_count(self, persona_id: Optional[str] = None) -> int:
        """
        Get number of active subscribers.

        Args:
            persona_id: If provided, return count for that persona.
                       If None, return total count across all personas.

        Returns:
            Number of active subscribers
        """
        if persona_id:
            return len(self._subscribers.get(persona_id, []))

        return sum(len(subs) for subs in self._subscribers.values())


# Global singleton instance
event_publisher = EventPublisher()
