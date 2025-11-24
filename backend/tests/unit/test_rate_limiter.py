"""
Unit tests for TokenBucket rate limiter.

Tests cover:
- Basic token acquisition
- Token refilling over time
- Concurrent access
- Timeout behavior
- try_acquire non-blocking behavior
- Edge cases and error handling
"""

import asyncio
import pytest
import time

from app.services.rate_limiter import TokenBucket


class TestTokenBucket:
    """Test suite for TokenBucket rate limiter."""

    def test_initialization_valid(self):
        """Test bucket initializes with correct parameters."""
        bucket = TokenBucket(capacity=60, refill_rate=1.0)

        assert bucket.capacity == 60
        assert bucket.refill_rate == 1.0
        assert bucket.tokens == 60.0  # Starts full
        assert bucket._lock is not None

    def test_initialization_invalid_capacity(self):
        """Test initialization fails with invalid capacity."""
        with pytest.raises(ValueError, match="Capacity must be positive"):
            TokenBucket(capacity=0, refill_rate=1.0)

        with pytest.raises(ValueError, match="Capacity must be positive"):
            TokenBucket(capacity=-10, refill_rate=1.0)

    def test_initialization_invalid_refill_rate(self):
        """Test initialization fails with invalid refill rate."""
        with pytest.raises(ValueError, match="Refill rate must be positive"):
            TokenBucket(capacity=60, refill_rate=0.0)

        with pytest.raises(ValueError, match="Refill rate must be positive"):
            TokenBucket(capacity=60, refill_rate=-1.0)

    @pytest.mark.asyncio
    async def test_acquire_single_token(self):
        """Test acquiring a single token."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Should succeed immediately
        result = await bucket.acquire(1)
        assert result is True
        assert bucket.tokens == 9.0

    @pytest.mark.asyncio
    async def test_acquire_multiple_tokens(self):
        """Test acquiring multiple tokens at once."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        result = await bucket.acquire(5)
        assert result is True
        assert bucket.tokens == 5.0

    @pytest.mark.asyncio
    async def test_acquire_waits_for_refill(self):
        """Test acquire waits when tokens insufficient."""
        bucket = TokenBucket(capacity=5, refill_rate=10.0)  # Refills quickly

        # Drain bucket
        await bucket.acquire(5)
        assert bucket.tokens == 0.0

        # Next acquire should wait
        start = time.monotonic()
        result = await bucket.acquire(1)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed >= 0.1  # Should wait ~0.1s (1 token / 10 tokens/s)
        assert elapsed < 0.2   # Should not wait too long

    @pytest.mark.asyncio
    async def test_acquire_timeout_expires(self):
        """Test acquire returns False when timeout expires."""
        bucket = TokenBucket(capacity=5, refill_rate=1.0)

        # Drain bucket
        await bucket.acquire(5)

        # Try to acquire with short timeout
        result = await bucket.acquire(1, timeout=0.1)
        assert result is False  # Timeout expired

    @pytest.mark.asyncio
    async def test_acquire_timeout_succeeds(self):
        """Test acquire succeeds within timeout period."""
        bucket = TokenBucket(capacity=5, refill_rate=10.0)

        # Drain bucket
        await bucket.acquire(5)

        # Try to acquire with sufficient timeout
        result = await bucket.acquire(1, timeout=0.5)
        assert result is True  # Should succeed

    @pytest.mark.asyncio
    async def test_acquire_invalid_tokens(self):
        """Test acquire fails with invalid token counts."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        with pytest.raises(ValueError, match="Must acquire at least 1 token"):
            await bucket.acquire(0)

        with pytest.raises(ValueError, match="Must acquire at least 1 token"):
            await bucket.acquire(-1)

        with pytest.raises(ValueError, match="Cannot acquire .* tokens"):
            await bucket.acquire(11)  # More than capacity

    @pytest.mark.asyncio
    async def test_try_acquire_success(self):
        """Test try_acquire succeeds when tokens available."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        result = await bucket.try_acquire(3)
        assert result is True
        assert bucket.tokens == 7.0

    @pytest.mark.asyncio
    async def test_try_acquire_failure(self):
        """Test try_acquire fails when tokens insufficient."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Drain bucket
        await bucket.acquire(10)

        # Try to acquire without waiting
        result = await bucket.try_acquire(1)
        assert result is False
        assert bucket.tokens == 0.0  # Tokens not consumed

    @pytest.mark.asyncio
    async def test_try_acquire_invalid_tokens(self):
        """Test try_acquire fails with invalid token counts."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        with pytest.raises(ValueError, match="Must acquire at least 1 token"):
            await bucket.try_acquire(0)

        with pytest.raises(ValueError, match="Cannot acquire .* tokens"):
            await bucket.try_acquire(11)

    @pytest.mark.asyncio
    async def test_refill_behavior(self):
        """Test tokens refill correctly over time."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)

        # Drain bucket
        await bucket.acquire(10)
        assert bucket.tokens == 0.0

        # Wait for refill
        await asyncio.sleep(0.5)  # Should add ~5 tokens

        result = await bucket.try_acquire(4)
        assert result is True  # Should have enough tokens

    @pytest.mark.asyncio
    async def test_refill_caps_at_capacity(self):
        """Test tokens don't exceed capacity after refill."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)

        # Start with some tokens
        await bucket.acquire(5)
        assert bucket.tokens == 5.0

        # Wait longer than needed to fill
        await asyncio.sleep(1.0)  # Would add 10 tokens, but capped at capacity

        # Check tokens capped at capacity
        result = await bucket.try_acquire(10)
        assert result is True
        assert bucket.tokens == 0.0

        # Should not have more than capacity
        result = await bucket.try_acquire(1)
        assert result is False

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test thread-safe concurrent token acquisition."""
        bucket = TokenBucket(capacity=20, refill_rate=100.0)  # Fast refill

        acquired_counts = []

        async def acquire_tokens(n: int):
            result = await bucket.acquire(n)
            if result:
                acquired_counts.append(n)

        # Launch concurrent acquires
        tasks = [
            acquire_tokens(2),
            acquire_tokens(3),
            acquire_tokens(5),
            acquire_tokens(4),
            acquire_tokens(3),
        ]

        await asyncio.gather(*tasks)

        # All should succeed eventually (fast refill)
        assert len(acquired_counts) == 5
        assert sum(acquired_counts) == 17  # Total tokens acquired

    @pytest.mark.asyncio
    async def test_available_tokens_property(self):
        """Test available_tokens property returns current count."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        assert bucket.available_tokens == 10.0

        await bucket.acquire(3)
        assert bucket.available_tokens == 7.0

    def test_reset(self):
        """Test reset restores bucket to full capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Drain some tokens
        asyncio.run(bucket.acquire(7))
        assert bucket.tokens == 3.0

        # Reset
        bucket.reset()
        assert bucket.tokens == 10.0

    @pytest.mark.asyncio
    async def test_multiple_sequential_acquires(self):
        """Test multiple sequential acquires work correctly."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Acquire in sequence
        assert await bucket.acquire(2) is True
        assert bucket.tokens == 8.0

        assert await bucket.acquire(3) is True
        assert bucket.tokens == 5.0

        assert await bucket.acquire(4) is True
        assert bucket.tokens == 1.0

        assert await bucket.acquire(1) is True
        assert bucket.tokens == 0.0

    @pytest.mark.asyncio
    async def test_burst_handling(self):
        """Test bucket handles burst traffic correctly."""
        bucket = TokenBucket(capacity=60, refill_rate=1.0)

        # Simulate burst: 60 requests immediately
        results = await asyncio.gather(*[
            bucket.try_acquire(1) for _ in range(60)
        ])

        # All 60 should succeed (burst capacity)
        assert all(results)
        assert bucket.tokens == 0.0

        # 61st should fail
        result = await bucket.try_acquire(1)
        assert result is False

    @pytest.mark.asyncio
    async def test_rate_limiting_reddit_scenario(self):
        """Test bucket enforces Reddit's 60 req/min limit."""
        # Reddit config: 60 requests/minute = 1 request/second
        bucket = TokenBucket(capacity=60, refill_rate=1.0)

        # Make 60 requests (burst)
        for _ in range(60):
            result = await bucket.try_acquire(1)
            assert result is True

        # 61st request should wait
        start = time.monotonic()
        result = await bucket.acquire(1, timeout=2.0)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed >= 1.0  # Should wait ~1 second for refill
        assert elapsed < 1.5   # Should not wait excessively
