"""
Web Fetch Service for URL Content Extraction.

Provides async HTTP fetching with content extraction for URLs referenced in
persona profiles or Reddit threads. Features:
- Async HTTP client using httpx
- HTML to text extraction via trafilatura
- Content truncation to fit token budgets
- In-memory cache with TTL
- Safety features: timeout, size limits, IP blocking
"""

import asyncio
import ipaddress
import logging
import re
import time
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Try to import trafilatura, provide fallback if not available
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logger.warning("trafilatura not installed, using basic HTML stripping fallback")


class WebFetchService:
    """
    Service for fetching and extracting content from web URLs.

    Features:
    - Async HTTP requests with httpx
    - HTML to readable text extraction
    - Content truncation for token budget compliance
    - In-memory cache with configurable TTL
    - Safety measures: timeout, size limits, private IP blocking

    Usage:
        service = WebFetchService()
        result = await service.fetch_url("https://example.com/article")
        if result["success"]:
            print(result["content"])
    """

    # Default configuration
    DEFAULT_TIMEOUT = 5.0  # seconds
    DEFAULT_MAX_SIZE = 1 * 1024 * 1024  # 1MB
    DEFAULT_MAX_CONTENT_LENGTH = 2000  # characters
    DEFAULT_CACHE_TTL = 900  # 15 minutes
    DEFAULT_USER_AGENT = "BubbleViews-Agent/1.0 (Reddit AI Agent; Content Research)"

    # Blocked hosts and patterns for safety
    BLOCKED_HOSTS: Set[str] = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
    }

    # Private IP ranges to block
    PRIVATE_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_size: int = DEFAULT_MAX_SIZE,
        max_content_length: int = DEFAULT_MAX_CONTENT_LENGTH,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        user_agent: Optional[str] = None,
    ):
        """
        Initialize WebFetchService.

        Args:
            timeout: Request timeout in seconds (default: 5)
            max_size: Maximum response size in bytes (default: 1MB)
            max_content_length: Maximum extracted content length in chars (default: 2000)
            cache_ttl: Cache time-to-live in seconds (default: 900 = 15 minutes)
            user_agent: Custom User-Agent header
        """
        self.timeout = timeout
        self.max_size = max_size
        self.max_content_length = max_content_length
        self.cache_ttl = cache_ttl
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

        # In-memory cache: url -> (result, timestamp)
        self._cache: Dict[str, tuple[Dict[str, Any], float]] = {}

        logger.info(
            "WebFetchService initialized",
            extra={
                "timeout": timeout,
                "max_size": max_size,
                "max_content_length": max_content_length,
                "cache_ttl": cache_ttl,
                "trafilatura_available": TRAFILATURA_AVAILABLE,
            }
        )

    async def fetch_url(self, url: str) -> Dict[str, Any]:
        """
        Fetch and extract readable content from a URL.

        Validates URL safety, fetches content, extracts main text,
        and returns structured result suitable for LLM context.

        Args:
            url: The URL to fetch content from

        Returns:
            Dictionary with:
                - success: bool indicating fetch success
                - url: The original URL
                - title: Extracted page title (if available)
                - content: Extracted readable text (truncated to max_content_length)
                - content_length: Original content length before truncation
                - truncated: bool indicating if content was truncated
                - error: Error message if success is False
                - cached: bool indicating if result was from cache

        Example:
            {
                "success": True,
                "url": "https://example.com/article",
                "title": "Article Title",
                "content": "The main article content...",
                "content_length": 5432,
                "truncated": True,
                "cached": False
            }
        """
        # Check cache first
        cached_result = self._get_cached(url)
        if cached_result:
            logger.debug(f"Cache hit for URL: {url}")
            result = cached_result.copy()
            result["cached"] = True
            return result

        # Validate URL
        validation_error = self._validate_url(url)
        if validation_error:
            logger.warning(f"URL validation failed: {url} - {validation_error}")
            return {
                "success": False,
                "url": url,
                "title": None,
                "content": None,
                "error": validation_error,
                "cached": False,
            }

        try:
            # Fetch content
            html_content = await self._fetch_html(url)

            if html_content is None:
                return {
                    "success": False,
                    "url": url,
                    "title": None,
                    "content": None,
                    "error": "Failed to fetch content",
                    "cached": False,
                }

            # Extract readable content
            title, content = self._extract_content(html_content, url)

            if not content:
                return {
                    "success": False,
                    "url": url,
                    "title": title,
                    "content": None,
                    "error": "No readable content extracted",
                    "cached": False,
                }

            # Truncate if needed
            original_length = len(content)
            truncated = original_length > self.max_content_length
            if truncated:
                content = self._smart_truncate(content, self.max_content_length)

            result = {
                "success": True,
                "url": url,
                "title": title,
                "content": content,
                "content_length": original_length,
                "truncated": truncated,
                "cached": False,
            }

            # Cache the result
            self._set_cached(url, result)

            logger.info(
                f"Successfully fetched URL: {url}",
                extra={
                    "content_length": original_length,
                    "truncated": truncated,
                    "title": title[:50] if title else None,
                }
            )

            return result

        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching URL: {url}")
            return {
                "success": False,
                "url": url,
                "title": None,
                "content": None,
                "error": f"Request timed out after {self.timeout}s",
                "cached": False,
            }

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error for URL: {url} - {e.response.status_code}")
            return {
                "success": False,
                "url": url,
                "title": None,
                "content": None,
                "error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
                "cached": False,
            }

        except Exception as e:
            logger.error(f"Error fetching URL: {url} - {e}", exc_info=True)
            return {
                "success": False,
                "url": url,
                "title": None,
                "content": None,
                "error": f"Fetch error: {str(e)}",
                "cached": False,
            }

    def _validate_url(self, url: str) -> Optional[str]:
        """
        Validate URL for safety.

        Checks:
        - Valid URL format
        - HTTP(S) scheme only
        - Not a private/local IP
        - Not a blocked host

        Args:
            url: URL to validate

        Returns:
            Error message if invalid, None if valid
        """
        try:
            parsed = urlparse(url)
        except Exception:
            return "Invalid URL format"

        # Check scheme
        if parsed.scheme not in ("http", "https"):
            return f"Invalid scheme '{parsed.scheme}', only HTTP(S) allowed"

        # Check for empty host
        if not parsed.netloc:
            return "Missing host in URL"

        # Extract hostname (without port)
        hostname = parsed.hostname
        if not hostname:
            return "Invalid hostname"

        # Check blocked hosts
        hostname_lower = hostname.lower()
        if hostname_lower in self.BLOCKED_HOSTS:
            return f"Host '{hostname}' is blocked"

        # Check for private IP addresses
        try:
            ip = ipaddress.ip_address(hostname)
            for network in self.PRIVATE_RANGES:
                if ip in network:
                    return f"Private IP addresses are blocked"
        except ValueError:
            # Not an IP address, that's fine
            pass

        return None

    async def _fetch_html(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from URL.

        Args:
            url: URL to fetch

        Returns:
            HTML content as string, or None on failure
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            # Check content length
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.max_size:
                logger.warning(
                    f"Content too large: {content_length} bytes (max: {self.max_size})"
                )
                return None

            # Check content type
            content_type = response.headers.get("content-type", "")
            if not any(ct in content_type.lower() for ct in ["text/html", "application/xhtml"]):
                logger.warning(f"Unexpected content type: {content_type}")
                # Still try to process, might work for some formats

            return response.text

    def _extract_content(self, html: str, url: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extract readable content from HTML.

        Uses trafilatura if available, falls back to basic regex stripping.

        Args:
            html: Raw HTML content
            url: Original URL (for trafilatura metadata)

        Returns:
            Tuple of (title, content) - either may be None
        """
        if TRAFILATURA_AVAILABLE:
            return self._extract_with_trafilatura(html, url)
        else:
            return self._extract_with_fallback(html)

    def _extract_with_trafilatura(
        self, html: str, url: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Extract content using trafilatura library.

        Args:
            html: Raw HTML content
            url: Original URL

        Returns:
            Tuple of (title, content)
        """
        try:
            # Extract main content
            content = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_precision=True,
            )

            # Try to extract title from metadata
            metadata = trafilatura.extract_metadata(html, url=url)
            title = metadata.title if metadata else None

            return (title, content)

        except Exception as e:
            logger.warning(f"trafilatura extraction failed: {e}")
            return self._extract_with_fallback(html)

    def _extract_with_fallback(self, html: str) -> tuple[Optional[str], Optional[str]]:
        """
        Basic HTML content extraction fallback.

        Simple regex-based extraction when trafilatura is not available.

        Args:
            html: Raw HTML content

        Returns:
            Tuple of (title, content)
        """
        # Extract title
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else None

        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        content = re.sub(r"<[^>]+>", " ", html)

        # Clean up whitespace
        content = re.sub(r"\s+", " ", content).strip()

        # Decode common HTML entities
        content = content.replace("&nbsp;", " ")
        content = content.replace("&amp;", "&")
        content = content.replace("&lt;", "<")
        content = content.replace("&gt;", ">")
        content = content.replace("&quot;", '"')
        content = content.replace("&#39;", "'")

        return (title, content if content else None)

    def _smart_truncate(self, text: str, max_length: int) -> str:
        """
        Truncate text at a sentence boundary when possible.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text with ellipsis if needed
        """
        if len(text) <= max_length:
            return text

        # Try to find a sentence boundary
        truncated = text[:max_length]

        # Look for sentence endings (.!?) near the end
        for i in range(len(truncated) - 1, max(len(truncated) - 100, 0), -1):
            if truncated[i] in ".!?" and (i + 1 >= len(truncated) or truncated[i + 1] == " "):
                return truncated[:i + 1]

        # No sentence boundary found, truncate at word boundary
        last_space = truncated.rfind(" ")
        if last_space > max_length - 100:
            return truncated[:last_space] + "..."

        return truncated + "..."

    def _get_cached(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get cached result for URL if not expired.

        Args:
            url: URL to look up

        Returns:
            Cached result or None
        """
        if url not in self._cache:
            return None

        result, timestamp = self._cache[url]
        if time.time() - timestamp > self.cache_ttl:
            # Cache expired
            del self._cache[url]
            return None

        return result

    def _set_cached(self, url: str, result: Dict[str, Any]) -> None:
        """
        Cache result for URL.

        Args:
            url: URL key
            result: Result to cache
        """
        self._cache[url] = (result, time.time())

        # Simple cache cleanup: remove old entries if cache grows too large
        if len(self._cache) > 100:
            self._cleanup_cache()

    def _cleanup_cache(self) -> None:
        """Remove expired entries from cache."""
        current_time = time.time()
        expired_urls = [
            url for url, (_, timestamp) in self._cache.items()
            if current_time - timestamp > self.cache_ttl
        ]
        for url in expired_urls:
            del self._cache[url]

    def clear_cache(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.info("WebFetchService cache cleared")
