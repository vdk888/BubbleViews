.PHONY: install dev test lint format migrate upgrade downgrade clean run

# Install production dependencies
install:
	pip install -e .

# Install development dependencies
dev:
	pip install -e ".[dev]"

# Run tests with coverage
test:
	pytest -v --cov=app --cov-report=term-missing

# Run linting checks
lint:
	ruff check app tests
	mypy app

# Format code
format:
	black app tests
	ruff check --fix app tests

# Create new migration
migrate:
	alembic revision --autogenerate -m "$(msg)"

# Apply migrations
upgrade:
	alembic upgrade head

# Rollback one migration
downgrade:
	alembic downgrade -1

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov/

# Run development server
run:
	uvicorn app.main:app --reload --port 8000

# Run agent loop (separate from API)
run-agent:
	python -m app.agent.loop
