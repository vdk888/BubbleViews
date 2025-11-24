"""
Integration tests for logging system.

Tests the complete logging infrastructure:
- Structured JSON logging format
- Request ID propagation
- Log fields presence (timestamp, level, path, status_code, latency_ms)
- Request ID matching between log and response header

Tests follow AAA (Arrange, Act, Assert) pattern.
"""

import pytest
import json
import logging
from io import StringIO
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
class TestStructuredLogging:
    """Integration tests for structured JSON logging."""

    async def test_request_produces_json_log(self, caplog):
        """
        Test that a request produces a structured JSON log entry.

        Arrange: Set up log capture with JSON level
        Act: Make a request to /health
        Assert: Log output contains valid JSON
        """
        # Arrange
        caplog.set_level(logging.INFO)

        # Act
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200

        # Find JSON log entries
        json_logs = []
        for record in caplog.records:
            try:
                # Try to parse message as JSON
                log_data = json.loads(record.message)
                json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                # Not a JSON log, skip
                continue

        # Should have at least one JSON log entry
        assert len(json_logs) > 0, "No JSON log entries found"

    async def test_log_contains_required_fields(self, caplog):
        """
        Test that log entry contains all required fields.

        Arrange: Set up log capture
        Act: Make a request to /health
        Assert: Log has timestamp, level, path, status_code, latency_ms
        """
        # Arrange
        caplog.set_level(logging.INFO)

        # Act
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200

        # Find the request log entry
        json_logs = []
        for record in caplog.records:
            try:
                log_data = json.loads(record.message)
                # Look for logs with path field (request logs)
                if "path" in log_data:
                    json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                continue

        assert len(json_logs) > 0, "No request log entries found"

        # Check first request log entry
        log_entry = json_logs[0]

        # Verify required fields
        assert "timestamp" in log_entry, "Log missing timestamp"
        assert "level" in log_entry, "Log missing level"
        assert "path" in log_entry, "Log missing path"
        assert "status_code" in log_entry, "Log missing status_code"
        assert "latency_ms" in log_entry, "Log missing latency_ms"

        # Verify field types
        assert isinstance(log_entry["timestamp"], str)
        assert isinstance(log_entry["level"], str)
        assert isinstance(log_entry["path"], str)
        assert isinstance(log_entry["status_code"], int)
        assert isinstance(log_entry["latency_ms"], (int, float))

    async def test_log_contains_request_id(self, caplog):
        """
        Test that log entry contains request_id.

        Arrange: Set up log capture
        Act: Make a request to /health
        Assert: Log has request_id field
        """
        # Arrange
        caplog.set_level(logging.INFO)

        # Act
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200

        # Find the request log entry
        json_logs = []
        for record in caplog.records:
            try:
                log_data = json.loads(record.message)
                if "path" in log_data:
                    json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                continue

        assert len(json_logs) > 0, "No request log entries found"

        # Check request_id is present
        log_entry = json_logs[0]
        assert "request_id" in log_entry, "Log missing request_id"
        assert isinstance(log_entry["request_id"], str)
        assert len(log_entry["request_id"]) > 0

    async def test_request_id_matches_header(self, caplog):
        """
        Test that request_id in log matches X-Request-ID header in response.

        Arrange: Set up log capture
        Act: Make a request to /health
        Assert: Log request_id matches response header
        """
        # Arrange
        caplog.set_level(logging.INFO)

        # Act
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200
        assert "x-request-id" in response.headers

        response_request_id = response.headers["x-request-id"]

        # Find the request log entry
        json_logs = []
        for record in caplog.records:
            try:
                log_data = json.loads(record.message)
                if "path" in log_data and "request_id" in log_data:
                    json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                continue

        assert len(json_logs) > 0, "No request log entries found"

        # Check request_id matches
        log_entry = json_logs[0]
        log_request_id = log_entry["request_id"]

        assert log_request_id == response_request_id, \
            f"Request ID mismatch: log={log_request_id}, header={response_request_id}"

    async def test_custom_request_id_propagated(self, caplog):
        """
        Test that custom request ID is propagated through system.

        Arrange: Set up log capture
        Act: Make a request with custom X-Request-ID header
        Assert: Same request ID appears in log and response
        """
        # Arrange
        caplog.set_level(logging.INFO)
        custom_request_id = "test-request-12345"

        # Act
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/health",
                headers={"X-Request-ID": custom_request_id}
            )

        # Assert
        assert response.status_code == 200
        assert response.headers["x-request-id"] == custom_request_id

        # Find the request log entry
        json_logs = []
        for record in caplog.records:
            try:
                log_data = json.loads(record.message)
                if "path" in log_data and "request_id" in log_data:
                    json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                continue

        assert len(json_logs) > 0, "No request log entries found"

        # Check request_id matches custom value
        log_entry = json_logs[0]
        assert log_entry["request_id"] == custom_request_id

    async def test_log_captures_path_correctly(self, caplog):
        """
        Test that log captures request path correctly.

        Arrange: Set up log capture
        Act: Make requests to different endpoints
        Assert: Logs contain correct paths
        """
        # Arrange
        caplog.set_level(logging.INFO)

        # Act - Make requests to different endpoints
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health_response = await client.get("/api/v1/health")
            agent_response = await client.get("/api/v1/health/agent")

        # Assert
        assert health_response.status_code == 200
        assert agent_response.status_code == 200

        # Find all request log entries
        json_logs = []
        for record in caplog.records:
            try:
                log_data = json.loads(record.message)
                if "path" in log_data:
                    json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                continue

        # Should have logs for both requests
        paths = [log["path"] for log in json_logs]
        assert "/api/v1/health" in paths
        assert "/api/v1/health/agent" in paths

    async def test_log_captures_status_codes(self, caplog):
        """
        Test that log captures HTTP status codes correctly.

        Arrange: Set up log capture
        Act: Make requests that return different status codes
        Assert: Logs contain correct status codes
        """
        # Arrange
        caplog.set_level(logging.INFO)

        # Act - Make successful and failed requests
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Success
            success_response = await client.get("/api/v1/health")
            # Not found
            notfound_response = await client.get("/api/v1/nonexistent")

        # Assert
        assert success_response.status_code == 200
        assert notfound_response.status_code == 404

        # Find all request log entries
        json_logs = []
        for record in caplog.records:
            try:
                log_data = json.loads(record.message)
                if "status_code" in log_data:
                    json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                continue

        # Check status codes are logged
        status_codes = [log["status_code"] for log in json_logs]
        assert 200 in status_codes
        assert 404 in status_codes

    async def test_latency_is_reasonable(self, caplog):
        """
        Test that logged latency values are reasonable.

        Arrange: Set up log capture
        Act: Make a request
        Assert: Latency is positive and within reasonable bounds
        """
        # Arrange
        caplog.set_level(logging.INFO)

        # Act
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200

        # Find the request log entry
        json_logs = []
        for record in caplog.records:
            try:
                log_data = json.loads(record.message)
                if "latency_ms" in log_data:
                    json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                continue

        assert len(json_logs) > 0, "No request log entries found"

        # Check latency is reasonable
        log_entry = json_logs[0]
        latency = log_entry["latency_ms"]

        # Latency should be positive and less than 1 second for simple health check
        assert latency > 0, "Latency should be positive"
        assert latency < 1000, f"Latency seems too high: {latency}ms"


@pytest.mark.asyncio
class TestLoggingWithAuth:
    """Integration tests for logging with authentication endpoints."""

    async def test_auth_endpoint_logging(self, caplog):
        """
        Test that authentication endpoints produce proper logs.

        Arrange: Set up log capture
        Act: Make request to auth endpoint
        Assert: Log entry is created with correct path
        """
        # Arrange
        caplog.set_level(logging.INFO)

        # Act
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/token",
                data={"username": "test", "password": "test"}
            )

        # Assert - Will fail auth, but should log
        assert response.status_code in [401, 422]

        # Find the request log entry
        json_logs = []
        for record in caplog.records:
            try:
                log_data = json.loads(record.message)
                if "path" in log_data and "/auth/token" in log_data["path"]:
                    json_logs.append(log_data)
            except (json.JSONDecodeError, ValueError):
                continue

        assert len(json_logs) > 0, "No auth request log entries found"

        # Verify log structure
        log_entry = json_logs[0]
        assert "request_id" in log_entry
        assert "status_code" in log_entry
        assert "latency_ms" in log_entry
