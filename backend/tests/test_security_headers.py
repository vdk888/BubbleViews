"""
Tests for security headers middleware.

Validates OWASP-recommended security headers are present in responses.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.security_headers import (
    SecurityHeadersMiddleware,
    StrictSecurityHeadersMiddleware
)


class TestSecurityHeaders:
    """Integration tests for security headers middleware."""

    @pytest.fixture
    def app_with_security_headers(self):
        """Create test app with security headers middleware."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        return app

    def test_x_content_type_options_header(self, app_with_security_headers):
        """Test X-Content-Type-Options header is present."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")

        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options_header(self, app_with_security_headers):
        """Test X-Frame-Options header is present."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")

        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection_header(self, app_with_security_headers):
        """Test X-XSS-Protection header is present."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")

        assert "X-XSS-Protection" in response.headers
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_content_security_policy_header(self, app_with_security_headers):
        """Test Content-Security-Policy header is present."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")

        assert "Content-Security-Policy" in response.headers
        csp = response.headers["Content-Security-Policy"]

        # Verify key CSP directives
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp
        assert "form-action 'self'" in csp

    def test_referrer_policy_header(self, app_with_security_headers):
        """Test Referrer-Policy header is present."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")

        assert "Referrer-Policy" in response.headers
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy_header(self, app_with_security_headers):
        """Test Permissions-Policy header is present."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")

        assert "Permissions-Policy" in response.headers
        permissions = response.headers["Permissions-Policy"]

        # Verify key permissions are disabled
        assert "geolocation=()" in permissions
        assert "microphone=()" in permissions
        assert "camera=()" in permissions

    def test_all_security_headers_present(self, app_with_security_headers):
        """Test all security headers are present in single response."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")

        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Content-Security-Policy",
            "Referrer-Policy",
            "Permissions-Policy"
        ]

        for header in required_headers:
            assert header in response.headers, f"Missing security header: {header}"

    def test_security_headers_on_all_endpoints(self, app_with_security_headers):
        """Test security headers are added to all routes."""
        app = app_with_security_headers

        @app.get("/another-endpoint")
        async def another_endpoint():
            return {"data": "test"}

        client = TestClient(app)

        # Test multiple endpoints
        for path in ["/test", "/another-endpoint"]:
            response = client.get(path)
            assert "X-Content-Type-Options" in response.headers
            assert "Content-Security-Policy" in response.headers

    def test_security_headers_on_error_responses(self, app_with_security_headers):
        """Test security headers are present even on handled error responses."""
        from fastapi import HTTPException
        app = app_with_security_headers

        @app.get("/error")
        async def error_endpoint():
            # Use HTTPException which is handled by middleware
            raise HTTPException(status_code=400, detail="Bad request")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")

        # Even on error responses, security headers should be present
        assert response.status_code == 400
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers


class TestCustomCSPPolicy:
    """Test custom CSP policy configuration."""

    def test_custom_csp_policy(self):
        """Test middleware with custom CSP policy."""
        app = FastAPI()

        custom_csp = "default-src 'none'; script-src 'self';"
        app.add_middleware(
            SecurityHeadersMiddleware,
            enable_csp=True,
            csp_policy=custom_csp
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)
        response = client.get("/test")

        assert "Content-Security-Policy" in response.headers
        assert response.headers["Content-Security-Policy"] == custom_csp

    def test_disable_csp(self):
        """Test CSP can be disabled."""
        app = FastAPI()
        app.add_middleware(
            SecurityHeadersMiddleware,
            enable_csp=False
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)
        response = client.get("/test")

        # CSP should not be present when disabled
        assert "Content-Security-Policy" not in response.headers

        # Other headers should still be present
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers


class TestStrictSecurityHeaders:
    """Test strict security headers for production."""

    @pytest.fixture
    def app_with_strict_headers(self):
        """Create app with strict security headers."""
        app = FastAPI()
        app.add_middleware(StrictSecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        return app

    def test_strict_csp_no_unsafe_inline(self, app_with_strict_headers):
        """Test strict CSP disallows unsafe-inline."""
        client = TestClient(app_with_strict_headers)
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]

        # Strict policy should NOT contain unsafe-inline or unsafe-eval
        assert "unsafe-inline" not in csp
        assert "unsafe-eval" not in csp

        # Should still have core directives
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_strict_headers_all_present(self, app_with_strict_headers):
        """Test all security headers present in strict mode."""
        client = TestClient(app_with_strict_headers)
        response = client.get("/test")

        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Content-Security-Policy",
            "Referrer-Policy",
            "Permissions-Policy"
        ]

        for header in required_headers:
            assert header in response.headers


class TestSecurityHeadersCompliance:
    """Test compliance with OWASP recommendations."""

    def test_owasp_secure_headers_compliance(self):
        """
        Test compliance with OWASP Secure Headers Project.

        Reference: https://owasp.org/www-project-secure-headers/
        """
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)
        response = client.get("/test")

        # OWASP recommended headers
        owasp_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": lambda v: "frame-ancestors" in v,
            "Referrer-Policy": lambda v: v in [
                "no-referrer",
                "strict-origin",
                "strict-origin-when-cross-origin"
            ]
        }

        for header, expected in owasp_headers.items():
            assert header in response.headers
            if callable(expected):
                assert expected(response.headers[header])
            else:
                assert response.headers[header] == expected

    def test_clickjacking_protection(self):
        """Test protection against clickjacking attacks."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)
        response = client.get("/test")

        # Both legacy and modern clickjacking protection should be present
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]

    def test_xss_protection_headers(self):
        """Test XSS protection headers are configured correctly."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)
        response = client.get("/test")

        # Multiple layers of XSS protection
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "Content-Security-Policy" in response.headers

        # CSP should restrict script sources
        csp = response.headers["Content-Security-Policy"]
        assert "script-src" in csp

    def test_mime_sniffing_protection(self):
        """Test MIME-type sniffing protection."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)
        response = client.get("/test")

        # Prevents browser from interpreting files as different MIME type
        assert response.headers["X-Content-Type-Options"] == "nosniff"
