"""
Tests for structured JSON logging configuration.

This module tests:
- JSONFormatter (JSON log output)
- setup_logging() (logging configuration)
- get_logger() (logger factory)

Tests follow AAA (Arrange, Act, Assert) pattern.
"""

import pytest
import json
import logging
import io
from unittest.mock import patch

from app.core.logging_config import (
    JSONFormatter,
    setup_logging,
    get_logger,
    log_with_context,
)


class TestJSONFormatter:
    """Tests for JSON log formatter."""

    def test_json_formatter_basic_message(self):
        """
        Test JSONFormatter outputs valid JSON.

        Arrange: Create logger with JSONFormatter
        Act: Log a message
        Assert: Output is valid JSON with required fields
        """
        # Arrange
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)

        # Remove existing handlers
        logger.handlers = []

        # Create string stream for output
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Act
        logger.info("Test message")

        # Assert
        output = stream.getvalue().strip()
        log_data = json.loads(output)  # Should be valid JSON

        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"
        assert "timestamp" in log_data
        assert log_data["logger"] == "test_logger"

    def test_json_formatter_with_extra_fields(self):
        """
        Test JSONFormatter includes extra fields.

        Arrange: Create logger with JSONFormatter
        Act: Log message with extra fields
        Assert: Extra fields included in JSON output
        """
        # Arrange
        logger = logging.getLogger("test_logger_extra")
        logger.setLevel(logging.INFO)
        logger.handlers = []

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Act
        logger.info(
            "Test message",
            extra={
                "request_id": "abc-123",
                "path": "/api/v1/test",
                "status_code": 200,
                "latency_ms": 12.5,
            }
        )

        # Assert
        output = stream.getvalue().strip()
        log_data = json.loads(output)

        assert log_data["request_id"] == "abc-123"
        assert log_data["path"] == "/api/v1/test"
        assert log_data["status_code"] == 200
        assert log_data["latency_ms"] == 12.5

    def test_json_formatter_with_exception(self):
        """
        Test JSONFormatter includes exception details.

        Arrange: Create logger with JSONFormatter
        Act: Log exception
        Assert: Exception info included in JSON output
        """
        # Arrange
        logger = logging.getLogger("test_logger_exc")
        logger.setLevel(logging.ERROR)
        logger.handlers = []

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Act
        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.error("Error occurred", exc_info=True)

        # Assert
        output = stream.getvalue().strip()
        log_data = json.loads(output)

        assert log_data["level"] == "ERROR"
        assert log_data["message"] == "Error occurred"
        assert "exception" in log_data
        assert "ValueError: Test exception" in log_data["exception"]

    def test_json_formatter_persona_and_cost(self):
        """
        Test JSONFormatter includes persona_id and cost fields.

        Arrange: Create logger with JSONFormatter
        Act: Log message with persona_id and cost
        Assert: Fields included in JSON output
        """
        # Arrange
        logger = logging.getLogger("test_logger_persona")
        logger.setLevel(logging.INFO)
        logger.handlers = []

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Act
        logger.info(
            "LLM call completed",
            extra={
                "persona_id": "persona-123",
                "cost": 0.00042,
                "request_id": "req-456",
            }
        )

        # Assert
        output = stream.getvalue().strip()
        log_data = json.loads(output)

        assert log_data["persona_id"] == "persona-123"
        assert log_data["cost"] == 0.00042
        assert log_data["request_id"] == "req-456"


class TestSetupLogging:
    """Tests for logging setup function."""

    def test_setup_logging_configures_root_logger(self):
        """
        Test setup_logging configures root logger.

        Arrange: None
        Act: Call setup_logging()
        Assert: Root logger has correct level and handler
        """
        # Arrange & Act
        setup_logging(level="INFO", json_format=True)

        # Assert
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) > 0

        # Should have JSONFormatter
        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)

    def test_setup_logging_with_debug_level(self):
        """
        Test setup_logging with DEBUG level.

        Arrange: None
        Act: Call setup_logging(level="DEBUG")
        Assert: Root logger level is DEBUG
        """
        # Arrange & Act
        setup_logging(level="DEBUG", json_format=True)

        # Assert
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_setup_logging_with_simple_format(self):
        """
        Test setup_logging with simple (non-JSON) format.

        Arrange: None
        Act: Call setup_logging(json_format=False)
        Assert: Handler has simple Formatter (not JSONFormatter)
        """
        # Arrange & Act
        setup_logging(level="INFO", json_format=False)

        # Assert
        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        assert not isinstance(handler.formatter, JSONFormatter)
        assert isinstance(handler.formatter, logging.Formatter)


class TestGetLogger:
    """Tests for get_logger factory function."""

    def test_get_logger_returns_logger(self):
        """
        Test get_logger returns logger instance.

        Arrange: None
        Act: Call get_logger()
        Assert: Returns logging.Logger instance
        """
        # Arrange & Act
        logger = get_logger("test_module")

        # Assert
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_module"

    def test_get_logger_different_names(self):
        """
        Test get_logger returns different loggers for different names.

        Arrange: None
        Act: Call get_logger() with different names
        Assert: Returns different logger instances
        """
        # Arrange & Act
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        # Assert
        assert logger1.name == "module1"
        assert logger2.name == "module2"
        assert logger1.name != logger2.name


class TestLogWithContext:
    """Tests for log_with_context helper function."""

    def test_log_with_context_includes_all_fields(self):
        """
        Test log_with_context includes all context fields.

        Arrange: Create logger with JSONFormatter
        Act: Call log_with_context with all fields
        Assert: All fields included in log output
        """
        # Arrange
        logger = logging.getLogger("test_context")
        logger.setLevel(logging.INFO)
        logger.handlers = []

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Act
        log_with_context(
            logger,
            "info",
            "Test message",
            request_id="req-123",
            persona_id="persona-456",
            path="/api/v1/test",
            method="GET",
            status_code=200,
            latency_ms=15.3,
            cost=0.0005,
        )

        # Assert
        output = stream.getvalue().strip()
        log_data = json.loads(output)

        assert log_data["message"] == "Test message"
        assert log_data["request_id"] == "req-123"
        assert log_data["persona_id"] == "persona-456"
        assert log_data["path"] == "/api/v1/test"
        assert log_data["method"] == "GET"
        assert log_data["status_code"] == 200
        assert log_data["latency_ms"] == 15.3
        assert log_data["cost"] == 0.0005

    def test_log_with_context_extra_fields(self):
        """
        Test log_with_context accepts extra fields.

        Arrange: Create logger with JSONFormatter
        Act: Call log_with_context with extra kwargs
        Assert: Extra fields included in log output
        """
        # Arrange
        logger = logging.getLogger("test_context_extra")
        logger.setLevel(logging.INFO)
        logger.handlers = []

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Act
        log_with_context(
            logger,
            "info",
            "Test message",
            request_id="req-123",
            custom_field="custom_value",
            another_field=42,
        )

        # Assert
        output = stream.getvalue().strip()
        log_data = json.loads(output)

        assert log_data["request_id"] == "req-123"
        assert log_data["custom_field"] == "custom_value"
        assert log_data["another_field"] == 42

    def test_log_with_context_supports_all_levels(self):
        """
        Test log_with_context supports all log levels.

        Arrange: Create logger with JSONFormatter
        Act: Call log_with_context with different levels
        Assert: Correct log level in output
        """
        # Arrange
        logger = logging.getLogger("test_context_levels")
        logger.setLevel(logging.DEBUG)
        logger.handlers = []

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Act & Assert
        for level in ["debug", "info", "warning", "error", "critical"]:
            stream.truncate(0)
            stream.seek(0)

            log_with_context(logger, level, f"Test {level} message")

            output = stream.getvalue().strip()
            log_data = json.loads(output)

            assert log_data["level"] == level.upper()
            assert log_data["message"] == f"Test {level} message"
