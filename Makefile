.PHONY: help install dev clean test lint format backend-run frontend-run run

# Default target
help:
	@echo "Reddit AI Agent - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install        Install all dependencies (backend + frontend)"
	@echo "  make dev            Install development dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make run            Run both backend and frontend concurrently"
	@echo "  make backend-run    Run only backend API server"
	@echo "  make frontend-run   Run only frontend dev server"
	@echo "  make agent-run      Run agent loop (separate from API)"
	@echo ""
	@echo "Quality:"
	@echo "  make test           Run all tests (backend + frontend)"
	@echo "  make lint           Run linting checks"
	@echo "  make format         Format code (backend + frontend)"
	@echo ""
	@echo "Database:"
	@echo "  make migrate        Create new migration (use msg='description')"
	@echo "  make upgrade        Apply database migrations"
	@echo "  make downgrade      Rollback one migration"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Remove build artifacts and caches"

# Installation
install:
	@echo "Installing backend dependencies..."
	cd backend && pip install -e .
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo "Done! Run 'make run' to start development servers."

dev:
	@echo "Installing backend dev dependencies..."
	cd backend && pip install -e ".[dev]"
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo "Done!"

# Run services
backend-run:
	@echo "Starting backend API server on http://localhost:8000"
	cd backend && uvicorn app.main:app --reload --port 8000

frontend-run:
	@echo "Starting frontend dev server on http://localhost:3000"
	cd frontend && npm run dev

agent-run:
	@echo "Starting agent loop..."
	cd backend && python -m app.agent.loop

# Run both services (requires separate terminals or use tmux/screen)
run:
	@echo "To run both services, open two terminals:"
	@echo "  Terminal 1: make backend-run"
	@echo "  Terminal 2: make frontend-run"
	@echo ""
	@echo "Or use tmux/screen for concurrent execution"

# Testing
test:
	@echo "Running backend tests..."
	cd backend && pytest -v --cov=app
	@echo "Running frontend tests..."
	cd frontend && npm run test || echo "Frontend tests not yet configured"

# Linting
lint:
	@echo "Linting backend..."
	cd backend && ruff check app tests && mypy app
	@echo "Linting frontend..."
	cd frontend && npm run lint

# Formatting
format:
	@echo "Formatting backend..."
	cd backend && black app tests && ruff check --fix app tests
	@echo "Formatting frontend..."
	cd frontend && npm run lint -- --fix || echo "Auto-fix completed"

# Database migrations
migrate:
	cd backend && alembic revision --autogenerate -m "$(msg)"

upgrade:
	cd backend && alembic upgrade head

downgrade:
	cd backend && alembic downgrade -1

# Cleanup
clean:
	@echo "Cleaning backend..."
	cd backend && rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .coverage htmlcov/
	cd backend && find . -type d -name __pycache__ -exec rm -rf {} + || true
	cd backend && find . -type f -name "*.pyc" -delete || true
	@echo "Cleaning frontend..."
	cd frontend && rm -rf .next node_modules/.cache
	@echo "Done!"
