"""
Seed admin user for dashboard authentication.

Creates a default admin user with username "admin" and password "changeme123".
This script is idempotent - it will not create duplicate users if run multiple times.

Usage:
    python scripts/seed_admin.py

Security:
    IMPORTANT: Change the default password immediately after first login!
    The default credentials are publicly known and insecure.
"""

import asyncio
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.core.database import async_session_maker
from app.core.security import get_password_hash
from app.models.user import Admin


async def seed_admin():
    """
    Create default admin user if it doesn't exist.

    Creates admin user with:
        - Username: admin
        - Password: changeme123 (MUST be changed in production!)

    Returns:
        None

    Prints:
        Success or skip message
    """
    async with async_session_maker() as session:
        try:
            # Check if admin already exists
            result = await session.execute(
                select(Admin).where(Admin.username == "admin")
            )
            existing_admin = result.scalar_one_or_none()

            if existing_admin:
                print("Admin user already exists. Skipping...")
                return

            # Create new admin user
            admin = Admin(
                username="admin",
                hashed_password=get_password_hash("changeme123")
            )

            session.add(admin)
            await session.commit()

            print("Admin user created successfully!")
            print("Username: admin")
            print("Password: changeme123")
            print("")
            print("WARNING: Please change this password immediately after first login!")
            print("This default password is publicly known and insecure.")

        except Exception as e:
            await session.rollback()
            print(f"Error creating admin user: {e}")
            raise


if __name__ == "__main__":
    print("Seeding admin user...")
    asyncio.run(seed_admin())
    print("Done!")
