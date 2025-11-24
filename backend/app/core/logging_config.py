"""
Structured JSON logging configuration.

This module sets up application-wide JSON logging with:
- Consistent field names across all logs
- Request correlation IDs
- Persona tracking
- Cost tracking for LLM calls
- Timestamp, level, message, path, status code, latency

Logs are output to stdout in JSON format for easy parsing by
log aggregation systems (CloudWatch, Datadog, etc.).
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.

    Outputs log records as single-line JSON objects with consistent fields:
    - timestamp: ISO 8601 format with microseconds
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - message: Log message
    - logger: Logger name (module path)
    - path: Request path (if available)
    - method: HTTP method (if available)
    - status_code: HTTP status code (if available)
    - latency_ms: Request latency in milliseconds (if available)
    - request_id: Correlation ID (if available)
    - persona_id: Persona ID (if available)
    - cost: LLM call cost (if available)
    - exception: Exception details (if exception occurred)
    - extra: Any additional fields from log record

    Example output:
        {"timestamp": "2025-11-24T10:30:00.123456", "level": "INFO",
         "message": "Request completed", "path": "/api/v1/health",
         "status_code": 200, "latency_ms": 12.5, "request_id": "abc-123"}
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON string.

        Args:
            record: LogRecord to format

        Returns:
            JSON string representation of log record
        """
        # Base log data
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add stack info if present
        if record.stack_info:
            log_data["stack_info"] = self.formatStack(record.stack_info)

        # Extract extra fields from record
        # These are fields passed via logger.info("msg", extra={...})
        extra_fields = {
            "path": None,
            "method": None,
            "status_code": None,
            "latency_ms": None,
            "request_id": None,
            "persona_id": None,
            "cost": None,
        }

        for field in extra_fields:
            if hasattr(record, field):
                value = getattr(record, field)
                if value is not None:
                    log_data[field] = value

        # Add any other custom fields from extra
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info",
                "getMessage", "getMessage"
            ] and key not in log_data:
                log_data[key] = value

        # Serialize to JSON
        return json.dumps(log_data, default=str)


def setup_logging(
    level: str = "INFO",
    json_format: bool = True
) -> None:
    """
    Configure application logging.

    Sets up:
    - Root logger with specified level
    - JSON formatter (if json_format=True)
    - StreamHandler to stdout
    - Removes default handlers

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatter (True) or simple formatter (False)

    Example:
        # In main.py startup
        setup_logging(level="INFO", json_format=True)

    Note:
        Call this once at application startup, before any logging occurs.
    """
    # Get root logger
    root_logger = logging.getLogger()

    # Set level
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Set formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        # Simple format for development/debugging
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    console_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance with given name.

    Args:
        name: Logger name (usually __name__ of the module)

    Returns:
        Logger instance configured with JSON formatting

    Example:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"request_id": "abc-123"})
    """
    return logging.getLogger(name)


# Example usage helper
def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    request_id: Optional[str] = None,
    persona_id: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    latency_ms: Optional[float] = None,
    cost: Optional[float] = None,
    **extra_fields: Any
) -> None:
    """
    Log message with structured context fields.

    Convenience function for logging with common context fields.

    Args:
        logger: Logger instance
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        request_id: Request correlation ID
        persona_id: Persona ID
        path: Request path
        method: HTTP method
        status_code: HTTP status code
        latency_ms: Request latency in milliseconds
        cost: LLM call cost
        **extra_fields: Additional fields to include

    Example:
        log_with_context(
            logger,
            "info",
            "Request completed",
            request_id="abc-123",
            path="/api/v1/health",
            status_code=200,
            latency_ms=12.5
        )
    """
    # Build extra dict
    extra: Dict[str, Any] = {}

    if request_id is not None:
        extra["request_id"] = request_id
    if persona_id is not None:
        extra["persona_id"] = persona_id
    if path is not None:
        extra["path"] = path
    if method is not None:
        extra["method"] = method
    if status_code is not None:
        extra["status_code"] = status_code
    if latency_ms is not None:
        extra["latency_ms"] = latency_ms
    if cost is not None:
        extra["cost"] = cost

    # Add any additional fields
    extra.update(extra_fields)

    # Get log method
    log_method = getattr(logger, level.lower())

    # Log with extra fields
    log_method(message, extra=extra)
