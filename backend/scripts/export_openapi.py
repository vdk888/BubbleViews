"""
Export OpenAPI schema to docs/api/ directory.

Generates both JSON and YAML versions of the OpenAPI specification
from the FastAPI application.
"""

import json
import yaml
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def export_openapi():
    """Export OpenAPI schema to JSON and YAML files."""
    # Import app to trigger all route registrations
    from app.main import app

    # Get OpenAPI schema from FastAPI
    openapi_schema = app.openapi()

    # Define output paths
    docs_dir = Path(__file__).parent.parent.parent / "docs" / "api"
    docs_dir.mkdir(parents=True, exist_ok=True)

    json_path = docs_dir / "openapi.json"
    yaml_path = docs_dir / "openapi.yaml"

    # Write JSON
    with open(json_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"✓ OpenAPI JSON exported to: {json_path}")

    # Write YAML
    with open(yaml_path, "w") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False)
    print(f"✓ OpenAPI YAML exported to: {yaml_path}")

    # Print summary
    print("\nAPI Summary:")
    print(f"  Title: {openapi_schema['info']['title']}")
    print(f"  Version: {openapi_schema['info']['version']}")
    print(f"  Endpoints: {len(openapi_schema['paths'])}")
    print(f"  Schemas: {len(openapi_schema.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    export_openapi()
