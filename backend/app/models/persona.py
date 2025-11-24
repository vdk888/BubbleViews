"""
Persona model for multi-account Reddit AI agent.

Each persona represents a distinct Reddit account with its own
configuration, beliefs, and interaction history.
"""

from sqlalchemy import Column, String, Text, Index
from sqlalchemy.orm import relationship
import json

from app.models.base import Base, UUIDMixin, TimestampMixin, ModelMixin


class Persona(Base, UUIDMixin, TimestampMixin, ModelMixin):
    """
    Persona model representing a Reddit account/agent identity.

    Each persona has its own:
    - Reddit credentials
    - Belief graph
    - Interaction history
    - Configuration settings
    - Moderation queue

    Attributes:
        id: UUID primary key
        reddit_username: Reddit account username (unique)
        display_name: Human-readable display name
        config: JSON configuration (target_subreddits, style sliders, safety flags)
        created_at: When persona was created
        updated_at: When persona was last modified
    """

    __tablename__ = "personas"

    reddit_username = Column(
        String(255),
        nullable=False,
        unique=True,
        doc="Reddit account username"
    )

    display_name = Column(
        String(255),
        nullable=True,
        doc="Human-readable display name for the persona"
    )

    config = Column(
        Text,
        nullable=False,
        default="{}",
        doc="JSON configuration: target_subreddits, style sliders, safety flags"
    )

    # Relationships
    belief_nodes = relationship(
        "BeliefNode",
        back_populates="persona",
        cascade="all, delete-orphan"
    )

    belief_edges = relationship(
        "BeliefEdge",
        back_populates="persona",
        cascade="all, delete-orphan"
    )

    stance_versions = relationship(
        "StanceVersion",
        back_populates="persona",
        cascade="all, delete-orphan"
    )

    evidence_links = relationship(
        "EvidenceLink",
        back_populates="persona",
        cascade="all, delete-orphan"
    )

    interactions = relationship(
        "Interaction",
        back_populates="persona",
        cascade="all, delete-orphan"
    )

    belief_updates = relationship(
        "BeliefUpdate",
        back_populates="persona",
        cascade="all, delete-orphan"
    )

    pending_posts = relationship(
        "PendingPost",
        back_populates="persona",
        cascade="all, delete-orphan"
    )

    agent_configs = relationship(
        "AgentConfig",
        back_populates="persona",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_persona_username", "reddit_username"),
    )

    def get_config(self) -> dict:
        """
        Parse config JSON string to dictionary.

        Returns:
            Dictionary with persona configuration

        Raises:
            json.JSONDecodeError: If config is not valid JSON
        """
        if not self.config:
            return {}
        return json.loads(self.config)

    def set_config(self, config_dict: dict) -> None:
        """
        Set config from dictionary.

        Args:
            config_dict: Configuration dictionary to store

        Note:
            Validates JSON serialization before setting.
        """
        self.config = json.dumps(config_dict)

    def __repr__(self) -> str:
        return f"Persona(id='{self.id}', reddit_username='{self.reddit_username}')"
