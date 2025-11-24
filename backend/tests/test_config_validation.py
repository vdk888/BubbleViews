"""
Tests for configuration validation.

Ensures environment variables are validated at startup.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestSecretKeyValidation:
    """Test SECRET_KEY validation."""

    def test_secret_key_too_short(self, monkeypatch):
        """Test SECRET_KEY must be at least 32 characters."""
        monkeypatch.setenv("SECRET_KEY", "tooshort")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "SECRET_KEY must be at least 32 characters long" in error_msg

    def test_secret_key_placeholder_value(self, monkeypatch):
        """Test SECRET_KEY rejects placeholder values."""
        placeholders = [
            "generate-with-openssl-rand-hex-32",
            "CHANGE_ME_32_CHARS_MIN",
            "your-secret-key-here"
        ]

        for placeholder in placeholders:
            monkeypatch.setenv("SECRET_KEY", placeholder)
            monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
            monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
            monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
            monkeypatch.setenv("REDDIT_USERNAME", "testuser")
            monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
            monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

            with pytest.raises(ValidationError) as exc_info:
                Settings()

            error_msg = str(exc_info.value)
            assert "placeholder" in error_msg.lower() or "secure random value" in error_msg.lower()

    def test_secret_key_valid(self, monkeypatch):
        """Test SECRET_KEY accepts valid value."""
        valid_key = "a" * 32  # 32 character key
        monkeypatch.setenv("SECRET_KEY", valid_key)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        settings = Settings()
        assert settings.secret_key == valid_key


class TestDatabaseURLValidation:
    """Test DATABASE_URL validation."""

    def test_database_url_empty(self, monkeypatch):
        """Test DATABASE_URL cannot be empty."""
        monkeypatch.setenv("DATABASE_URL", "")
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "DATABASE_URL" in error_msg

    def test_database_url_invalid_scheme(self, monkeypatch):
        """Test DATABASE_URL must have valid scheme."""
        monkeypatch.setenv("DATABASE_URL", "mysql://localhost/db")  # Not supported
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "must start with one of" in error_msg.lower()

    def test_database_url_valid_sqlite(self, monkeypatch):
        """Test DATABASE_URL accepts SQLite."""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        settings = Settings()
        assert settings.database_url == "sqlite+aiosqlite:///./data/test.db"

    def test_database_url_valid_postgresql(self, monkeypatch):
        """Test DATABASE_URL accepts PostgreSQL."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        settings = Settings()
        assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/db"


class TestRedditCredentialsValidation:
    """Test Reddit credentials validation."""

    def test_reddit_credentials_missing(self, monkeypatch):
        """Test Reddit credentials are required."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "")  # Missing
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "REDDIT_CLIENT_ID" in error_msg

    def test_reddit_credentials_placeholder(self, monkeypatch):
        """Test Reddit credentials reject placeholders."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "your_client_id_here")  # Placeholder
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "placeholder" in error_msg.lower()

    def test_reddit_user_agent_placeholder(self, monkeypatch):
        """Test Reddit user agent rejects placeholders."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "python:MyRedditBot:v1.0 (by /u/YourUsername)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "placeholder" in error_msg.lower()

    def test_reddit_credentials_valid(self, monkeypatch):
        """Test valid Reddit credentials are accepted."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "abc123def456")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "xyz789uvw012")
        monkeypatch.setenv("REDDIT_USER_AGENT", "python:TestBot:v1.0 (by /u/testuser)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "securepassword123")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        settings = Settings()
        assert settings.reddit_client_id == "abc123def456"
        assert settings.reddit_client_secret == "xyz789uvw012"


class TestOpenRouterValidation:
    """Test OpenRouter API key validation."""

    def test_openrouter_key_missing(self, monkeypatch):
        """Test OpenRouter API key is required."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "")  # Missing

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "OPENROUTER_API_KEY" in error_msg

    def test_openrouter_key_placeholder(self, monkeypatch):
        """Test OpenRouter key rejects placeholders."""
        placeholders = [
            "sk-or-v1-your-api-key-here",
            "sk-or-v1-...",
            "YOUR_KEY_HERE"
        ]

        for placeholder in placeholders:
            monkeypatch.setenv("SECRET_KEY", "a" * 32)
            monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
            monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
            monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
            monkeypatch.setenv("REDDIT_USERNAME", "testuser")
            monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
            monkeypatch.setenv("OPENROUTER_API_KEY", placeholder)

            with pytest.raises(ValidationError) as exc_info:
                Settings()

            error_msg = str(exc_info.value)
            assert "placeholder" in error_msg.lower()

    def test_openrouter_key_valid(self, monkeypatch):
        """Test valid OpenRouter key is accepted."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-abc123def456")

        settings = Settings()
        assert settings.openrouter_api_key == "sk-or-v1-abc123def456"


class TestCORSValidation:
    """Test CORS configuration validation."""

    def test_cors_origins_json_array(self, monkeypatch):
        """Test CORS origins accepts JSON array."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000","https://app.example.com"]')

        settings = Settings()
        assert settings.cors_origins == ["http://localhost:3000", "https://app.example.com"]

    def test_cors_origins_default(self, monkeypatch):
        """Test CORS origins has sensible default."""
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        settings = Settings()
        assert "http://localhost:3000" in settings.cors_origins


class TestConfigurationStartupValidation:
    """Test app won't start with bad configuration."""

    def test_app_fails_with_invalid_config(self, monkeypatch):
        """Test application startup fails with invalid config."""
        # Set invalid SECRET_KEY
        monkeypatch.setenv("SECRET_KEY", "short")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        # Should raise ValidationError on Settings initialization
        with pytest.raises(ValidationError):
            Settings()

    def test_validation_error_messages_actionable(self, monkeypatch):
        """Test validation errors provide actionable messages."""
        monkeypatch.setenv("SECRET_KEY", "short")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test:agent:v1.0 (by /u/test)")
        monkeypatch.setenv("REDDIT_USERNAME", "testuser")
        monkeypatch.setenv("REDDIT_PASSWORD", "testpass")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)

        # Error should mention how to fix it
        assert "openssl rand -hex 32" in error_msg.lower() or "32 characters" in error_msg.lower()
