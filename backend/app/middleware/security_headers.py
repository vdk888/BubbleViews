"""
Security headers middleware for protection against common web vulnerabilities.

This middleware adds HTTP security headers to all responses to protect against:
- XSS (Cross-Site Scripting) attacks
- Clickjacking attacks
- MIME-type sniffing vulnerabilities
- Drive-by downloads
- Content injection

Headers implemented (OWASP recommendations):
- X-Content-Type-Options: Prevents MIME-type sniffing
- X-Frame-Options: Prevents clickjacking (legacy, use CSP frame-ancestors)
- X-XSS-Protection: Legacy XSS protection (browsers now use CSP)
- Content-Security-Policy: Modern protection against XSS and data injection

References:
- OWASP Secure Headers Project: https://owasp.org/www-project-secure-headers/
- OWASP Security Headers: https://owasp.org/www-community/Security_Headers
- CSP Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html

Note: CSP frame-ancestors obsoletes X-Frame-Options in modern browsers.
We include both for backwards compatibility during MVP phase.
"""

from typing import Callable
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all HTTP responses.

    These headers protect against common web vulnerabilities per OWASP guidelines.

    Security Headers Added:
    1. X-Content-Type-Options: nosniff
       - Prevents browsers from MIME-sniffing responses
       - Stops browsers from interpreting files as different type than declared

    2. X-Frame-Options: DENY
       - Prevents page from being embedded in iframe/frame/embed/object
       - Protects against clickjacking attacks
       - Note: Obsoleted by CSP frame-ancestors but kept for legacy browser support

    3. X-XSS-Protection: 1; mode=block
       - Legacy XSS filter for older browsers
       - Modern browsers use CSP instead
       - Kept for backwards compatibility

    4. Content-Security-Policy (CSP)
       - Modern defense against XSS and data injection
       - Controls what resources browser can load
       - frame-ancestors 'none': Prevents embedding (replaces X-Frame-Options)
       - default-src 'self': Only load resources from same origin by default

    Example:
        app.add_middleware(SecurityHeadersMiddleware)

    For Production:
        Consider customizing CSP policy based on your needs:
        - Add 'unsafe-inline' for inline scripts (not recommended)
        - Whitelist specific domains for external resources
        - Add report-uri for CSP violation reporting
        - Use Content-Security-Policy-Report-Only for testing

    MVP Relaxations:
        Current CSP is relaxed for development:
        - Allows 'unsafe-inline' for ease of development
        - Allows 'unsafe-eval' for framework compatibility
        - Should be tightened for production deployment
    """

    def __init__(
        self,
        app,
        enable_csp: bool = True,
        csp_policy: str | None = None,
    ):
        """
        Initialize security headers middleware.

        Args:
            app: FastAPI application instance
            enable_csp: Whether to include Content-Security-Policy header
            csp_policy: Custom CSP policy (if None, uses default relaxed policy)
        """
        super().__init__(app)
        self.enable_csp = enable_csp

        # Default CSP policy (relaxed for MVP, should tighten for production)
        # References:
        # - https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html
        # - https://owasp.org/www-community/controls/Content_Security_Policy
        if csp_policy:
            self.csp_policy = csp_policy
        else:
            # MVP policy: Relaxed but still provides protection
            # Production should remove 'unsafe-inline' and 'unsafe-eval'
            self.csp_policy = (
                "default-src 'self'; "  # Only load resources from same origin
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Allow inline scripts (MVP only)
                "style-src 'self' 'unsafe-inline'; "  # Allow inline styles
                "img-src 'self' data: https:; "  # Allow images from self, data URIs, and HTTPS
                "font-src 'self' data:; "  # Allow fonts from self and data URIs
                "connect-src 'self'; "  # API calls only to same origin
                "frame-ancestors 'none'; "  # Prevent embedding (replaces X-Frame-Options)
                "form-action 'self'; "  # Forms can only submit to same origin
                "base-uri 'self'; "  # Restrict <base> tag to prevent injection
                "object-src 'none'; "  # Block Flash, Java, etc.
                "upgrade-insecure-requests"  # Upgrade HTTP to HTTPS requests
            )

        logger.info(
            "Security headers middleware initialized",
            extra={
                "enable_csp": enable_csp,
                "csp_policy_length": len(self.csp_policy),
            }
        )

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request and add security headers to response.

        Args:
            request: Incoming FastAPI request
            call_next: Next middleware/route handler

        Returns:
            Response with security headers added
        """
        # Process request through route handlers
        response = await call_next(request)

        # Add security headers to response

        # 1. X-Content-Type-Options: Prevents MIME-type sniffing
        # Browser must respect Content-Type header (e.g., don't execute text/plain as JS)
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 2. X-Frame-Options: Prevents clickjacking (legacy)
        # DENY: Page cannot be displayed in iframe/frame/embed/object
        # Note: CSP frame-ancestors 'none' is modern replacement
        response.headers["X-Frame-Options"] = "DENY"

        # 3. X-XSS-Protection: Legacy XSS filter (legacy)
        # 1; mode=block: Enable filter and block page if attack detected
        # Modern browsers use CSP instead, but keep for older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 4. Content-Security-Policy: Modern XSS/injection protection
        # Controls what resources browser can load/execute
        # frame-ancestors 'none': Modern clickjacking protection
        if self.enable_csp:
            response.headers["Content-Security-Policy"] = self.csp_policy

        # 5. Referrer-Policy: Control referrer information (optional but recommended)
        # strict-origin-when-cross-origin: Send full URL for same-origin, origin only for cross-origin
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 6. Permissions-Policy: Control browser features (optional but recommended)
        # Disable features not needed by application
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        return response


class StrictSecurityHeadersMiddleware(SecurityHeadersMiddleware):
    """
    Strict security headers for production deployment.

    Removes unsafe-inline and unsafe-eval from CSP.
    Use this after you've refactored code to not need inline scripts.

    Example:
        app.add_middleware(StrictSecurityHeadersMiddleware)
    """

    def __init__(self, app):
        """Initialize with strict CSP policy."""
        strict_csp = (
            "default-src 'self'; "
            "script-src 'self'; "  # No inline scripts
            "style-src 'self'; "  # No inline styles
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "upgrade-insecure-requests"
        )
        super().__init__(app, enable_csp=True, csp_policy=strict_csp)
        logger.info("Strict security headers middleware initialized (production mode)")
