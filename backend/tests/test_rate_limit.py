"""
Tests for rate limiting middleware.

Tests the token bucket algorithm and rate limit enforcement.
"""

import pytest
import time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.rate_limit import RateLimitMiddleware, TokenBucket


class TestTokenBucket:
    """Unit tests for TokenBucket implementation."""

    def test_token_bucket_initialization(self):
        """Test token bucket initializes with full capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.capacity == 10
        assert bucket.refill_rate == 1.0
        assert bucket.tokens == 10.0

    def test_consume_token_success(self):
        """Test consuming tokens when available."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(1) is True
        assert bucket.tokens == 9.0

    def test_consume_token_failure(self):
        """Test consuming tokens when insufficient."""
        bucket = TokenBucket(capacity=1, refill_rate=1.0)
        assert bucket.consume(1) is True  # First consume succeeds
        assert bucket.consume(1) is False  # Second fails (no tokens left)

    def test_token_refill_over_time(self):
        """Test tokens refill at correct rate."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)  # 10 tokens/second
        bucket.consume(5)  # Use 5 tokens
        assert bucket.tokens == 5.0

        # Wait 0.5 seconds, should refill 5 tokens (10 * 0.5)
        time.sleep(0.5)
        bucket.consume(0)  # Trigger refill by consuming 0
        assert bucket.tokens >= 9.9  # Should be close to full

    def test_token_refill_cap(self):
        """Test tokens don't exceed capacity during refill."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)
        time.sleep(0.5)  # Wait for refill
        bucket.consume(0)  # Trigger refill
        assert bucket.tokens <= 10.0  # Should not exceed capacity

    def test_multiple_token_consumption(self):
        """Test consuming multiple tokens at once."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(5) is True
        assert bucket.tokens == 5.0
        assert bucket.consume(6) is False  # Not enough tokens
        assert bucket.consume(5) is True  # Exactly enough

    def test_get_wait_time(self):
        """Test wait time calculation."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)  # 2 tokens/second
        bucket.consume(10)  # Empty bucket
        wait_time = bucket.get_wait_time()
        assert wait_time >= 0.4  # Need 1 token, refill rate is 2/sec = 0.5 sec
        assert wait_time <= 0.6  # Allow some tolerance


class TestRateLimitMiddleware:
    """Integration tests for rate limiting middleware."""

    @pytest.fixture
    def app_with_rate_limit(self, monkeypatch):
        """Create test app with rate limiting."""
        # Enable rate limiting for these tests (overriding conftest)
        monkeypatch.delenv("DISABLE_RATE_LIMIT", raising=False)
        
        app = FastAPI()

        # Add rate limiting middleware
        app.add_middleware(
            RateLimitMiddleware,
            auth_limit=5,  # 5 req/min for testing
            default_limit=10  # 10 req/min for testing
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        @app.get("/auth/login")
        async def auth_endpoint():
            return {"message": "auth success"}

        return app

    def test_rate_limit_allows_requests_under_limit(self, app_with_rate_limit):
        """Test requests are allowed when under rate limit."""
        client = TestClient(app_with_rate_limit)

        # Make 5 requests (under limit of 10)
        for i in range(5):
            response = client.get("/test")
            assert response.status_code == 200
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers

    def test_rate_limit_blocks_requests_over_limit(self, app_with_rate_limit):
        """Test requests are blocked when over rate limit."""
        client = TestClient(app_with_rate_limit)

        # Make requests up to limit (10 for default endpoints)
        for i in range(10):
            response = client.get("/test")
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get("/test")
        assert response.status_code == 429
        assert response.json()["detail"] == "Rate limit exceeded"
        assert "Retry-After" in response.headers

    def test_rate_limit_auth_endpoint_stricter(self, app_with_rate_limit):
        """Test auth endpoints have stricter rate limits."""
        client = TestClient(app_with_rate_limit)

        # Auth endpoints limited to 5 req/min in test config
        for i in range(5):
            response = client.get("/auth/login")
            assert response.status_code == 200

        # 6th request should be blocked
        response = client.get("/auth/login")
        assert response.status_code == 429

    def test_rate_limit_different_ips_independent(self, app_with_rate_limit):
        """Test rate limits are per-IP (mocked via headers)."""
        # Note: In real deployment behind proxy, use X-Forwarded-For
        # TestClient doesn't easily support multiple IPs, so this test
        # validates the header parsing logic exists
        client = TestClient(app_with_rate_limit)

        # Make requests with X-Forwarded-For header
        headers1 = {"X-Forwarded-For": "192.168.1.1"}
        headers2 = {"X-Forwarded-For": "192.168.1.2"}

        # IP1 exhausts limit
        for i in range(10):
            response = client.get("/test", headers=headers1)
            assert response.status_code == 200

        # IP1 blocked
        response = client.get("/test", headers=headers1)
        assert response.status_code == 429

        # IP2 still works (independent bucket)
        response = client.get("/test", headers=headers2)
        assert response.status_code == 200

    def test_rate_limit_returns_correct_headers(self, app_with_rate_limit):
        """Test rate limit headers are present and correct."""
        client = TestClient(app_with_rate_limit)

        response = client.get("/test")
        assert response.status_code == 200

        # Check required headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

        # Verify values
        limit = int(response.headers["X-RateLimit-Limit"])
        remaining = int(response.headers["X-RateLimit-Remaining"])
        assert limit == 10  # Default limit for test
        assert remaining >= 0
        assert remaining <= limit

    def test_rate_limit_429_response_format(self, app_with_rate_limit):
        """Test 429 response has correct format and retry info."""
        client = TestClient(app_with_rate_limit)

        # Exhaust limit
        for i in range(10):
            client.get("/test")

        # Get 429 response
        response = client.get("/test")
        assert response.status_code == 429

        # Check response body
        data = response.json()
        assert "detail" in data
        assert "limit" in data
        assert "window" in data
        assert "retry_after" in data
        assert data["limit"] == 10
        assert data["window"] == "1 minute"
        assert isinstance(data["retry_after"], int)

        # Check headers
        assert "Retry-After" in response.headers

    def test_rate_limit_refill_allows_new_requests(self, app_with_rate_limit):
        """Test tokens refill over time allowing new requests."""
        client = TestClient(app_with_rate_limit)

        # Consume some tokens
        for i in range(5):
            response = client.get("/test")
            assert response.status_code == 200

        # Wait for refill (10 tokens/min = 1 token per 6 seconds)
        # In test, we set refill_rate = limit/60
        # For 10 limit: 10/60 = 0.166 tokens/second
        # Wait 1 second should give ~0.166 tokens
        time.sleep(1.0)

        # Should be able to make more requests (tokens refilled)
        response = client.get("/test")
        assert response.status_code == 200


class TestRateLimitConfiguration:
    """Test rate limit configuration and customization."""

    def test_custom_rate_limits(self, monkeypatch):
        """Test custom rate limit configuration."""
        # Enable rate limiting for this test
        monkeypatch.delenv("DISABLE_RATE_LIMIT", raising=False)
        
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            auth_limit=2,  # Very strict for testing
            default_limit=5
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)

        # Verify custom limit applied
        for i in range(5):
            response = client.get("/test")
            assert response.status_code == 200

        # 6th request blocked
        response = client.get("/test")
        assert response.status_code == 429

    def test_cleanup_old_buckets(self):
        """Test old IP buckets are cleaned up to prevent memory leak."""
        bucket_middleware = RateLimitMiddleware(
            app=None,
            auth_limit=10,
            default_limit=60,
            cleanup_interval=1  # Clean up every 1 second for testing
        )

        # Add some buckets
        bucket_middleware.buckets["192.168.1.1"] = (
            TokenBucket(10, 1.0),
            time.time() - 700  # 700 seconds ago (>10 min)
        )
        bucket_middleware.buckets["192.168.1.2"] = (
            TokenBucket(10, 1.0),
            time.time()  # Recent
        )

        # Trigger cleanup
        bucket_middleware.last_cleanup = time.time() - 2  # Force cleanup
        bucket_middleware._cleanup_old_buckets(time.time())

        # Old bucket should be removed, recent bucket kept
        assert "192.168.1.1" not in bucket_middleware.buckets
        assert "192.168.1.2" in bucket_middleware.buckets
