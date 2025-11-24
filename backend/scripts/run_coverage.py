"""
Run pytest with coverage reporting.

This script runs the test suite and generates coverage reports.
"""

import subprocess
import sys
from pathlib import Path

# Change to backend directory
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def run_coverage():
    """Run pytest with coverage."""

    print("Installing pytest-cov if needed...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pytest-cov"], check=False)

    print("\nRunning tests with coverage...\n")

    # Run pytest with coverage
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=app",
            "--cov-report=term-missing",
            "--cov-report=html",
            "--cov-report=json",
            "-v",
            "tests/integration/",
            "tests/unit/",
            "tests/test_health_endpoints.py",
            "tests/test_probes.py",
            "tests/test_middleware.py",
            "tests/test_logging_config.py",
        ],
        cwd=backend_dir,
        capture_output=False,
    )

    print(f"\n{'='*70}")
    print("Coverage report generated:")
    print(f"  - Terminal: (see above)")
    print(f"  - HTML: {backend_dir / 'htmlcov' / 'index.html'}")
    print(f"  - JSON: {backend_dir / 'coverage.json'}")
    print(f"{'='*70}\n")

    return result.returncode


if __name__ == "__main__":
    exit_code = run_coverage()
    sys.exit(exit_code)
