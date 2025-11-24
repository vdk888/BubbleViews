"""
Agent configuration model for per-persona settings.

Stores key-value configuration pairs for each persona with JSON values.
"""

from sqlalchemy import Column, String, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
import json

from app.models.base import Base, UUIDMixin, TimestampMixin, ModelMixin


class AgentConfig(Base, UUIDMixin, TimestampMixin, ModelMixin):
    """
    Agent configuration key-value store per persona.

    Stores flexible configuration settings for each persona using
    key-value pairs with JSON values. Allows runtime configuration
    changes without schema migrations.

    Attributes:
        id: UUID primary key
        persona_id: Foreign key to Persona
        config_key: Configuration key name
        config_value: JSON configuration value
        updated_at: When configuration was last updated
    """

    __tablename__ = "agent_config"

    persona_id = Column(
        String,
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to Persona"
    )

    config_key = Column(
        String(255),
        nullable=False,
        doc="Configuration key name"
    )

    config_value = Column(
        Text,
        nullable=False,
        doc="JSON configuration value"
    )

    # Relationships
    persona = relationship("Persona", back_populates="agent_configs")

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("persona_id", "config_key", name="uq_persona_config_key"),
        Index("idx_agent_config_persona", "persona_id"),
        Index("idx_agent_config_key", "config_key"),
    )

    def get_value(self) -> any:
        """
        Parse config_value JSON to Python object.

        Returns:
            Parsed JSON value (dict, list, str, int, bool, etc.)
        """
        if not self.config_value:
            return None
        try:
            return json.loads(self.config_value)
        except json.JSONDecodeError:
            return self.config_value

    def set_value(self, value: any) -> None:
        """
        Set config_value from Python object.

        Args:
            value: Value to store (will be JSON-serialized)
        """
        if isinstance(value, str):
            # If already a string, check if it's valid JSON
            try:
                json.loads(value)
                self.config_value = value
            except json.JSONDecodeError:
                # Not JSON, so wrap it
                self.config_value = json.dumps(value)
        else:
            self.config_value = json.dumps(value)

    def __repr__(self) -> str:
        return (
            f"AgentConfig(id='{self.id}', "
            f"key='{self.config_key}', "
            f"persona_id='{self.persona_id}')"
        )
