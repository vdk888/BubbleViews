import requests
import json

# Check OpenAPI spec
r = requests.get("http://localhost:8000/api/v1/openapi.json")
data = r.json()
personas_path = data.get("paths", {}).get("/api/v1/personas", {})
print("OpenAPI Methods for /api/v1/personas:", list(personas_path.keys()))

# Also check the test endpoint
test_path = data.get("paths", {}).get("/api/v1/personas/test", {})
print("OpenAPI Methods for /api/v1/personas/test:", list(test_path.keys()))

# List all persona-related paths
print("\nAll persona-related paths:")
for path, methods in data.get("paths", {}).items():
    if "persona" in path.lower():
        print(f"  {path}: {list(methods.keys())}")
