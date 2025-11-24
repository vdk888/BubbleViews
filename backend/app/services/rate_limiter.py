"""
Token Bucket Rate Limiter

Implements a thread-safe token bucket algorithm for rate limiting API requests.
Designed for Reddit API's 60 requests/minute limit with burst allowance.

Key features:
- Asynchronous token acquisition with wait support
- Thread-safe via asyncio.Lock
- Configurable capacity and refill rate
- Automatic token replenishment
- Burst traffic handling
"""

import asyncio
import time
from typing import Optional


class TokenBucket:
    """
    Token bucket rate limiter for async operations.

    The bucket holds a maximum number of tokens and refills at a constant rate.
    Each API call consumes one token. If no tokens are available, the caller
    waits until a token is refilled.

    Attributes:
        capacity: Maximum number of tokens (burst allowance)
        refill_rate: Tokens added per second
        tokens: Current available tokens
        last_refill: Timestamp of last refill operation
    """

    def __init__(
        self,
        capacity: int = 60,
        refill_rate: float = 1.0
    ):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum tokens (default: 60 for Reddit's 60/min limit)
            refill_rate: Tokens per second (default: 1.0 = 60/min)

        Note:
            - Default configuration: 60 requests/minute with burst of 60
            - For Reddit: capacity=60, refill_rate=1.0
            - Starts with full bucket (capacity tokens available)
        """
        if capacity <= 0:
            raise ValueError("Capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("Refill rate must be positive")

        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """
        Refill tokens based on elapsed time.

        Calculates tokens to add based on time since last refill
        and the configured refill rate. Caps at capacity.

        Note:
            - Called automatically during acquire()
            - Uses monotonic clock for accuracy
            - Thread-safe when called within lock
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.refill_rate

        if new_tokens > 0:
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            self.last_refill = now

    async def acquire(
        self,
        tokens: int = 1,
        timeout: Optional[float] = None
    ) -> bool:
        """
        Acquire tokens from the bucket.

        Attempts to consume the specified number of tokens. If insufficient
        tokens are available, waits for refill. Supports timeout to prevent
        infinite waiting.

        Args:
            tokens: Number of tokens to acquire (default: 1)
            timeout: Maximum wait time in seconds (default: None = infinite)
                If timeout expires, returns False

        Returns:
            True if tokens acquired successfully
            False if timeout expired before acquiring tokens

        Raises:
            ValueError: If tokens <= 0 or tokens > capacity

        Note:
            - Blocks until tokens available or timeout
            - Multiple concurrent calls are serialized via lock
            - Uses asyncio.sleep() for non-blocking waits
            - Typical wait time: (tokens - current) / refill_rate seconds
        """
        if tokens <= 0:
            raise ValueError("Must acquire at least 1 token")
        if tokens > self.capacity:
            raise ValueError(f"Cannot acquire {tokens} tokens (capacity: {self.capacity})")

        start_time = time.monotonic() if timeout else None

        async with self._lock:
            while True:
                self._refill()

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

                # Check timeout
                if timeout is not None:
                    elapsed = time.monotonic() - start_time
                    if elapsed >= timeout:
                        return False

                # Calculate wait time until next token available
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.refill_rate

                # Cap wait time by remaining timeout
                if timeout is not None:
                    remaining = timeout - (time.monotonic() - start_time)
                    wait_time = min(wait_time, remaining)

                if wait_time > 0:
                    await asyncio.sleep(wait_time)

    async def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens without waiting.

        Non-blocking version of acquire(). Returns immediately if tokens
        are not available.

        Args:
            tokens: Number of tokens to acquire (default: 1)

        Returns:
            True if tokens acquired successfully
            False if insufficient tokens available

        Raises:
            ValueError: If tokens <= 0 or tokens > capacity

        Note:
            - Never blocks
            - Useful for optional operations or backpressure handling
            - Refills tokens before checking availability
        """
        if tokens <= 0:
            raise ValueError("Must acquire at least 1 token")
        if tokens > self.capacity:
            raise ValueError(f"Cannot acquire {tokens} tokens (capacity: {self.capacity})")

        async with self._lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    @property
    def available_tokens(self) -> float:
        """
        Get current available tokens (approximate).

        Note:
            - Does not acquire lock (may be slightly stale)
            - For monitoring/debugging only
            - Refills before returning value
        """
        return self.tokens

    def reset(self) -> None:
        """
        Reset bucket to full capacity.

        Useful for testing or manual rate limit resets.

        Note:
            - Not thread-safe (acquire lock externally if needed)
            - Resets token count and refill timestamp
        """
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()
