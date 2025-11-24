"""
Generate OpenAPI specification from FastAPI app.

This script generates the OpenAPI schema in both JSON and YAML formats
and exports them to the docs/api directory.
"""

import os
import sys
import json
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Set minimal environment variables for app initialization
# Use temporary file database to avoid async driver issues during schema generation
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./temp_openapi.db")
os.environ.setdefault("REDDIT_CLIENT_ID", "placeholder")
os.environ.setdefault("REDDIT_CLIENT_SECRET", "placeholder")
os.environ.setdefault("REDDIT_USER_AGENT", "python:PlaceholderApp:v1.0 (by /u/PlaceholderUser)")
os.environ.setdefault("REDDIT_USERNAME", "placeholder")
os.environ.setdefault("REDDIT_PASSWORD", "placeholder")
os.environ.setdefault("OPENROUTER_API_KEY", "placeholder")
os.environ.setdefault("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
os.environ.setdefault("SECRET_KEY", "placeholder_secret_key_at_least_32_characters_long")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("TARGET_SUBREDDITS", '["test", "bottest"]')
os.environ.setdefault("AUTO_POSTING_ENABLED", "false")

# Import app after setting environment variables
from app.main import app


def generate_openapi_spec():
    """Generate OpenAPI specification in JSON and YAML formats."""

    # Get OpenAPI schema
    openapi_schema = app.openapi()

    # Add descriptions to improve documentation
    openapi_schema["info"]["description"] = """
# Reddit AI Agent API

Autonomous Reddit AI Agent with Belief Graph and Memory System.

## Features

- **Health Monitoring**: Liveness and readiness probes for deployment
- **Authentication**: JWT-based authentication for admin dashboard
- **Settings Management**: Persona-scoped configuration storage
- **Agent Status**: Monitor agent loop status and activity

## Authentication

Most endpoints require authentication via JWT token. To authenticate:

1. Obtain a token by POSTing credentials to `/api/v1/auth/token`
2. Include the token in the `Authorization` header: `Bearer <token>`

## Persona Isolation

All data is scoped to personas (Reddit accounts). Settings and configurations
are isolated per persona using the `persona_id` parameter.

## Rate Limiting

- Auth endpoints: 10 requests/minute per IP
- Other endpoints: 60 requests/minute per IP

## Observability

All requests include:
- **X-Request-ID**: Correlation ID for distributed tracing
- **Structured JSON logs**: Timestamp, path, status, latency

## Architecture

- **Backend**: FastAPI + Python 3.11
- **Database**: SQLite (MVP), Postgres-ready contracts
- **Auth**: JWT tokens with bcrypt password hashing
- **LLM**: OpenRouter API (model-agnostic)
- **Memory**: FAISS for semantic retrieval
"""

    # Add security scheme documentation
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}

    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}

    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT token obtained from /api/v1/auth/token endpoint"
    }

    # Ensure output directory exists
    docs_api_dir = backend_dir.parent / "docs" / "api"
    docs_api_dir.mkdir(parents=True, exist_ok=True)

    # Write JSON format
    json_path = docs_api_dir / "openapi.json"
    with open(json_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"Generated OpenAPI JSON: {json_path}")

    # Try to write YAML format (if PyYAML is available)
    try:
        import yaml
        yaml_path = docs_api_dir / "openapi.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False)
        print(f"Generated OpenAPI YAML: {yaml_path}")
    except ImportError:
        print("PyYAML not installed, skipping YAML generation")
        print("Install with: pip install pyyaml")

    # Print summary
    print("\nOpenAPI Specification Summary:")
    print(f"  Title: {openapi_schema['info']['title']}")
    print(f"  Version: {openapi_schema['info']['version']}")
    print(f"  Paths: {len(openapi_schema.get('paths', {}))}")
    print(f"  Components: {len(openapi_schema.get('components', {}).get('schemas', {}))}")

    # List all endpoints
    print("\nEndpoints:")
    for path, methods in openapi_schema.get("paths", {}).items():
        for method in methods.keys():
            if method != "parameters":
                print(f"  {method.upper():6} {path}")

    return openapi_schema


if __name__ == "__main__":
    print("Generating OpenAPI specification...\n")
    generate_openapi_spec()
    print("\nDone!")
