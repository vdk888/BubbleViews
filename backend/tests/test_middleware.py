"""
Tests for middleware components.

This module tests:
- RequestIDMiddleware (correlation ID tracking)
- LoggingMiddleware (request/response logging)

Tests follow AAA (Arrange, Act, Assert) pattern.
"""

import pytest
import json
import uuid
from unittest.mock import patch, MagicMock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.request_id import RequestIDMiddleware
from app.middleware.logging import LoggingMiddleware


class TestRequestIDMiddleware:
    """Tests for request ID correlation middleware."""

    def test_request_id_generated_when_missing(self):
        """
        Test that request ID is generated when not provided.

        Arrange: FastAPI app with RequestIDMiddleware
        Act: Make request without X-Request-ID header
        Assert: Response has X-Request-ID header with valid UUID
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint(request: Request):
            return {"request_id": request.state.request_id}

        client = TestClient(app)

        # Act
        response = client.get("/test")

        # Assert
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]

        # Should be valid UUID
        try:
            uuid.UUID(request_id)
            assert True
        except ValueError:
            pytest.fail("Request ID is not a valid UUID")

        # Should match value in response body
        assert response.json()["request_id"] == request_id

    def test_request_id_preserved_from_header(self):
        """
        Test that existing request ID is preserved.

        Arrange: FastAPI app with RequestIDMiddleware
        Act: Make request with X-Request-ID header
        Assert: Same request ID is returned in response
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint(request: Request):
            return {"request_id": request.state.request_id}

        client = TestClient(app)
        custom_request_id = "custom-request-id-123"

        # Act
        response = client.get(
            "/test",
            headers={"X-Request-ID": custom_request_id}
        )

        # Assert
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_request_id
        assert response.json()["request_id"] == custom_request_id

    def test_request_id_available_in_request_state(self):
        """
        Test that request ID is accessible via request.state.

        Arrange: FastAPI app with RequestIDMiddleware
        Act: Make request and access request.state.request_id in handler
        Assert: request_id is available and matches response header
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        captured_request_id = None

        @app.get("/test")
        async def test_endpoint(request: Request):
            nonlocal captured_request_id
            captured_request_id = request.state.request_id
            return {"ok": True}

        client = TestClient(app)

        # Act
        response = client.get("/test")

        # Assert
        assert response.status_code == 200
        assert captured_request_id is not None
        assert response.headers["X-Request-ID"] == captured_request_id

    def test_request_id_different_per_request(self):
        """
        Test that each request gets unique request ID.

        Arrange: FastAPI app with RequestIDMiddleware
        Act: Make multiple requests without X-Request-ID header
        Assert: Each request gets different request ID
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        # Act
        response1 = client.get("/test")
        response2 = client.get("/test")
        response3 = client.get("/test")

        # Assert
        request_id_1 = response1.headers["X-Request-ID"]
        request_id_2 = response2.headers["X-Request-ID"]
        request_id_3 = response3.headers["X-Request-ID"]

        assert request_id_1 != request_id_2
        assert request_id_2 != request_id_3
        assert request_id_1 != request_id_3


class TestLoggingMiddleware:
    """Tests for request/response logging middleware."""

    def test_logging_middleware_logs_request(self):
        """
        Test that logging middleware logs request details.

        Arrange: FastAPI app with both middleware, mock logger
        Act: Make request
        Assert: Logger called with request details
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        with patch('app.middleware.logging.logger') as mock_logger:
            # Act
            response = client.get("/test?param=value")

            # Assert
            assert response.status_code == 200
            # Should log request start and completion
            assert mock_logger.info.call_count >= 2

            # Check that request_id was included in logs
            calls = mock_logger.info.call_args_list
            # At least one call should include request details
            assert any("Request started" in str(call) for call in calls)
            assert any("Request completed" in str(call) for call in calls)

    def test_logging_middleware_logs_response_status(self):
        """
        Test that logging middleware logs response status.

        Arrange: FastAPI app with middleware, mock logger
        Act: Make request
        Assert: Logger called with status code
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        with patch('app.middleware.logging.logger') as mock_logger:
            # Act
            response = client.get("/test")

            # Assert
            assert response.status_code == 200

            # Find completion log call
            completion_calls = [
                call for call in mock_logger.info.call_args_list
                if "Request completed" in str(call)
            ]
            assert len(completion_calls) > 0

            # Check that status_code was logged
            completion_call = completion_calls[0]
            extra = completion_call.kwargs.get('extra', {})
            assert extra.get('status_code') == 200

    def test_logging_middleware_logs_latency(self):
        """
        Test that logging middleware logs request latency.

        Arrange: FastAPI app with middleware, mock logger
        Act: Make request
        Assert: Logger called with latency_ms
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        with patch('app.middleware.logging.logger') as mock_logger:
            # Act
            response = client.get("/test")

            # Assert
            assert response.status_code == 200

            # Find completion log call
            completion_calls = [
                call for call in mock_logger.info.call_args_list
                if "Request completed" in str(call)
            ]
            assert len(completion_calls) > 0

            # Check that latency_ms was logged
            completion_call = completion_calls[0]
            extra = completion_call.kwargs.get('extra', {})
            assert 'latency_ms' in extra
            assert isinstance(extra['latency_ms'], (int, float))
            assert extra['latency_ms'] >= 0

    def test_logging_middleware_logs_exceptions(self):
        """
        Test that logging middleware logs exceptions.

        Arrange: FastAPI app with middleware, endpoint that raises exception
        Act: Make request that triggers exception
        Assert: Logger called with exception details
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            raise ValueError("Test exception")

        client = TestClient(app)

        with patch('app.middleware.logging.logger') as mock_logger:
            # Act
            try:
                response = client.get("/test")
            except Exception:
                pass  # Exception expected

            # Assert
            # Should log error
            assert mock_logger.error.call_count > 0

            # Check that exception was logged
            error_calls = mock_logger.error.call_args_list
            assert len(error_calls) > 0
            error_call = error_calls[0]
            assert "Request failed" in str(error_call)

    def test_logging_middleware_includes_request_id(self):
        """
        Test that logging middleware includes request ID.

        Arrange: FastAPI app with both middleware, mock logger
        Act: Make request with custom request ID
        Assert: Logger called with same request ID
        """
        # Arrange
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)
        custom_request_id = "test-request-id-456"

        with patch('app.middleware.logging.logger') as mock_logger:
            # Act
            response = client.get(
                "/test",
                headers={"X-Request-ID": custom_request_id}
            )

            # Assert
            assert response.status_code == 200

            # Check that request_id was included in logs
            completion_calls = [
                call for call in mock_logger.info.call_args_list
                if "Request completed" in str(call)
            ]
            assert len(completion_calls) > 0

            completion_call = completion_calls[0]
            extra = completion_call.kwargs.get('extra', {})
            assert extra.get('request_id') == custom_request_id
