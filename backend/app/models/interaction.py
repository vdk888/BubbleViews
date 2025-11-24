"""
Interaction model for episodic memory.

Stores all Reddit interactions (posts, comments, replies) with metadata
and optional embeddings for semantic search.
"""

from sqlalchemy import Column, String, Text, LargeBinary, ForeignKey, Index
from sqlalchemy.orm import relationship
import json

from app.models.base import Base, UUIDMixin, TimestampMixin, ModelMixin


class Interaction(Base, UUIDMixin, TimestampMixin, ModelMixin):
    """
    Episodic memory of Reddit interactions.

    Stores all agent interactions on Reddit including posts, comments,
    and replies. Each interaction includes content, metadata, and optional
    embedding for semantic search via FAISS.

    Attributes:
        id: UUID primary key
        persona_id: Foreign key to Persona
        content: The text content of the interaction
        interaction_type: Type of interaction (post, comment, reply)
        reddit_id: Reddit's unique ID for this item (e.g., t1_abc123)
        subreddit: Subreddit where interaction occurred
        parent_id: Parent item ID if this is a reply
        metadata: JSON metadata (score, author, timestamp, etc.)
        embedding: Optional BLOB for embedding vector (primary storage in FAISS)
        created_at: When interaction was created
        updated_at: When interaction was last modified
    """

    __tablename__ = "interactions"

    persona_id = Column(
        String,
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to Persona"
    )

    content = Column(
        Text,
        nullable=False,
        doc="The text content of the interaction"
    )

    interaction_type = Column(
        String(50),
        nullable=False,
        doc="Type of interaction (post, comment, reply)"
    )

    reddit_id = Column(
        String(255),
        nullable=False,
        unique=True,
        doc="Reddit's unique ID for this item (e.g., t1_abc123)"
    )

    subreddit = Column(
        String(255),
        nullable=False,
        doc="Subreddit where interaction occurred"
    )

    parent_id = Column(
        String(255),
        nullable=True,
        doc="Parent item ID if this is a reply"
    )

    interaction_metadata = Column(
        "metadata",  # Column name in DB
        Text,
        nullable=True,
        doc="JSON metadata (score, author, timestamp, etc.)"
    )

    embedding = Column(
        LargeBinary,
        nullable=True,
        doc="Optional BLOB for embedding vector (primary storage in FAISS)"
    )

    # Relationships
    persona = relationship("Persona", back_populates="interactions")

    # Indexes
    __table_args__ = (
        Index("idx_interactions_persona", "persona_id"),
        Index("idx_interactions_subreddit", "subreddit"),
        Index("idx_interactions_created", "created_at"),
        Index("idx_interactions_reddit_id", "reddit_id"),
        Index("idx_interactions_type", "interaction_type"),
    )

    def get_metadata(self) -> dict:
        """
        Parse metadata JSON to dictionary.

        Returns:
            Dictionary with interaction metadata
        """
        if not self.interaction_metadata:
            return {}
        try:
            return json.loads(self.interaction_metadata)
        except json.JSONDecodeError:
            return {}

    def set_metadata(self, metadata_dict: dict) -> None:
        """
        Set metadata from dictionary.

        Args:
            metadata_dict: Metadata dictionary to store
        """
        self.interaction_metadata = json.dumps(metadata_dict)

    def __repr__(self) -> str:
        return (
            f"Interaction(id='{self.id}', "
            f"type='{self.interaction_type}', "
            f"reddit_id='{self.reddit_id}')"
        )
