"""
Centralized configuration management using Pydantic Settings.

This module provides type-safe configuration management with validation,
loading settings from environment variables and .env files.
"""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    Secrets should never be committed to code - use .env file (gitignored).
    """

    # API Configuration
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="API version 1 prefix for all endpoints"
    )
    project_name: str = Field(
        default="Reddit AI Agent",
        description="Project name displayed in API docs"
    )

    # Database Configuration (SQLite)
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/reddit_agent.db",
        description="Database connection URL (SQLite for MVP, PostgreSQL-ready format)"
    )
    data_directory: str = Field(
        default="./data",
        description="Directory for data storage (FAISS indexes, etc.)"
    )

    # Reddit API Credentials
    reddit_client_id: str = Field(
        ...,
        description="Reddit OAuth2 client ID"
    )
    reddit_client_secret: str = Field(
        ...,
        description="Reddit OAuth2 client secret"
    )
    reddit_user_agent: str = Field(
        ...,
        description="Reddit API user agent string"
    )
    reddit_username: str = Field(
        ...,
        description="Reddit account username"
    )
    reddit_password: str = Field(
        ...,
        description="Reddit account password"
    )

    # OpenRouter LLM Configuration
    openrouter_api_key: str = Field(
        ...,
        description="OpenRouter API key for LLM access"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL (OpenAI-compatible)"
    )

    # Model Selection (can switch without code changes)
    response_model: str = Field(
        default="openai/gpt-5-mini",
        description="Primary model for generating responses (fast, cheap)"
    )
    consistency_model: str = Field(
        default="anthropic/claude-haiku-4.5",
        description="Secondary model for consistency checks (accurate, cheap)"
    )
    relationship_model: str = Field(
        default="anthropic/claude-haiku-4.5",
        description="Model for intelligent relationship suggestions between beliefs"
    )

    # Belief Auto-Linking Configuration
    auto_link_beliefs: bool = Field(
        default=True,
        description="Enable automatic relationship creation when new beliefs are created"
    )
    auto_link_min_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum weight threshold for auto-creating belief edges (0.0-1.0)"
    )

    # Agent Configuration
    agent_interval_seconds: int = Field(
        default=14400,
        description="Seconds between agent perception cycles (default: 14400 = 4 hours)"
    )
    target_subreddits: List[str] = Field(
        default=["test", "bottest"],
        description="List of subreddits the agent monitors"
    )
    auto_posting_enabled: bool = Field(
        default=False,
        description="Enable automatic posting (bypasses moderation queue)"
    )

    # Security Configuration
    secret_key: str = Field(
        ...,
        description="Secret key for JWT token signing (generate with: openssl rand -hex 32)"
    )
    access_token_expire_minutes: int = Field(
        default=60,
        description="JWT access token expiration time in minutes"
    )

    # CORS Configuration
    cors_origins: List[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins (frontend URLs)"
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow cookies/credentials in CORS requests"
    )

    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
        env_nested_delimiter="__",  # Support nested config via env vars
    )

    @field_validator("target_subreddits", mode="before")
    @classmethod
    def parse_target_subreddits(cls, v: str | List[str]) -> List[str]:
        """
        Parse target_subreddits from JSON string or list.

        Handles both JSON array strings and Python lists for flexibility.
        """
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Fallback: split by comma if not valid JSON
                return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        """
        Parse cors_origins from JSON string or list.

        Handles both JSON array strings and Python lists for flexibility.
        Supports comma-separated origins for easier .env configuration.
        """
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Fallback: split by comma if not valid JSON
                return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """
        Validate that secret_key is properly configured.

        Raises ValueError if still using placeholder value or too short.
        Security requirement: JWT signing keys must be at least 32 characters.
        """
        if not v or v.strip() == "":
            raise ValueError(
                "SECRET_KEY is required and cannot be empty. "
                "Generate one with: openssl rand -hex 32"
            )
        if v in ["generate-with-openssl-rand-hex-32", "CHANGE_ME_32_CHARS_MIN", "your-secret-key-here"]:
            raise ValueError(
                "SECRET_KEY must be set to a secure random value (not placeholder). "
                "Generate one with: openssl rand -hex 32"
            )
        if len(v) < 32:
            raise ValueError(
                f"SECRET_KEY must be at least 32 characters long for security. "
                f"Current length: {len(v)}. Generate with: openssl rand -hex 32"
            )
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """
        Validate database URL format.

        Ensures URL has proper scheme and is not a placeholder.
        Supports SQLite (MVP) and PostgreSQL (production-ready).
        """
        if not v or v.strip() == "":
            raise ValueError("DATABASE_URL is required and cannot be empty")

        # Check for valid database schemes
        valid_schemes = ["sqlite", "sqlite+aiosqlite", "postgresql", "postgresql+asyncpg"]
        if not any(v.startswith(scheme + "://") or v.startswith(scheme + ":///") for scheme in valid_schemes):
            raise ValueError(
                f"DATABASE_URL must start with one of: {', '.join(valid_schemes)}. "
                f"Got: {v[:20]}..."
            )

        # Warn if using relative SQLite path in production (not an error, just validation)
        if "sqlite" in v and not v.startswith("sqlite:///:memory:"):
            # This is fine for MVP, just ensure it's intentional
            pass

        return v

    @field_validator("reddit_client_id", "reddit_client_secret", "reddit_username", "reddit_password")
    @classmethod
    def validate_reddit_credentials(cls, v: str, info) -> str:
        """
        Validate Reddit API credentials are set.

        These are required for the agent to interact with Reddit.
        """
        field_name = info.field_name
        if not v or v.strip() == "":
            raise ValueError(
                f"{field_name.upper()} is required. "
                f"Get credentials from https://www.reddit.com/prefs/apps"
            )

        # Check for placeholder values
        placeholders = [
            "your_client_id_here",
            "your_client_secret_here",
            "your_reddit_username",
            "your_reddit_password",
            "YOUR_",
            "CHANGE_ME",
        ]
        if any(placeholder.lower() in v.lower() for placeholder in placeholders):
            raise ValueError(
                f"{field_name.upper()} contains placeholder value. "
                f"Set real credential from https://www.reddit.com/prefs/apps"
            )

        return v

    @field_validator("reddit_user_agent")
    @classmethod
    def validate_user_agent(cls, v: str) -> str:
        """
        Validate Reddit user agent format.

        Reddit requires descriptive user agents following their API rules:
        platform:app_name:version (by /u/username)
        """
        if not v or v.strip() == "":
            raise ValueError(
                "REDDIT_USER_AGENT is required. "
                "Format: platform:app_name:version (by /u/username)"
            )

        # Check for generic placeholder
        if "MyRedditBot" in v or "YourUsername" in v:
            raise ValueError(
                "REDDIT_USER_AGENT contains placeholder values. "
                "Update to: python:YourAppName:v1.0 (by /u/YourRedditUsername)"
            )

        # Warn if missing required components (not strict error, Reddit will enforce)
        if ":" not in v or "(by /u/" not in v:
            # This is more of a warning, but we'll allow it (Reddit API will reject if invalid)
            pass

        return v

    @field_validator("openrouter_api_key")
    @classmethod
    def validate_openrouter_key(cls, v: str) -> str:
        """
        Validate OpenRouter API key format.

        OpenRouter keys start with 'sk-or-v1-' prefix.
        """
        if not v or v.strip() == "":
            raise ValueError(
                "OPENROUTER_API_KEY is required. "
                "Get one from https://openrouter.ai/keys"
            )

        # Check for placeholder
        if "your-api-key-here" in v.lower() or "your_key" in v.lower() or v == "sk-or-v1-...":
            raise ValueError(
                "OPENROUTER_API_KEY contains placeholder value. "
                "Get real key from https://openrouter.ai/keys"
            )

        # Check format (OpenRouter keys typically start with sk-or-v1-)
        if not v.startswith("sk-or-"):
            # Not a strict error - OpenRouter might change format
            # But warn in logs (could add logging here if needed)
            pass

        return v


# Global settings instance
# Import this instance throughout the application
settings = Settings()
