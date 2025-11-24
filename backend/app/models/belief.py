"""
Belief system models for the agent's knowledge graph.

Implements a belief graph with nodes, edges, stance versions, evidence,
and update audit logs. Supports belief evolution tracking and Bayesian-style
confidence updates.
"""

from sqlalchemy import Column, String, Text, Float, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import relationship
import json

from app.models.base import Base, UUIDMixin, TimestampMixin, ModelMixin


class BeliefNode(Base, UUIDMixin, TimestampMixin, ModelMixin):
    """
    Belief node in the agent's knowledge graph.

    Each belief is a structured statement with confidence, tags,
    and supporting evidence. Beliefs can be connected via edges
    (supports, contradicts, depends_on, etc.).

    Attributes:
        id: UUID primary key
        persona_id: Foreign key to Persona
        title: Brief title/summary of the belief
        summary: Detailed description of the belief
        current_confidence: Current confidence level (0.0 to 1.0)
        tags: JSON array of tags for categorization
        created_at: When belief was created
        updated_at: When belief was last modified
    """

    __tablename__ = "belief_nodes"

    persona_id = Column(
        String,
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to Persona"
    )

    title = Column(
        String(500),
        nullable=False,
        doc="Brief title/summary of the belief"
    )

    summary = Column(
        Text,
        nullable=False,
        doc="Detailed description of the belief"
    )

    current_confidence = Column(
        Float,
        nullable=True,
        doc="Current confidence level (0.0 to 1.0)"
    )

    tags = Column(
        Text,
        nullable=True,
        doc="JSON array of tags for categorization"
    )

    # Relationships
    persona = relationship("Persona", back_populates="belief_nodes")

    # Edges where this belief is the source
    outgoing_edges = relationship(
        "BeliefEdge",
        foreign_keys="BeliefEdge.source_id",
        back_populates="source",
        cascade="all, delete-orphan"
    )

    # Edges where this belief is the target
    incoming_edges = relationship(
        "BeliefEdge",
        foreign_keys="BeliefEdge.target_id",
        back_populates="target",
        cascade="all, delete-orphan"
    )

    stance_versions = relationship(
        "StanceVersion",
        back_populates="belief",
        cascade="all, delete-orphan"
    )

    evidence_links = relationship(
        "EvidenceLink",
        back_populates="belief",
        cascade="all, delete-orphan"
    )

    belief_updates = relationship(
        "BeliefUpdate",
        back_populates="belief",
        cascade="all, delete-orphan"
    )

    # Indexes and constraints
    __table_args__ = (
        Index("idx_belief_nodes_persona", "persona_id"),
        Index("idx_belief_nodes_confidence", "current_confidence"),
        CheckConstraint(
            "current_confidence IS NULL OR (current_confidence >= 0 AND current_confidence <= 1)",
            name="ck_belief_confidence_range"
        ),
    )

    def get_tags(self) -> list[str]:
        """
        Parse tags JSON to list.

        Returns:
            List of tag strings
        """
        if not self.tags:
            return []
        try:
            tags = json.loads(self.tags)
            return tags if isinstance(tags, list) else []
        except json.JSONDecodeError:
            return []

    def set_tags(self, tags: list[str]) -> None:
        """
        Set tags from list.

        Args:
            tags: List of tag strings
        """
        self.tags = json.dumps(tags)

    def __repr__(self) -> str:
        return f"BeliefNode(id='{self.id}', title='{self.title[:50]}...')"


class BeliefEdge(Base, UUIDMixin, TimestampMixin, ModelMixin):
    """
    Edge connecting two beliefs in the knowledge graph.

    Edges represent relationships between beliefs:
    - supports: belief A supports belief B
    - contradicts: belief A contradicts belief B
    - depends_on: belief A depends on belief B
    - evidence_for: belief A is evidence for belief B

    Attributes:
        id: UUID primary key
        persona_id: Foreign key to Persona
        source_id: Source belief node ID
        target_id: Target belief node ID
        relation: Type of relationship (supports, contradicts, depends_on, evidence_for)
        weight: Strength of relationship (0.0 to 1.0)
        created_at: When edge was created
        updated_at: When edge was last modified
    """

    __tablename__ = "belief_edges"

    persona_id = Column(
        String,
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to Persona"
    )

    source_id = Column(
        String,
        ForeignKey("belief_nodes.id", ondelete="CASCADE"),
        nullable=False,
        doc="Source belief node ID"
    )

    target_id = Column(
        String,
        ForeignKey("belief_nodes.id", ondelete="CASCADE"),
        nullable=False,
        doc="Target belief node ID"
    )

    relation = Column(
        String(50),
        nullable=False,
        doc="Type of relationship (supports, contradicts, depends_on, evidence_for)"
    )

    weight = Column(
        Float,
        default=0.5,
        doc="Strength of relationship (0.0 to 1.0)"
    )

    # Relationships
    persona = relationship("Persona", back_populates="belief_edges")

    source = relationship(
        "BeliefNode",
        foreign_keys=[source_id],
        back_populates="outgoing_edges"
    )

    target = relationship(
        "BeliefNode",
        foreign_keys=[target_id],
        back_populates="incoming_edges"
    )

    # Indexes
    __table_args__ = (
        Index("idx_belief_edges_persona", "persona_id"),
        Index("idx_belief_edges_relation", "relation"),
        Index("idx_belief_edges_source", "source_id"),
        Index("idx_belief_edges_target", "target_id"),
    )

    def __repr__(self) -> str:
        return f"BeliefEdge(id='{self.id}', relation='{self.relation}')"


class StanceVersion(Base, UUIDMixin, TimestampMixin, ModelMixin):
    """
    Historical version of a belief stance.

    Tracks how the agent's stance on a belief has evolved over time.
    Each version includes the text, confidence, status, and rationale.

    Attributes:
        id: UUID primary key
        persona_id: Foreign key to Persona
        belief_id: Foreign key to BeliefNode
        text: Text representation of the stance
        confidence: Confidence level at this version (0.0 to 1.0)
        status: Version status (current, deprecated, locked)
        rationale: Explanation for this stance/version
        created_at: When this version was created
    """

    __tablename__ = "stance_versions"

    persona_id = Column(
        String,
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to Persona"
    )

    belief_id = Column(
        String,
        ForeignKey("belief_nodes.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to BeliefNode"
    )

    text = Column(
        Text,
        nullable=False,
        doc="Text representation of the stance"
    )

    confidence = Column(
        Float,
        nullable=True,
        doc="Confidence level at this version (0.0 to 1.0)"
    )

    status = Column(
        String(50),
        default="current",
        doc="Version status (current, deprecated, locked)"
    )

    rationale = Column(
        Text,
        nullable=True,
        doc="Explanation for this stance/version"
    )

    # Relationships
    persona = relationship("Persona", back_populates="stance_versions")
    belief = relationship("BeliefNode", back_populates="stance_versions")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_stance_versions_status", "status"),
        Index("idx_stance_versions_belief", "belief_id"),
        Index("idx_stance_versions_created", "created_at"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_stance_confidence_range"
        ),
    )

    def __repr__(self) -> str:
        return f"StanceVersion(id='{self.id}', status='{self.status}')"


class EvidenceLink(Base, UUIDMixin, TimestampMixin, ModelMixin):
    """
    Evidence supporting or contradicting a belief.

    Links external sources (Reddit comments, articles, notes) to beliefs
    to track the evidence base and support belief updates.

    Attributes:
        id: UUID primary key
        persona_id: Foreign key to Persona
        belief_id: Foreign key to BeliefNode
        source_type: Type of source (reddit_comment, external_link, note)
        source_ref: Reference to source (reddit ID, URL, etc.)
        strength: Strength of evidence (weak, moderate, strong)
        created_at: When evidence was linked
    """

    __tablename__ = "evidence_links"

    persona_id = Column(
        String,
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to Persona"
    )

    belief_id = Column(
        String,
        ForeignKey("belief_nodes.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to BeliefNode"
    )

    source_type = Column(
        String(50),
        nullable=False,
        doc="Type of source (reddit_comment, external_link, note)"
    )

    source_ref = Column(
        Text,
        nullable=False,
        doc="Reference to source (reddit ID, URL, etc.)"
    )

    strength = Column(
        String(20),
        nullable=True,
        doc="Strength of evidence (weak, moderate, strong)"
    )

    # Relationships
    persona = relationship("Persona", back_populates="evidence_links")
    belief = relationship("BeliefNode", back_populates="evidence_links")

    # Indexes
    __table_args__ = (
        Index("idx_evidence_links_belief", "belief_id"),
        Index("idx_evidence_links_source_type", "source_type"),
    )

    def __repr__(self) -> str:
        return f"EvidenceLink(id='{self.id}', source_type='{self.source_type}')"


class BeliefUpdate(Base, UUIDMixin, TimestampMixin, ModelMixin):
    """
    Audit log of belief updates.

    Tracks all changes to beliefs including old/new values, reason,
    and trigger type. Provides complete audit trail for belief evolution.

    Attributes:
        id: UUID primary key
        persona_id: Foreign key to Persona
        belief_id: Foreign key to BeliefNode
        old_value: JSON snapshot of old belief state
        new_value: JSON snapshot of new belief state
        reason: Human-readable reason for the update
        trigger_type: What triggered the update (manual, evidence, conflict, governor)
        updated_by: Who/what made the update
        created_at: When the update occurred
    """

    __tablename__ = "belief_updates"

    persona_id = Column(
        String,
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to Persona"
    )

    belief_id = Column(
        String,
        ForeignKey("belief_nodes.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to BeliefNode"
    )

    old_value = Column(
        Text,
        nullable=True,
        doc="JSON snapshot of old belief state"
    )

    new_value = Column(
        Text,
        nullable=True,
        doc="JSON snapshot of new belief state"
    )

    reason = Column(
        Text,
        nullable=False,
        doc="Human-readable reason for the update"
    )

    trigger_type = Column(
        String(50),
        nullable=True,
        doc="What triggered the update (manual, evidence, conflict, governor)"
    )

    updated_by = Column(
        String(255),
        nullable=True,
        doc="Who/what made the update"
    )

    # Relationships
    persona = relationship("Persona", back_populates="belief_updates")
    belief = relationship("BeliefNode", back_populates="belief_updates")

    # Indexes
    __table_args__ = (
        Index("idx_belief_updates_belief", "belief_id"),
        Index("idx_belief_updates_created", "created_at"),
        Index("idx_belief_updates_trigger", "trigger_type"),
    )

    def get_old_value(self) -> dict:
        """Parse old_value JSON to dict."""
        if not self.old_value:
            return {}
        return json.loads(self.old_value)

    def get_new_value(self) -> dict:
        """Parse new_value JSON to dict."""
        if not self.new_value:
            return {}
        return json.loads(self.new_value)

    def set_old_value(self, value: dict) -> None:
        """Set old_value from dict."""
        self.old_value = json.dumps(value)

    def set_new_value(self, value: dict) -> None:
        """Set new_value from dict."""
        self.new_value = json.dumps(value)

    def __repr__(self) -> str:
        return f"BeliefUpdate(id='{self.id}', trigger_type='{self.trigger_type}')"
