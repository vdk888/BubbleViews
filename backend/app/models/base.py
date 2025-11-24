"""
Base models and mixins for SQLAlchemy ORM.

Provides reusable base classes, mixins for timestamps and UUIDs,
and common utilities for all database models.
"""

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import Column, String, text
from sqlalchemy.ext.declarative import declarative_base


# SQLAlchemy declarative base for all ORM models
Base = declarative_base()


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at timestamp columns.

    Uses TEXT type for SQLite compatibility (ISO format strings).
    Timestamps are stored in UTC ISO format for PostgreSQL compatibility.

    Attributes:
        created_at: Timestamp when record was created (immutable)
        updated_at: Timestamp when record was last updated (auto-updated)
    """

    created_at = Column(
        String,
        nullable=False,
        server_default=text("(datetime('now'))"),
        doc="UTC timestamp when record was created"
    )

    updated_at = Column(
        String,
        nullable=False,
        server_default=text("(datetime('now'))"),
        onupdate=lambda: datetime.utcnow().isoformat(),
        doc="UTC timestamp when record was last updated"
    )


class UUIDMixin:
    """
    Mixin that adds a UUID primary key column.

    Uses TEXT type for SQLite compatibility (string format UUIDs).
    UUIDs are stored as strings for easy migration to PostgreSQL later.

    Attributes:
        id: UUID primary key as TEXT
    """

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="UUID primary key"
    )


def utc_now_iso() -> str:
    """
    Get current UTC timestamp in ISO format.

    Returns:
        ISO format timestamp string (e.g., "2025-01-15T10:30:45.123456")

    Note:
        Used for explicit timestamp setting in application code.
        Database triggers use CURRENT_TIMESTAMP for automatic timestamps.
    """
    return datetime.utcnow().isoformat()


class ModelMixin:
    """
    Mixin providing common model utilities.

    Adds helper methods for serialization, representation, and common operations.
    """

    def to_dict(self) -> dict[str, Any]:
        """
        Convert model instance to dictionary.

        Returns:
            Dictionary with all column values

        Note:
            Only includes columns, not relationships.
            Override in subclasses to customize serialization.
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

    def __repr__(self) -> str:
        """
        String representation of model instance.

        Returns:
            String like "ModelName(id='uuid', attr1='value'...)"
        """
        attrs = ", ".join(
            f"{key}={repr(value)}"
            for key, value in self.to_dict().items()
            if key in ["id", "name", "title", "username"]  # Key identifying fields
        )
        return f"{self.__class__.__name__}({attrs})"
