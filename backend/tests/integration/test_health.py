"""
Integration tests for health check endpoints.

Tests the complete health check system with real dependencies:
- /health endpoint (liveness probe)
- /health/ready endpoint (readiness probe with DB and OpenRouter checks)
- /health/agent endpoint (agent status stub)

Tests follow AAA (Arrange, Act, Assert) pattern.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
class TestHealthEndpointIntegration:
    """Integration tests for /health liveness probe."""

    async def test_health_returns_200(self):
        """
        Test that /health endpoint returns 200 status.

        Arrange: None needed - endpoint should always work
        Act: GET /health
        Assert: Status 200, response has status and timestamp
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    async def test_health_returns_valid_timestamp(self):
        """
        Test that /health returns valid ISO timestamp.

        Arrange: None needed
        Act: GET /health
        Assert: Timestamp is valid ISO 8601 format
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        # Should be able to parse timestamp
        timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)

    async def test_health_response_schema(self):
        """
        Test that /health response matches schema.

        Arrange: None needed
        Act: GET /health
        Assert: Response has required fields with correct types
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["status"], str)
        assert isinstance(data["timestamp"], str)
        assert data["status"] == "ok"

    async def test_health_includes_request_id(self):
        """
        Test that /health includes X-Request-ID header.

        Arrange: None needed
        Act: GET /health
        Assert: Response has X-Request-ID header
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health")

        # Assert
        assert response.status_code == 200
        assert "x-request-id" in response.headers


@pytest.mark.asyncio
class TestReadinessEndpointIntegration:
    """Integration tests for /health/ready readiness probe."""

    @patch('app.api.v1.health.check_database')
    @patch('app.api.v1.health.check_openrouter')
    async def test_ready_all_checks_pass(self, mock_openrouter, mock_db):
        """
        Test /health/ready when all dependencies are healthy.

        Arrange: Mock all probes to return True
        Act: GET /health/ready
        Assert: Status 200, overall status "ready", all checks healthy
        """
        # Arrange
        mock_db.return_value = AsyncMock(return_value=True)()
        mock_openrouter.return_value = AsyncMock(return_value=True)()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/ready")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["db"]["healthy"] is True
        assert data["checks"]["openrouter"]["healthy"] is True
        assert "timestamp" in data

    @patch('app.api.v1.health.check_database')
    @patch('app.api.v1.health.check_openrouter')
    async def test_ready_db_fails(self, mock_openrouter, mock_db):
        """
        Test /health/ready when database check fails.

        Arrange: Mock DB probe to return False, OpenRouter to return True
        Act: GET /health/ready
        Assert: Status 503, overall status "not_ready", DB check failed
        """
        # Arrange
        mock_db.return_value = AsyncMock(return_value=False)()
        mock_openrouter.return_value = AsyncMock(return_value=True)()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/ready")

        # Assert
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["db"]["healthy"] is False
        assert data["checks"]["openrouter"]["healthy"] is True
        assert data["checks"]["db"]["error"] is not None

    @patch('app.api.v1.health.check_database')
    @patch('app.api.v1.health.check_openrouter')
    async def test_ready_openrouter_fails(self, mock_openrouter, mock_db):
        """
        Test /health/ready when OpenRouter check fails.

        Arrange: Mock OpenRouter probe to return False, DB to return True
        Act: GET /health/ready
        Assert: Status 503, overall status "not_ready", OpenRouter check failed
        """
        # Arrange
        mock_db.return_value = AsyncMock(return_value=True)()
        mock_openrouter.return_value = AsyncMock(return_value=False)()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/ready")

        # Assert
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["db"]["healthy"] is True
        assert data["checks"]["openrouter"]["healthy"] is False
        assert data["checks"]["openrouter"]["error"] is not None

    @patch('app.api.v1.health.check_database')
    @patch('app.api.v1.health.check_openrouter')
    async def test_ready_all_checks_fail(self, mock_openrouter, mock_db):
        """
        Test /health/ready when all dependencies fail.

        Arrange: Mock all probes to return False
        Act: GET /health/ready
        Assert: Status 503, overall status "not_ready", all checks failed
        """
        # Arrange
        mock_db.return_value = AsyncMock(return_value=False)()
        mock_openrouter.return_value = AsyncMock(return_value=False)()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/ready")

        # Assert
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["db"]["healthy"] is False
        assert data["checks"]["openrouter"]["healthy"] is False

    @patch('app.api.v1.health.check_database')
    @patch('app.api.v1.health.check_openrouter')
    async def test_ready_includes_latency(self, mock_openrouter, mock_db):
        """
        Test that /health/ready includes latency measurements.

        Arrange: Mock all probes to return True
        Act: GET /health/ready
        Assert: All checks have latency_ms field
        """
        # Arrange
        mock_db.return_value = AsyncMock(return_value=True)()
        mock_openrouter.return_value = AsyncMock(return_value=True)()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/ready")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "latency_ms" in data["checks"]["db"]
        assert "latency_ms" in data["checks"]["openrouter"]
        assert isinstance(data["checks"]["db"]["latency_ms"], (int, float))
        assert isinstance(data["checks"]["openrouter"]["latency_ms"], (int, float))


@pytest.mark.asyncio
class TestAgentStatusEndpointIntegration:
    """Integration tests for /health/agent status endpoint."""

    async def test_agent_status_returns_200(self):
        """
        Test that /health/agent endpoint returns 200 status.

        Arrange: None needed - stub endpoint
        Act: GET /health/agent
        Assert: Status 200
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/agent")

        # Assert
        assert response.status_code == 200

    async def test_agent_status_stub_response(self):
        """
        Test that /health/agent returns stub response.

        Arrange: None needed
        Act: GET /health/agent
        Assert: Status is "not_started", last_activity is None
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/agent")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_started"
        assert data["last_activity"] is None

    async def test_agent_status_response_schema(self):
        """
        Test that /health/agent response matches schema.

        Arrange: None needed
        Act: GET /health/agent
        Assert: Response has required fields
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/agent")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "last_activity" in data
        assert isinstance(data["status"], str)

    async def test_agent_status_includes_request_id(self):
        """
        Test that /health/agent includes request correlation ID.

        Arrange: None needed
        Act: GET /health/agent
        Assert: Response has X-Request-ID header
        """
        # Arrange
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Act
            response = await client.get("/api/v1/health/agent")

        # Assert
        assert response.status_code == 200
        assert "x-request-id" in response.headers
