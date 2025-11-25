"""
Agent Manager Service

Manages running agent loop processes as background asyncio tasks.
Provides centralized control for starting, stopping, and monitoring
agent loops per persona.

This is a singleton service that persists across requests to maintain
references to running agent tasks.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass

from app.core.database import async_session_maker
from app.services.reddit_client import AsyncPRAWClient
from app.services.llm_client import OpenRouterClient
from app.services.memory_store import SQLiteMemoryStore
from app.services.retrieval import RetrievalCoordinator
from app.services.moderation import ModerationService
from app.agent.loop import AgentLoop

logger = logging.getLogger(__name__)


@dataclass
class AgentStatus:
    """Status information for a running agent."""
    persona_id: str
    status: str  # "running", "stopped", "error"
    started_at: Optional[datetime]
    last_activity: Optional[datetime]
    error_message: Optional[str]
    cycle_count: int


class AgentManager:
    """
    Singleton manager for agent loop tasks.

    Maintains references to running agent tasks and provides
    control methods for starting/stopping agents per persona.
    """

    _instance: Optional["AgentManager"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        """
        Initialize agent manager.

        Private constructor - use get_instance() instead.
        """
        # Map of persona_id -> asyncio.Task
        self._running_tasks: Dict[str, asyncio.Task] = {}

        # Map of persona_id -> asyncio.Event (stop signals)
        self._stop_events: Dict[str, asyncio.Event] = {}

        # Map of persona_id -> AgentStatus
        self._status_map: Dict[str, AgentStatus] = {}

        # Shared service instances (initialized once)
        self._reddit_client: Optional[AsyncPRAWClient] = None
        self._llm_client: Optional[OpenRouterClient] = None
        self._memory_store: Optional[SQLiteMemoryStore] = None
        self._retrieval: Optional[RetrievalCoordinator] = None
        self._moderation: Optional[ModerationService] = None

        logger.info("AgentManager initialized")

    @classmethod
    async def get_instance(cls) -> "AgentManager":
        """
        Get singleton instance of AgentManager.

        Thread-safe lazy initialization.

        Returns:
            AgentManager singleton instance
        """
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def _initialize_services(self) -> None:
        """
        Initialize shared service instances.

        Services are reused across all agent loops for efficiency.

        Raises:
            ConnectionError: If service initialization fails
        """
        if self._reddit_client is not None:
            # Already initialized
            return

        try:
            # Import here to avoid circular dependencies at module level
            import os
            from dotenv import load_dotenv

            # Load .env file to ensure environment variables are available
            load_dotenv()

            # Initialize Reddit client
            self._reddit_client = AsyncPRAWClient(
                client_id=os.getenv('REDDIT_CLIENT_ID'),
                client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
                user_agent=os.getenv('REDDIT_USER_AGENT'),
                username=os.getenv('REDDIT_USERNAME'),
                password=os.getenv('REDDIT_PASSWORD'),
            )

            # Initialize LLM client
            self._llm_client = OpenRouterClient()

            # Initialize memory store
            self._memory_store = SQLiteMemoryStore(async_session_maker)

            # Initialize retrieval coordinator
            from app.services.embedding import get_embedding_service
            embedding_service = get_embedding_service()
            self._retrieval = RetrievalCoordinator(
                memory_store=self._memory_store,
                embedding_service=embedding_service
            )

            # Initialize moderation service
            self._moderation = ModerationService(async_session_maker)

            logger.info("Agent services initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize agent services: {e}")
            raise ConnectionError(f"Service initialization failed: {e}")

    async def start_agent(
        self,
        persona_id: str,
        interval_seconds: int = 60,
        max_posts_per_cycle: int = 5,
        response_probability: float = 0.3
    ) -> Dict[str, Any]:
        """
        Start agent loop for a persona.

        If agent is already running for this persona, returns current status
        without starting a new task.

        Args:
            persona_id: UUID of persona to run agent for
            interval_seconds: Seconds between perception cycles (default: 60)
            max_posts_per_cycle: Max posts to process per cycle (default: 5)
            response_probability: Probability of responding to eligible posts (default: 0.3)

        Returns:
            Status dict with:
            - persona_id: str
            - status: "running" | "started"
            - started_at: ISO timestamp
            - message: str

        Raises:
            ValueError: If persona not found or invalid
            ConnectionError: If services fail to initialize
        """
        # Check if already running
        if persona_id in self._running_tasks:
            task = self._running_tasks[persona_id]
            if not task.done():
                logger.info(f"Agent already running for persona {persona_id}")
                status = self._status_map.get(persona_id)
                return {
                    "persona_id": persona_id,
                    "status": "running",
                    "started_at": status.started_at.isoformat() if status and status.started_at else None,
                    "message": "Agent is already running"
                }

        # Initialize services if needed
        await self._initialize_services()

        # Validate persona exists
        try:
            persona = await self._memory_store.get_persona(persona_id)
            if not persona:
                raise ValueError(f"Persona not found: {persona_id}")
            logger.info(f"Starting agent for persona: {persona['reddit_username']}")
        except Exception as e:
            logger.error(f"Failed to load persona {persona_id}: {e}")
            raise ValueError(f"Persona validation failed: {e}")

        # Create stop event
        stop_event = asyncio.Event()
        self._stop_events[persona_id] = stop_event

        # Create agent loop
        agent_loop = AgentLoop(
            reddit_client=self._reddit_client,
            llm_client=self._llm_client,
            memory_store=self._memory_store,
            retrieval=self._retrieval,
            moderation=self._moderation,
            interval_seconds=interval_seconds,
            max_posts_per_cycle=max_posts_per_cycle,
            response_probability=response_probability,
        )

        # Create status tracking
        status = AgentStatus(
            persona_id=persona_id,
            status="running",
            started_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            error_message=None,
            cycle_count=0
        )
        self._status_map[persona_id] = status

        # Start task in background
        task = asyncio.create_task(
            self._run_agent_with_error_handling(agent_loop, persona_id, stop_event)
        )
        self._running_tasks[persona_id] = task

        logger.info(f"Agent loop started for persona {persona_id}")

        return {
            "persona_id": persona_id,
            "status": "started",
            "started_at": status.started_at.isoformat(),
            "message": f"Agent started for u/{persona['reddit_username']}"
        }

    async def _run_agent_with_error_handling(
        self,
        agent_loop: AgentLoop,
        persona_id: str,
        stop_event: asyncio.Event
    ) -> None:
        """
        Run agent loop with error handling and status updates.

        Wrapper that catches exceptions and updates status accordingly.

        Args:
            agent_loop: AgentLoop instance to run
            persona_id: UUID of persona
            stop_event: Event to signal stop
        """
        try:
            await agent_loop.run(persona_id, stop_event)

            # Normal completion
            status = self._status_map.get(persona_id)
            if status:
                status.status = "stopped"
                status.last_activity = datetime.utcnow()

            logger.info(f"Agent loop completed normally for persona {persona_id}")

        except Exception as e:
            logger.error(f"Agent loop crashed for persona {persona_id}: {e}", exc_info=True)

            # Update status with error
            status = self._status_map.get(persona_id)
            if status:
                status.status = "error"
                status.error_message = str(e)
                status.last_activity = datetime.utcnow()

        finally:
            # Cleanup
            if persona_id in self._running_tasks:
                del self._running_tasks[persona_id]
            if persona_id in self._stop_events:
                del self._stop_events[persona_id]

    async def stop_agent(self, persona_id: str) -> Dict[str, Any]:
        """
        Stop agent loop for a persona.

        Signals the agent loop to stop gracefully. The loop will complete
        its current cycle before exiting.

        Args:
            persona_id: UUID of persona

        Returns:
            Status dict with:
            - persona_id: str
            - status: "stopped" | "not_running"
            - message: str

        Raises:
            ValueError: If persona not found
        """
        # Check if running
        if persona_id not in self._running_tasks:
            logger.warning(f"Agent not running for persona {persona_id}")
            return {
                "persona_id": persona_id,
                "status": "not_running",
                "message": "Agent is not running"
            }

        task = self._running_tasks[persona_id]
        if task.done():
            logger.warning(f"Agent task already completed for persona {persona_id}")
            del self._running_tasks[persona_id]
            return {
                "persona_id": persona_id,
                "status": "not_running",
                "message": "Agent was not running"
            }

        # Signal stop
        stop_event = self._stop_events.get(persona_id)
        if stop_event:
            logger.info(f"Signaling agent to stop for persona {persona_id}")
            stop_event.set()

            # Wait for task to complete (with timeout)
            try:
                await asyncio.wait_for(task, timeout=10.0)
                logger.info(f"Agent stopped successfully for persona {persona_id}")
            except asyncio.TimeoutError:
                logger.warning(f"Agent stop timeout for persona {persona_id}, cancelling task")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Update status
        status = self._status_map.get(persona_id)
        if status:
            status.status = "stopped"
            status.last_activity = datetime.utcnow()

        return {
            "persona_id": persona_id,
            "status": "stopped",
            "message": "Agent stopped successfully"
        }

    async def get_agent_status(self, persona_id: str) -> Dict[str, Any]:
        """
        Get current status of agent for a persona.

        Args:
            persona_id: UUID of persona

        Returns:
            Status dict with:
            - persona_id: str
            - status: "running" | "stopped" | "error" | "not_running"
            - started_at: ISO timestamp or None
            - last_activity: ISO timestamp or None
            - error_message: str or None
            - cycle_count: int
        """
        # Check if task exists and is running
        task = self._running_tasks.get(persona_id)
        is_running = task is not None and not task.done()

        # Get stored status
        status = self._status_map.get(persona_id)

        if not is_running and not status:
            # Never started or fully cleaned up
            return {
                "persona_id": persona_id,
                "status": "not_running",
                "started_at": None,
                "last_activity": None,
                "error_message": None,
                "cycle_count": 0
            }

        # Task exists or we have historical status
        current_status = "not_running"
        if is_running:
            current_status = "running"
        elif status:
            current_status = status.status

        return {
            "persona_id": persona_id,
            "status": current_status,
            "started_at": status.started_at.isoformat() if status and status.started_at else None,
            "last_activity": status.last_activity.isoformat() if status and status.last_activity else None,
            "error_message": status.error_message if status else None,
            "cycle_count": status.cycle_count if status else 0
        }

    async def get_all_agent_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all known agents.

        Returns:
            Dict mapping persona_id to status dict
        """
        statuses = {}

        # Include all personas with running tasks
        for persona_id in self._running_tasks.keys():
            statuses[persona_id] = await self.get_agent_status(persona_id)

        # Include all personas with historical status
        for persona_id in self._status_map.keys():
            if persona_id not in statuses:
                statuses[persona_id] = await self.get_agent_status(persona_id)

        return statuses

    async def shutdown_all(self) -> None:
        """
        Shutdown all running agents gracefully.

        Used during application shutdown to clean up resources.
        """
        logger.info("Shutting down all running agents...")

        # Get all running persona IDs
        running_ids = list(self._running_tasks.keys())

        # Stop all agents
        for persona_id in running_ids:
            try:
                await self.stop_agent(persona_id)
            except Exception as e:
                logger.error(f"Error stopping agent {persona_id}: {e}")

        # Close Reddit client if initialized
        if self._reddit_client:
            try:
                await self._reddit_client.close()
                logger.info("Reddit client closed")
            except Exception as e:
                logger.error(f"Error closing Reddit client: {e}")

        logger.info("All agents shut down")


# Global accessor function for dependency injection
async def get_agent_manager() -> AgentManager:
    """
    Get the singleton AgentManager instance.

    Used as a FastAPI dependency.

    Returns:
        AgentManager singleton instance
    """
    return await AgentManager.get_instance()
