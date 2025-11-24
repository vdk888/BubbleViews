"""
Rate limiting middleware using token bucket algorithm.

This middleware implements per-IP rate limiting to protect against:
- Brute force attacks on authentication endpoints
- API abuse and resource exhaustion
- DDoS attempts

Token Bucket Algorithm:
- Each IP address gets a bucket with a fixed capacity
- Tokens are added at a constant rate (refill_rate)
- Each request consumes one token
- If no tokens available, request is rejected with 429

References:
- https://blog.compliiant.io/api-defense-with-rate-limiting-using-fastapi-and-token-buckets-0f5206fc5029
- https://medium.com/@viswanathan.arjun/develop-your-own-api-rate-limiter-in-fastapi-part-i-c9f0c88b49b5

Note: This is an in-memory implementation suitable for MVP.
For production with multiple instances, use Redis-based rate limiting.
"""

import time
from typing import Callable, Dict, Tuple
from collections import defaultdict
import logging

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class TokenBucket:
    """
    Token bucket for rate limiting.

    Tokens are added at a fixed rate up to a maximum capacity.
    Each request consumes one token.

    Attributes:
        capacity: Maximum number of tokens in the bucket
        refill_rate: Number of tokens added per second
        tokens: Current number of available tokens
        last_refill: Timestamp of last refill operation
    """

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum number of tokens (burst size)
            refill_rate: Tokens added per second (sustained rate)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume tokens from the bucket.

        Refills tokens based on elapsed time before checking availability.

        Args:
            tokens: Number of tokens to consume (default: 1)

        Returns:
            True if tokens were available and consumed, False otherwise
        """
        # Refill tokens based on elapsed time
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + (elapsed * self.refill_rate)
        )
        self.last_refill = now

        # Check if enough tokens available
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def get_wait_time(self) -> float:
        """
        Calculate time until next token is available.

        Returns:
            Seconds until next token refill
        """
        if self.tokens >= 1:
            return 0.0
        tokens_needed = 1 - self.tokens
        return tokens_needed / self.refill_rate


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using token bucket per IP address.

    Rate limits:
    - Auth endpoints (/auth/*): 10 requests/minute
    - Other endpoints: 60 requests/minute

    Returns 429 Too Many Requests when limit exceeded.

    Example:
        app.add_middleware(
            RateLimitMiddleware,
            auth_limit=10,
            default_limit=60
        )

    Security Notes:
    - Uses client IP for bucketing (can be spoofed behind proxies)
    - In-memory storage (not shared across instances)
    - Consider Redis for production with multiple workers
    - Add X-Forwarded-For handling for proxied deployments
    """

    def __init__(
        self,
        app,
        auth_limit: int = 10,
        default_limit: int = 60,
        cleanup_interval: int = 300,  # Clean up old buckets every 5 minutes
    ):
        """
        Initialize rate limiting middleware.

        Args:
            app: FastAPI application instance
            auth_limit: Requests per minute for auth endpoints
            default_limit: Requests per minute for other endpoints
            cleanup_interval: Seconds between cleanup of old buckets
        """
        super().__init__(app)
        self.auth_limit = auth_limit
        self.default_limit = default_limit
        self.cleanup_interval = cleanup_interval

        # Storage: {ip: (bucket, last_access_time)}
        self.buckets: Dict[str, Tuple[TokenBucket, float]] = {}
        self.last_cleanup = time.time()

        logger.info(
            "Rate limiting initialized",
            extra={
                "auth_limit": auth_limit,
                "default_limit": default_limit,
            }
        )

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.

        Checks X-Forwarded-For header for proxied requests.

        Args:
            request: FastAPI request object

        Returns:
            Client IP address as string
        """
        # Check for X-Forwarded-For (proxied requests)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take first IP in chain (original client)
            return forwarded.split(",")[0].strip()

        # Fallback to direct connection IP
        if request.client:
            return request.client.host
        return "unknown"

    def _get_rate_limit(self, path: str) -> int:
        """
        Determine rate limit for given path.

        Args:
            path: Request path

        Returns:
            Requests per minute limit
        """
        # Auth endpoints get stricter limits
        if "/auth" in path:
            return self.auth_limit
        return self.default_limit

    def _get_or_create_bucket(self, ip: str, limit: int) -> TokenBucket:
        """
        Get existing bucket or create new one for IP.

        Args:
            ip: Client IP address
            limit: Requests per minute limit

        Returns:
            TokenBucket instance for this IP
        """
        now = time.time()

        # Periodic cleanup of old buckets to prevent memory leak
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_buckets(now)

        if ip in self.buckets:
            bucket, _ = self.buckets[ip]
            # Update last access time
            self.buckets[ip] = (bucket, now)
            return bucket

        # Create new bucket
        # Capacity = limit (burst), refill_rate = limit/60 (per second)
        bucket = TokenBucket(
            capacity=limit,
            refill_rate=limit / 60.0
        )
        self.buckets[ip] = (bucket, now)
        return bucket

    def _cleanup_old_buckets(self, now: float) -> None:
        """
        Remove buckets not accessed in last 10 minutes.

        Prevents memory leak from accumulating IP buckets.

        Args:
            now: Current timestamp
        """
        timeout = 600  # 10 minutes
        old_ips = [
            ip for ip, (_, last_access) in self.buckets.items()
            if now - last_access > timeout
        ]

        for ip in old_ips:
            del self.buckets[ip]

        if old_ips:
            logger.info(
                "Cleaned up old rate limit buckets",
                extra={"count": len(old_ips)}
            )

        self.last_cleanup = now

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request with rate limiting.

        Args:
            request: Incoming FastAPI request
            call_next: Next middleware/route handler

        Returns:
            Response (200 if allowed, 429 if rate limited)
        """
        # Get client IP and rate limit
        client_ip = self._get_client_ip(request)
        path = request.url.path
        limit = self._get_rate_limit(path)

        # Get or create bucket for this IP
        bucket = self._get_or_create_bucket(client_ip, limit)

        # Attempt to consume token
        if not bucket.consume():
            # Rate limit exceeded
            wait_time = bucket.get_wait_time()

            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "path": path,
                    "limit": limit,
                    "wait_time": wait_time,
                    "request_id": getattr(request.state, "request_id", None),
                }
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded",
                    "limit": limit,
                    "window": "1 minute",
                    "retry_after": int(wait_time) + 1,
                },
                headers={
                    "Retry-After": str(int(wait_time) + 1),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                }
            )

        # Add rate limit headers to response
        response = await call_next(request)

        # Calculate remaining tokens
        remaining = int(bucket.tokens)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
