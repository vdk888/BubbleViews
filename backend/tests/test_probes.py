"""
Tests for health probe functions.

This module tests:
- check_database() probe
- check_openrouter() probe

Tests follow AAA (Arrange, Act, Assert) pattern with mocks for external dependencies.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.probes import check_database, check_openrouter


class TestDatabaseProbe:
    """Tests for database readiness probe."""

    @pytest.mark.asyncio
    async def test_check_database_success(self):
        """
        Test check_database returns True when DB is healthy.

        Arrange: Mock async_session_maker to return working session
        Act: Call check_database()
        Assert: Returns True
        """
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch('app.core.probes.async_session_maker') as mock_maker:
            mock_maker.return_value = mock_session

            # Act
            result = await check_database()

            # Assert
            assert result is True
            mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_database_connection_error(self):
        """
        Test check_database returns False when DB connection fails.

        Arrange: Mock async_session_maker to raise exception
        Act: Call check_database()
        Assert: Returns False (exception caught gracefully)
        """
        # Arrange
        with patch('app.core.probes.async_session_maker') as mock_maker:
            mock_maker.side_effect = Exception("Connection failed")

            # Act
            result = await check_database()

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_check_database_timeout(self):
        """
        Test check_database returns False on timeout.

        Arrange: Mock async_session_maker to hang indefinitely
        Act: Call check_database() with short timeout
        Assert: Returns False (timeout caught gracefully)
        """
        # Arrange
        async def slow_query():
            await asyncio.sleep(10)  # Longer than timeout
            return MagicMock()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(side_effect=slow_query)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch('app.core.probes.async_session_maker') as mock_maker:
            mock_maker.return_value = mock_session

            # Act
            result = await check_database(timeout_seconds=0.1)

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_check_database_query_error(self):
        """
        Test check_database returns False when query fails.

        Arrange: Mock session.execute to raise exception
        Act: Call check_database()
        Assert: Returns False
        """
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(side_effect=Exception("Query failed"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch('app.core.probes.async_session_maker') as mock_maker:
            mock_maker.return_value = mock_session

            # Act
            result = await check_database()

            # Assert
            assert result is False


class TestOpenRouterProbe:
    """Tests for OpenRouter API readiness probe."""

    @pytest.mark.asyncio
    async def test_check_openrouter_success(self):
        """
        Test check_openrouter returns True when API is reachable.

        Arrange: Mock httpx client to return 200 status
        Act: Call check_openrouter()
        Assert: Returns True
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Act
            result = await check_openrouter()

            # Assert
            assert result is True
            mock_client.head.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_openrouter_2xx_status(self):
        """
        Test check_openrouter accepts all 2xx status codes.

        Arrange: Mock httpx client to return 204 status
        Act: Call check_openrouter()
        Assert: Returns True
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Act
            result = await check_openrouter()

            # Assert
            assert result is True

    @pytest.mark.asyncio
    async def test_check_openrouter_4xx_status(self):
        """
        Test check_openrouter returns False on 4xx status.

        Arrange: Mock httpx client to return 404 status
        Act: Call check_openrouter()
        Assert: Returns False
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Act
            result = await check_openrouter()

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_check_openrouter_timeout(self):
        """
        Test check_openrouter returns False on timeout.

        Arrange: Mock httpx client to raise TimeoutException
        Act: Call check_openrouter()
        Assert: Returns False
        """
        # Arrange
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Act
            result = await check_openrouter()

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_check_openrouter_network_error(self):
        """
        Test check_openrouter returns False on network error.

        Arrange: Mock httpx client to raise RequestError
        Act: Call check_openrouter()
        Assert: Returns False
        """
        # Arrange
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=httpx.RequestError("Network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Act
            result = await check_openrouter()

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_check_openrouter_unexpected_error(self):
        """
        Test check_openrouter returns False on unexpected error.

        Arrange: Mock httpx client to raise generic exception
        Act: Call check_openrouter()
        Assert: Returns False (exception caught gracefully)
        """
        # Arrange
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=Exception("Unexpected error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Act
            result = await check_openrouter()

            # Assert
            assert result is False
