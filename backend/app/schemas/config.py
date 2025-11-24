"""
Agent configuration schemas for Pydantic validation.

Provides request/response schemas for agent configuration endpoints
with validation rules aligned to business requirements.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field, field_validator


class AgentConfigSchema(BaseModel):
    """
    Schema for agent configuration settings.

    Defines the complete configuration shape for a persona's agent behavior,
    including target subreddits, posting mode, safety rules, and style sliders.

    Attributes:
        target_subreddits: List of subreddit names to monitor (without 'r/' prefix)
        auto_posting_enabled: Whether agent can post without approval
        safety_flags: Dictionary of safety/moderation settings
        persona_style: Dictionary of style sliders (0.0-1.0) for tone/personality

    Example:
        {
            "target_subreddits": ["test", "bottest"],
            "auto_posting_enabled": false,
            "safety_flags": {"require_approval": true, "content_filter": "strict"},
            "persona_style": {"directness": 0.7, "formality": 0.5, "humor": 0.8}
        }
    """

    target_subreddits: List[str] = Field(
        ...,
        description="List of subreddit names to monitor (without 'r/' prefix)",
        min_length=1,
        examples=[["test", "bottest", "AskReddit"]]
    )

    auto_posting_enabled: bool = Field(
        default=False,
        description="Whether agent can post without human approval"
    )

    safety_flags: Dict[str, Any] = Field(
        default_factory=dict,
        description="Safety and moderation settings",
        examples=[{"require_approval": True, "content_filter": "strict"}]
    )

    persona_style: Dict[str, float] = Field(
        default_factory=dict,
        description="Style sliders for personality (values 0.0-1.0)",
        examples=[{"directness": 0.7, "formality": 0.5, "humor": 0.8}]
    )

    @field_validator("target_subreddits")
    @classmethod
    def validate_subreddits(cls, v: List[str]) -> List[str]:
        """
        Validate that subreddit list is non-empty and contains valid names.

        Args:
            v: List of subreddit names

        Returns:
            Validated and cleaned list of subreddit names

        Raises:
            ValueError: If list is empty or contains invalid names
        """
        if not v or len(v) == 0:
            raise ValueError("target_subreddits must contain at least one subreddit")

        # Clean and validate each subreddit name
        cleaned = []
        for sub in v:
            # Remove 'r/' prefix if present
            sub = sub.strip()
            if sub.startswith("r/"):
                sub = sub[2:]

            # Validate subreddit name format (alphanumeric + underscores)
            if not sub:
                raise ValueError("Subreddit name cannot be empty")
            if not sub.replace("_", "").isalnum():
                raise ValueError(f"Invalid subreddit name: {sub}")

            cleaned.append(sub)

        return cleaned

    @field_validator("persona_style")
    @classmethod
    def validate_style_sliders(cls, v: Dict[str, float]) -> Dict[str, float]:
        """
        Validate that all style slider values are between 0.0 and 1.0.

        Args:
            v: Dictionary of style slider values

        Returns:
            Validated style sliders

        Raises:
            ValueError: If any slider value is out of range
        """
        for key, value in v.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"Style slider '{key}' must be a number, got {type(value)}")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"Style slider '{key}' must be between 0.0 and 1.0, got {value}")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "target_subreddits": ["test", "bottest"],
                "auto_posting_enabled": False,
                "safety_flags": {
                    "require_approval": True,
                    "content_filter": "strict",
                    "max_comment_length": 500
                },
                "persona_style": {
                    "directness": 0.7,
                    "formality": 0.5,
                    "humor": 0.8,
                    "technical_depth": 0.6
                }
            }
        }


class ConfigKeyValue(BaseModel):
    """
    Schema for a single configuration key-value pair.

    Used for setting/updating individual config keys via API.

    Attributes:
        persona_id: UUID of the persona
        key: Configuration key name
        value: Configuration value (JSON-serializable)
    """

    persona_id: str = Field(
        ...,
        description="UUID of the persona this config belongs to",
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )

    key: str = Field(
        ...,
        description="Configuration key name",
        min_length=1,
        max_length=255,
        examples=["target_subreddits", "auto_posting_enabled"]
    )

    value: Any = Field(
        ...,
        description="Configuration value (JSON-serializable)"
    )

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """
        Validate configuration key format.

        Args:
            v: Configuration key name

        Returns:
            Validated key name

        Raises:
            ValueError: If key format is invalid
        """
        # Only alphanumeric and underscores
        if not v.replace("_", "").isalnum():
            raise ValueError("Config key must contain only alphanumeric characters and underscores")

        return v


class ConfigResponse(BaseModel):
    """
    Response schema for configuration retrieval.

    Returns all configuration key-value pairs for a persona.

    Attributes:
        persona_id: UUID of the persona
        config: Dictionary of all configuration key-value pairs
    """

    persona_id: str = Field(
        ...,
        description="UUID of the persona"
    )

    config: Dict[str, Any] = Field(
        ...,
        description="Dictionary of all configuration key-value pairs"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "persona_id": "123e4567-e89b-12d3-a456-426614174000",
                "config": {
                    "target_subreddits": ["test", "bottest"],
                    "auto_posting_enabled": False,
                    "safety_flags": {"require_approval": True}
                }
            }
        }


class ConfigUpdateRequest(BaseModel):
    """
    Request schema for updating a configuration value.

    Attributes:
        persona_id: UUID of the persona
        key: Configuration key to update
        value: New configuration value
    """

    persona_id: str = Field(
        ...,
        description="UUID of the persona",
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )

    key: str = Field(
        ...,
        description="Configuration key to update",
        min_length=1,
        max_length=255,
        examples=["auto_posting_enabled"]
    )

    value: Any = Field(
        ...,
        description="New configuration value (JSON-serializable)",
        examples=[True]
    )


class ConfigUpdateResponse(BaseModel):
    """
    Response schema for configuration update.

    Attributes:
        persona_id: UUID of the persona
        key: Configuration key that was updated
        value: New configuration value
        updated: Whether the update was successful
    """

    persona_id: str
    key: str
    value: Any
    updated: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "persona_id": "123e4567-e89b-12d3-a456-426614174000",
                "key": "auto_posting_enabled",
                "value": True,
                "updated": True
            }
        }
