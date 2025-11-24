"""
Retry Decorator with Exponential Backoff

Provides a decorator for retrying async functions with exponential backoff
and jitter. Designed for handling transient failures in external API calls.

Key features:
- Exponential backoff with configurable base and max delay
- Jitter to prevent thundering herd
- Selective exception catching
- Maximum retry attempts
- Detailed logging of retry attempts
"""

import asyncio
import functools
import logging
import random
from typing import Callable, Type, Tuple, Any

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator for retrying async functions with exponential backoff.

    Retries failed async function calls using exponential backoff with
    optional jitter. Catches specified exceptions and retries up to max_retries times.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
            Does not include the initial attempt
            Total attempts = max_retries + 1
        base_delay: Initial delay in seconds (default: 1.0)
            First retry waits base_delay seconds
        max_delay: Maximum delay in seconds (default: 60.0)
            Caps delay to prevent excessive waits
        exponential_base: Base for exponential growth (default: 2.0)
            Delay formula: base_delay * (exponential_base ** attempt)
        jitter: Whether to add random jitter (default: True)
            Jitter range: ±20% of calculated delay
        exceptions: Tuple of exceptions to catch (default: (Exception,))
            Only these exceptions trigger retries

    Returns:
        Decorated async function that retries on failure

    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        async def fetch_data():
            response = await api_call()
            return response

    Note:
        - Delays: 1s, 2s, 4s (with exponential_base=2.0)
        - Jitter prevents synchronized retries across clients
        - Non-matching exceptions propagate immediately
        - Logs each retry attempt at INFO level
        - Final failure logged at ERROR level
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    # Don't retry on last attempt
                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}",
                            exc_info=True
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    # Add jitter if enabled (±20%)
                    if jitter:
                        jitter_amount = delay * 0.2
                        delay = delay + random.uniform(-jitter_amount, jitter_amount)
                        delay = max(0.0, delay)  # Ensure non-negative

                    logger.info(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} "
                        f"failed with {type(e).__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    await asyncio.sleep(delay)

            # Should never reach here due to raise in loop
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def retry_on_rate_limit(
    max_retries: int = 5,
    base_delay: float = 60.0
):
    """
    Specialized retry decorator for rate limit errors.

    Retries with longer delays specifically for rate limit responses.
    Used for 429 (Too Many Requests) errors.

    Args:
        max_retries: Maximum retry attempts (default: 5)
        base_delay: Initial delay in seconds (default: 60.0)
            Reddit rate limits typically last 60+ seconds

    Returns:
        Decorated async function

    Note:
        - Uses fixed delays (no exponential growth)
        - No jitter (rate limits are time-based, not load-based)
        - Longer base delay than standard retries
        - Logs rate limit incidents
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except Exception as e:
                    # Check if it's a rate limit error
                    is_rate_limit = (
                        isinstance(e, PermissionError) and "rate limit" in str(e).lower()
                    ) or (
                        hasattr(e, 'response') and
                        getattr(e.response, 'status_code', None) == 429
                    )

                    if not is_rate_limit:
                        raise

                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} rate limited after {max_retries + 1} attempts"
                        )
                        raise

                    delay = base_delay

                    logger.warning(
                        f"{func.__name__} rate limited (attempt {attempt + 1}/"
                        f"{max_retries + 1}). Waiting {delay:.0f}s..."
                    )

                    await asyncio.sleep(delay)

            raise Exception("Unexpected: retry loop exited without return or raise")

        return wrapper
    return decorator
