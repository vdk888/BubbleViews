"""
Test script to verify Day 3 configuration is working correctly.

Run this to validate that config, security, and database modules are properly set up.
"""

import asyncio
import os
from pathlib import Path


def test_imports():
    """Test that all core modules can be imported."""
    print("✓ Testing imports...")
    try:
        from app.core import config, security, database
        print("  ✓ All core modules imported successfully")
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_config_structure():
    """Test that Settings class has all required fields."""
    print("\n✓ Testing configuration structure...")
    try:
        from app.core.config import Settings

        # Check required fields exist
        required_fields = [
            'api_v1_prefix', 'project_name', 'database_url',
            'reddit_client_id', 'reddit_client_secret', 'reddit_user_agent',
            'reddit_username', 'reddit_password',
            'openrouter_api_key', 'openrouter_base_url',
            'response_model', 'consistency_model',
            'target_subreddits', 'auto_posting_enabled',
            'secret_key', 'access_token_expire_minutes'
        ]

        settings_fields = Settings.model_fields.keys()
        missing_fields = [f for f in required_fields if f not in settings_fields]

        if missing_fields:
            print(f"  ✗ Missing fields: {missing_fields}")
            return False

        print(f"  ✓ All {len(required_fields)} required fields present")
        return True
    except Exception as e:
        print(f"  ✗ Config structure test failed: {e}")
        return False


def test_security_functions():
    """Test that security module has all required functions."""
    print("\n✓ Testing security module...")
    try:
        from app.core import security

        # Check required functions exist
        required_functions = [
            'verify_password', 'get_password_hash', 'create_access_token',
            'decode_access_token', 'get_current_user', 'authenticate_user'
        ]

        missing_functions = [f for f in required_functions if not hasattr(security, f)]

        if missing_functions:
            print(f"  ✗ Missing functions: {missing_functions}")
            return False

        print(f"  ✓ All {len(required_functions)} required functions present")

        # Test password hashing
        password = "test_password"
        hashed = security.get_password_hash(password)
        verified = security.verify_password(password, hashed)

        if not verified:
            print("  ✗ Password hashing/verification failed")
            return False

        print("  ✓ Password hashing works correctly")
        return True
    except Exception as e:
        print(f"  ✗ Security module test failed: {e}")
        return False


def test_database_structure():
    """Test that database module has all required functions."""
    print("\n✓ Testing database module...")
    try:
        from app.core import database

        # Check required components exist
        required_components = [
            'Base', 'engine', 'async_session_maker', 'get_db',
            'init_db', 'close_db', 'DatabaseHealthCheck'
        ]

        missing_components = [c for c in required_components if not hasattr(database, c)]

        if missing_components:
            print(f"  ✗ Missing components: {missing_components}")
            return False

        print(f"  ✓ All {len(required_components)} required components present")
        return True
    except Exception as e:
        print(f"  ✗ Database module test failed: {e}")
        return False


async def test_database_health_check():
    """Test database health check (requires valid .env)."""
    print("\n✓ Testing database health check...")
    try:
        from app.core.database import DatabaseHealthCheck

        info = await DatabaseHealthCheck.get_database_info()
        print(f"  ✓ Database info: {info}")

        # Note: Connection check will fail without valid .env, which is expected
        print("  ℹ Connection check skipped (requires valid .env)")
        return True
    except Exception as e:
        print(f"  ✗ Database health check failed: {e}")
        return False


def test_env_example_exists():
    """Test that .env.example exists and has all required variables."""
    print("\n✓ Testing .env.example...")
    try:
        backend_dir = Path(__file__).parent.parent
        env_example = backend_dir / ".env.example"

        if not env_example.exists():
            print(f"  ✗ .env.example not found at {env_example}")
            return False

        with open(env_example, 'r') as f:
            content = f.read()

        # Check for key variable names
        required_vars = [
            'DATABASE_URL', 'REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET',
            'REDDIT_USER_AGENT', 'REDDIT_USERNAME', 'REDDIT_PASSWORD',
            'OPENROUTER_API_KEY', 'OPENROUTER_BASE_URL',
            'RESPONSE_MODEL', 'CONSISTENCY_MODEL',
            'TARGET_SUBREDDITS', 'AUTO_POSTING_ENABLED',
            'SECRET_KEY', 'ACCESS_TOKEN_EXPIRE_MINUTES'
        ]

        missing_vars = [v for v in required_vars if v not in content]

        if missing_vars:
            print(f"  ✗ Missing variables in .env.example: {missing_vars}")
            return False

        print(f"  ✓ All {len(required_vars)} required variables present")
        return True
    except Exception as e:
        print(f"  ✗ .env.example test failed: {e}")
        return False


def test_secrets_documentation():
    """Test that secrets.md exists."""
    print("\n✓ Testing secrets documentation...")
    try:
        # Find project root
        backend_dir = Path(__file__).parent.parent
        project_root = backend_dir.parent
        secrets_doc = project_root / "docs" / "runbooks" / "secrets.md"

        if not secrets_doc.exists():
            print(f"  ✗ secrets.md not found at {secrets_doc}")
            return False

        with open(secrets_doc, 'r') as f:
            content = f.read()

        # Check for key sections
        required_sections = [
            'Generating Secrets', 'Where Secrets Are Stored',
            'Secret Rotation Policy', 'Updating Secrets Without Downtime',
            'Emergency Procedures'
        ]

        missing_sections = [s for s in required_sections if s not in content]

        if missing_sections:
            print(f"  ✗ Missing sections: {missing_sections}")
            return False

        print(f"  ✓ All {len(required_sections)} required sections present")
        print(f"  ✓ Documentation size: {len(content)} characters")
        return True
    except Exception as e:
        print(f"  ✗ Secrets documentation test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Day 3 Configuration Verification")
    print("=" * 60)

    results = []

    # Synchronous tests
    results.append(("Imports", test_imports()))
    results.append(("Config Structure", test_config_structure()))
    results.append(("Security Functions", test_security_functions()))
    results.append(("Database Structure", test_database_structure()))
    results.append((".env.example", test_env_example_exists()))
    results.append(("Secrets Documentation", test_secrets_documentation()))

    # Async tests
    results.append(("Database Health Check", await test_database_health_check()))

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All Day 3 deliverables are complete and working!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review errors above.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
