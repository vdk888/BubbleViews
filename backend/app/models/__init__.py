"""
SQLAlchemy ORM models for Reddit AI Agent.

This module exports all database models and the declarative base.
Import models from this module to ensure they're registered with SQLAlchemy.
"""

from app.models.base import Base, TimestampMixin, UUIDMixin, ModelMixin
from app.models.persona import Persona
from app.models.belief import (
    BeliefNode,
    BeliefEdge,
    StanceVersion,
    EvidenceLink,
    BeliefUpdate,
)
from app.models.interaction import Interaction
from app.models.pending_post import PendingPost
from app.models.agent_config import AgentConfig

# Export all models
__all__ = [
    # Base classes
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "ModelMixin",
    # Models
    "Persona",
    "BeliefNode",
    "BeliefEdge",
    "StanceVersion",
    "EvidenceLink",
    "BeliefUpdate",
    "Interaction",
    "PendingPost",
    "AgentConfig",
]
