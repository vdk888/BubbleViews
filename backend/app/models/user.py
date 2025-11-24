"""
Admin user model for authentication.

Provides user authentication and authorization for the dashboard.
For MVP, supports a single admin user with username/password auth.
"""

from sqlalchemy import Column, String

from app.models.base import Base, UUIDMixin, TimestampMixin


class Admin(Base, UUIDMixin, TimestampMixin):
    """
    Admin user model for dashboard authentication.

    Stores admin credentials for accessing the control panel.
    For MVP, this is a simple username/password model.
    In production, extend with roles, permissions, MFA, etc.

    Attributes:
        id: UUID primary key (from UUIDMixin)
        username: Unique username for login
        hashed_password: Bcrypt-hashed password (never store plaintext)
        created_at: Timestamp when admin was created (from TimestampMixin)
        updated_at: Timestamp when admin was last updated (from TimestampMixin)

    Security considerations:
        - Never log or expose hashed_password
        - Use bcrypt with 12+ rounds for password hashing
        - Passwords should be validated for strength before hashing
        - Consider adding email, MFA, and password reset in production
    """

    __tablename__ = "admins"

    username = Column(
        String,
        nullable=False,
        unique=True,
        index=True,
        doc="Unique username for authentication"
    )

    hashed_password = Column(
        String,
        nullable=False,
        doc="Bcrypt-hashed password (never store plaintext)"
    )

    def __repr__(self) -> str:
        """
        String representation of Admin.

        Returns:
            String representation (without sensitive data)
        """
        return f"Admin(id={self.id!r}, username={self.username!r})"
