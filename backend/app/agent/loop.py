"""
Agent loop skeleton.

Provides a minimal stub to satisfy Phase 2 scaffolding.
Actual perception/retrieval/decision logic will be wired in Week 4.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AgentLoop:
    """
    Lightweight agent loop placeholder.
    """

    def __init__(self, interval_seconds: int = 60):
        self.interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        logger.info("Agent loop starting", extra={"interval_seconds": self.interval_seconds})
        while not self._stop_event.is_set():
            # TODO: plug perception -> retrieval -> decision -> moderation -> action
            logger.debug("Agent loop tick (stub)")
            await asyncio.sleep(self.interval_seconds)
        logger.info("Agent loop stopped")

    async def stop(self) -> None:
        self._stop_event.set()


async def run_agent(interval_seconds: int = 60, stop_after: Optional[int] = None) -> None:
    """
    Run the stub agent loop.

    Args:
        interval_seconds: delay between iterations
        stop_after: optional number of iterations to run (for tests)
    """
    loop = AgentLoop(interval_seconds=interval_seconds)
    iterations = 0
    while stop_after is None or iterations < stop_after:
        logger.debug("Agent stub iteration %s", iterations)
        iterations += 1
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_agent())
