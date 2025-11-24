"""API v1 endpoints"""

from app.api.v1 import health, auth, protected

__all__ = ["health", "auth", "protected"]
