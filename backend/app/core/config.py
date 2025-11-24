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
        default="openai/gpt-5.1-mini",
        description="Primary model for generating responses (fast, cheap)"
    )
    consistency_model: str = Field(
        default="anthropic/claude-4.5-haiku",
        description="Secondary model for consistency checks (accurate, cheap)"
    )

    # Agent Configuration
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

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """
        Validate that secret_key is properly configured.

        Raises ValueError if still using placeholder value.
        """
        if v == "generate-with-openssl-rand-hex-32":
            raise ValueError(
                "SECRET_KEY must be set to a secure random value. "
                "Generate one with: openssl rand -hex 32"
            )
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v


# Global settings instance
# Import this instance throughout the application
settings = Settings()
