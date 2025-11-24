from pydantic import BaseModel, Field, validator
from typing import Optional, List


class PersonaSummary(BaseModel):
    id: str
    reddit_username: str
    display_name: str | None = None

    class Config:
        orm_mode = True


class PersonaConfig(BaseModel):
    """
    Configuration schema for persona behavior and style.

    Attributes:
        tone: Writing tone (e.g., "witty", "formal", "casual")
        style: Writing style (e.g., "concise", "detailed", "technical")
        core_values: List of core values/beliefs that guide persona
        target_subreddits: List of subreddit names to monitor (optional)
    """
    tone: Optional[str] = Field(default="casual", description="Writing tone")
    style: Optional[str] = Field(default="concise", description="Writing style")
    core_values: Optional[List[str]] = Field(
        default_factory=list,
        description="Core values/beliefs that guide persona"
    )
    target_subreddits: Optional[List[str]] = Field(
        default_factory=list,
        description="List of subreddit names to monitor"
    )

    class Config:
        schema_extra = {
            "example": {
                "tone": "friendly",
                "style": "concise",
                "core_values": ["honesty", "evidence-based reasoning"],
                "target_subreddits": ["test", "bottest"]
            }
        }


class PersonaCreateRequest(BaseModel):
    """
    Request schema for creating a new persona.

    Attributes:
        reddit_username: Reddit account username (must be unique, min 3 chars)
        display_name: Human-readable display name (optional)
        config: Persona configuration (optional, uses defaults if not provided)
    """
    reddit_username: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Reddit account username (unique, 3-255 chars)"
    )
    display_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Human-readable display name"
    )
    config: Optional[PersonaConfig] = Field(
        default_factory=PersonaConfig,
        description="Persona configuration"
    )

    @validator('reddit_username')
    def validate_reddit_username(cls, v):
        """Validate reddit_username format."""
        if not v:
            raise ValueError("reddit_username is required")
        # Reddit usernames cannot contain spaces
        if ' ' in v:
            raise ValueError("reddit_username cannot contain spaces")
        # Basic validation: alphanumeric, underscore, hyphen
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError(
                "reddit_username can only contain letters, numbers, "
                "underscores, and hyphens"
            )
        return v

    @validator('config', pre=True, always=True)
    def ensure_config(cls, v):
        """Ensure config is always a PersonaConfig instance."""
        if v is None:
            return PersonaConfig()
        if isinstance(v, dict):
            return PersonaConfig(**v)
        return v

    class Config:
        schema_extra = {
            "example": {
                "reddit_username": "AgentBot123",
                "display_name": "Friendly Agent",
                "config": {
                    "tone": "friendly",
                    "style": "concise",
                    "core_values": ["honesty", "evidence-based reasoning"],
                    "target_subreddits": ["test"]
                }
            }
        }


class PersonaCreateResponse(BaseModel):
    """
    Response schema for persona creation.

    Attributes:
        id: UUID of created persona
        reddit_username: Reddit account username
        display_name: Human-readable display name
        config: Persona configuration
        created_at: ISO 8601 timestamp of creation
    """
    id: str = Field(..., description="UUID of created persona")
    reddit_username: str = Field(..., description="Reddit account username")
    display_name: Optional[str] = Field(None, description="Display name")
    config: dict = Field(..., description="Persona configuration")
    created_at: str = Field(..., description="ISO 8601 timestamp")

    class Config:
        orm_mode = True
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "reddit_username": "AgentBot123",
                "display_name": "Friendly Agent",
                "config": {
                    "tone": "friendly",
                    "style": "concise",
                    "core_values": ["honesty"],
                    "target_subreddits": ["test"]
                },
                "created_at": "2025-11-25T10:30:00Z"
            }
        }
