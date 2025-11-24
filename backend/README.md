# Reddit AI Agent - Backend

FastAPI backend for the autonomous Reddit engagement agent with belief management and moderation.

## Architecture

- **Framework**: FastAPI with Python 3.11+
- **Database**: SQLite with JSON1 extension (upgradeable to PostgreSQL)
- **LLM Provider**: OpenRouter API (GPT-5.1-mini + Claude-4.5-Haiku)
- **Vector Search**: FAISS (in-memory) with sentence-transformers
- **Async Support**: asyncpraw, aiosqlite, httpx

## Project Structure

```
backend/
├── app/
│   ├── core/               # Configuration and infrastructure
│   ├── api/v1/             # API endpoints
│   ├── services/           # Business logic
│   │   └── interfaces/     # Service contracts (ABCs)
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic validation schemas
│   └── agent/              # Autonomous agent logic
├── data/                   # SQLite database + FAISS index
├── tests/                  # Test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── alembic/                # Database migrations
└── pyproject.toml          # Dependencies and configuration
```

## Setup

### Prerequisites

- Python 3.11 or higher
- pip or uv package manager

### Installation

1. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   make dev  # Installs both production and dev dependencies
   # Or: pip install -e ".[dev]"
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials (Reddit API, OpenRouter API key)
   ```

4. **Initialize database**:
   ```bash
   make upgrade  # Runs alembic upgrade head
   ```

## Development

### Running the API server

```bash
make run  # Starts uvicorn with auto-reload on port 8000
```

API will be available at:
- API docs: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc

### Running the agent loop

```bash
make run-agent  # Starts autonomous agent process
```

### Code quality

```bash
make format  # Format code with black and ruff
make lint    # Run linting checks (ruff, mypy)
make test    # Run tests with coverage
```

### Database migrations

```bash
# Create new migration
make migrate msg="description of changes"

# Apply migrations
make upgrade

# Rollback one migration
make downgrade
```

## Configuration

Configuration is managed via Pydantic Settings in `app/core/config.py`. All settings can be overridden via environment variables.

Key settings:
- `DATABASE_URL`: SQLite path (default: `sqlite+aiosqlite:///./data/reddit_agent.db`)
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`: Reddit API credentials
- `OPENROUTER_API_KEY`: OpenRouter API key
- `RESPONSE_MODEL`: LLM model for responses (default: `openai/gpt-5.1-mini`)
- `CONSISTENCY_MODEL`: LLM model for consistency checks (default: `anthropic/claude-4.5-haiku`)

## API Endpoints

### Core Endpoints
- `GET /health` - Health check
- `GET /api/v1/activity` - Recent agent activity
- `GET /api/v1/beliefs` - Belief graph
- `GET /api/v1/moderation/pending` - Moderation queue
- `POST /api/v1/moderation/approve` - Approve pending post
- `PUT /api/v1/settings` - Update agent configuration

See API documentation at `/docs` for complete endpoint reference.

## Testing

```bash
# Run all tests
make test

# Run specific test file
pytest tests/unit/test_llm_client.py

# Run with verbose output
pytest -v

# Run tests matching pattern
pytest -k "test_belief"
```

## Deployment

### Local Development
```bash
make run  # API server
make run-agent  # Agent loop (separate terminal)
```

### Production (DigitalOcean Droplet)
```bash
# On server
git clone <repo>
cd backend
python -m venv venv
source venv/bin/activate
pip install -e .
alembic upgrade head

# Set up systemd service (see docs/runbooks/deployment.md)
sudo systemctl start reddit-agent
sudo systemctl enable reddit-agent
```

## Architecture Decisions

See `docs/decisions/ADR-001-tech-stack.md` for detailed rationale on technology choices.

Key decisions:
- SQLite for MVP (upgradeable to PostgreSQL)
- OpenRouter for model flexibility and cost optimization
- In-memory FAISS for vector search (< 10K interactions)
- Contract-first design with ABC interfaces

## Cost Optimization

Estimated monthly costs:
- LLM (10 responses/day): ~$0.22/month
- Infrastructure: $6/month (DigitalOcean droplet)
- Total: ~$6.25/month

## Troubleshooting

### Database locked errors
Enable WAL mode (should be default):
```sql
sqlite3 data/reddit_agent.db
> PRAGMA journal_mode=WAL;
```

### Import errors
Ensure you're in the backend directory and virtual environment is activated:
```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
```

### Migration conflicts
```bash
# Reset database (WARNING: destroys data)
rm data/reddit_agent.db
alembic upgrade head
```

## Contributing

1. Create feature branch from `main`
2. Run `make format` before committing
3. Ensure `make lint` and `make test` pass
4. Write tests for new features
5. Update API documentation if endpoints change

## References

- [Technical Specification](../docs/MVP_Reddit_AI_Agent_Technical_Specification.md)
- [Architecture Build Plan](../docs/MVP%20Reddit%20AI%20Agent%20-%20Architecture%20Build.md)
- [Quality Guidelines](../docs/0_dev.md)
- [ADR-001: Tech Stack](../docs/decisions/ADR-001-tech-stack.md)
