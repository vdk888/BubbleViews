# BubbleViews - Autonomous Reddit AI Agent

An autonomous AI agent that engages on Reddit with a consistent persona, evolving belief system, and long-term memory. The agent maintains its own personality, tracks its convictions, and remembers past interactions to ensure consistency across sessions.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16.0-black.svg)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🎯 Key Features

### 🤖 Autonomous Agent
- **Perception-Decision-Action Loop**: Continuously monitors Reddit, makes decisions, and executes actions
- **Multi-Persona Support**: Architecture supports multiple Reddit accounts with separate personalities
- **Context-Aware**: Retrieves relevant memories and beliefs before responding
- **Moderation Layer**: Manual review queue or auto-posting mode with content evaluation

### 🧠 Belief Management
- **Structured Belief Graph**: Nodes and edges representing convictions with confidence scores
- **Bayesian Updates**: Log-odds transformation for smooth, evidence-based confidence adjustments
- **Stance Versioning**: Complete audit trail of belief evolution over time
- **Evidence Linking**: Track sources (Reddit comments, external links, notes) with strength ratings

### 💾 Memory System
- **Episodic Memory**: Remembers all past Reddit interactions (posts, comments, replies)
- **Semantic Retrieval**: FAISS-based vector search over past interactions for consistency
- **Self-Consistency**: Searches prior responses to avoid contradicting itself
- **Token Budget Management**: Intelligent context pruning (max 3000 tokens)

### 📊 Control Dashboard
- **Activity Timeline**: Real-time feed of agent actions with karma tracking
- **Belief Graph Visualization**: Interactive force-directed graph of convictions
- **Moderation Console**: Review queue with approve/reject actions
- **Governor Chat**: Conversational interface to query agent reasoning
- **Settings Panel**: Auto-posting toggle, persona configuration

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                       │
│  Activity Feed | Belief Graph | Moderation | Governor | Settings │
└───────────────────────────────┬─────────────────────────────────┘
                                │ REST API
┌───────────────────────────────┴─────────────────────────────────┐
│                     Backend (FastAPI)                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Agent Loop (Autonomous)                      │  │
│  │  Perception → Retrieval → Decision → Moderation → Action  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ├─ Services: Memory, Reddit Client, LLM, Belief Updater        │
│  ├─ Repositories: Data access layer (contract-based)            │
│  └─ Models: SQLAlchemy ORM (Personas, Beliefs, Interactions)    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
   ┌────▼─────┐         ┌──────▼──────┐        ┌──────▼──────┐
   │ SQLite   │         │ FAISS Index │        │ OpenRouter  │
   │ Database │         │  (Vectors)  │        │    (LLM)    │
   └──────────┘         └─────────────┘        └─────────────┘
```

### Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) - Async API framework with OpenAPI generation
- [SQLAlchemy](https://www.sqlalchemy.org/) + [aiosqlite](https://aiosqlite.omnilib.dev/) - Async ORM with SQLite
- [asyncpraw](https://asyncpraw.readthedocs.io/) - Async Reddit API wrapper
- [sentence-transformers](https://www.sbert.net/) - Local embedding generation (384-dim)
- [FAISS](https://github.com/facebookresearch/faiss) - In-memory vector search
- [OpenRouter](https://openrouter.ai/) - Model-agnostic LLM gateway

**Frontend**
- [Next.js 16](https://nextjs.org/) - React framework with SSR
- [TypeScript](https://www.typescriptlang.org/) - Type-safe development
- [Tailwind CSS](https://tailwindcss.com/) - Utility-first styling
- [Recharts](https://recharts.org/) - Data visualization

**LLM Models**
- Primary: `openai/gpt-5.1-mini` ($0.15/1M tokens) - Fast response drafting
- Secondary: `anthropic/claude-4.5-haiku` ($0.25/1M tokens) - Consistency checks

## 🚀 Quick Start

### Prerequisites

- Python 3.11+ ([Download](https://www.python.org/downloads/))
- Node.js 20+ ([Download](https://nodejs.org/))
- Reddit API credentials ([Create App](https://www.reddit.com/prefs/apps))
- OpenRouter API key ([Get Key](https://openrouter.ai/keys))

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your credentials:
# - REDDIT_CLIENT_ID
# - REDDIT_CLIENT_SECRET
# - REDDIT_USERNAME
# - REDDIT_PASSWORD
# - OPENROUTER_API_KEY

# Initialize database
alembic upgrade head

# Seed initial data
python scripts/seed_admin.py
python scripts/seed_default_config.py
python scripts/seed_demo.py  # Optional: demo persona with beliefs

# Run API server
uvicorn app.main:app --reload --port 8000
```

API will be available at:
- **Interactive docs**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Set NEXT_PUBLIC_API_URL=http://localhost:8000

# Run development server
npm run dev
```

Dashboard will be available at http://localhost:3000

### Run Agent Loop

```bash
cd backend
source venv/bin/activate

# Start autonomous agent (separate terminal)
python scripts/run_agent.py
```

The agent will continuously monitor Reddit and take actions based on its configuration.

## 📁 Project Structure

```
BubbleViews/
├── backend/                    # FastAPI + Python 3.11
│   ├── app/
│   │   ├── core/              # Config, database, logging, security
│   │   ├── api/v1/            # REST endpoints
│   │   ├── services/          # Business logic
│   │   │   └── interfaces/    # ABC contracts
│   │   ├── models/            # SQLAlchemy ORM
│   │   ├── schemas/           # Pydantic validation
│   │   ├── agent/             # Agent loop logic
│   │   ├── middleware/        # Request ID, logging, rate limiting
│   │   └── repositories/      # Data access layer
│   ├── data/                  # SQLite DB + FAISS index
│   ├── tests/                 # Unit + integration tests
│   ├── alembic/               # Database migrations
│   └── pyproject.toml
├── frontend/                  # Next.js 14 + TypeScript
│   ├── app/                   # Pages
│   │   ├── activity/          # Activity timeline
│   │   ├── beliefs/           # Belief graph visualization
│   │   ├── moderation/        # Review queue
│   │   ├── governor/          # Governor chat interface
│   │   ├── costs/             # Cost monitoring dashboard
│   │   └── settings/          # Configuration panel
│   ├── components/            # Reusable UI components
│   ├── lib/                   # API client (type-safe)
│   └── package.json
├── docs/
│   ├── decisions/             # Architecture Decision Records (ADRs)
│   ├── api/                   # OpenAPI specification
│   ├── architecture/          # System diagrams, data flows
│   ├── runbooks/              # Operations guides
│   ├── completion_reports/    # Implementation phase summaries
│   ├── week2.md               # Foundation services (Week 2)
│   ├── week3.md               # Core agent services (Week 3)
│   └── week4.md               # Agent loop & dashboard (Week 4)
├── CLAUDE.md                  # Claude Code usage guide
└── README.md                  # This file
```

## 🧪 Testing

```bash
cd backend

# Run all tests with coverage
pytest --cov=app --cov-report=term-missing --cov-report=html

# Run specific test file
pytest tests/test_agent_loop.py -v

# Run tests matching pattern
pytest -k "test_belief" -v

# View coverage report
open htmlcov/index.html  # macOS
# or: start htmlcov/index.html  # Windows
```

**Test Coverage**: >80% on core services, models, and API endpoints

## 📖 API Documentation

### Health Endpoints
- `GET /health` - Basic health check
- `GET /health/ready` - Readiness probe (checks DB + OpenRouter)
- `GET /health/agent` - Agent loop status

### Activity Endpoints
- `GET /api/v1/activity?persona_id={id}&limit={n}` - Recent interactions

### Belief Endpoints
- `GET /api/v1/beliefs?persona_id={id}` - Belief graph
- `PUT /api/v1/beliefs/{id}` - Manual belief update
- `POST /api/v1/beliefs/{id}/lock` - Prevent automatic updates
- `POST /api/v1/beliefs/{id}/unlock` - Re-enable updates
- `POST /api/v1/beliefs/{id}/nudge` - Soft confidence adjustments
- `GET /api/v1/beliefs/{id}/history` - Version history

### Moderation Endpoints
- `GET /api/v1/moderation/pending?persona_id={id}` - Review queue
- `POST /api/v1/moderation/approve` - Approve pending post
- `POST /api/v1/moderation/reject` - Reject pending post
- `POST /api/v1/moderation/review` - Evaluate content

### Settings Endpoints
- `GET /api/v1/settings?persona_id={id}` - Agent configuration
- `PUT /api/v1/settings` - Update configuration

### Governor Endpoints
- `POST /api/v1/governor/query` - Conversational queries about agent reasoning
- `POST /api/v1/governor/approve-proposal` - Admin approval for belief changes

Full API documentation available at `/docs` when running the backend.

## 🎛️ Configuration

Configuration is managed via environment variables (Pydantic Settings). See [.env.example](backend/.env.example) for all options.

### Key Settings

**Database**
```env
DATABASE_URL=sqlite+aiosqlite:///./data/reddit_agent.db
```

**Reddit API**
```env
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USERNAME=your_bot_username
REDDIT_PASSWORD=your_bot_password
REDDIT_USER_AGENT=BubbleViews/0.1.0
```

**OpenRouter**
```env
OPENROUTER_API_KEY=your_api_key
RESPONSE_MODEL=openai/gpt-5.1-mini
CONSISTENCY_MODEL=anthropic/claude-4.5-haiku
```

**Agent Behavior**
```env
AGENT_POLL_INTERVAL=300  # seconds between checks
AGENT_AUTO_POSTING_ENABLED=false  # manual review mode by default
MAX_CONTEXT_TOKENS=3000  # token budget for retrieval
```

## 💡 Key Concepts

### Belief Graph

The agent maintains a structured graph of its beliefs:
- **Nodes**: Individual beliefs (statements + confidence scores)
- **Edges**: Relationships (supports, contradicts, depends_on)
- **Stance Versions**: Historical snapshots of belief evolution
- **Evidence Links**: Sources backing each belief (Reddit comments, external links, notes)

Example belief:
```json
{
  "id": "belief_123",
  "persona_id": "persona_1",
  "topic": "climate_change",
  "statement": "Carbon emissions are the primary driver of global warming",
  "confidence": 0.92,
  "status": "current",
  "evidence_links": [
    {
      "source_type": "external_link",
      "source_id": "https://ipcc.ch/report",
      "strength": "strong"
    }
  ]
}
```

### Bayesian Belief Updates

Confidence updates use log-odds transformation for smooth, diminishing-returns behavior:

```python
log_odds = log(confidence / (1 - confidence))
new_log_odds = log_odds + (delta * 5)  # delta: 0.05 (weak), 0.10 (moderate), 0.20 (strong)
new_confidence = 1 / (1 + exp(-new_log_odds))
```

This ensures:
- Strong evidence required to push confidence near extremes (0 or 1)
- Incremental updates have larger effects at mid-confidence
- Prevents overconfident assertions without strong backing

### Retrieval Pipeline

Before responding, the agent assembles context from multiple sources:

1. **Persona config** - Core personality traits, values, tone
2. **Belief graph** - Current stances + relations
3. **Past comments** - Semantic search via FAISS (top-k=5)
4. **Live Reddit thread** - Post/comment context
5. **Moderation status** - Auto/manual mode, content flags

Token budget enforced with priority pruning:
1. Persona config (always included)
2. High-confidence beliefs
3. Recent statements
4. Low-confidence or deprecated stances

### Moderation Modes

- **Manual Mode** (`auto_posting_enabled=false`): All drafts go to review queue
- **Auto Mode** (`auto_posting_enabled=true`): Drafts auto-posted after consistency checks

Content evaluation checks:
- Banned keywords (toxicity, spam patterns)
- Length limits (min 20 chars, max 10,000)
- Consistency with beliefs (LLM-based check)
- Reddit TOS compliance

## 🚢 Deployment

### Development (Local)

```bash
# Terminal 1: Backend API
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2: Agent loop
cd backend && python scripts/run_agent.py

# Terminal 3: Frontend
cd frontend && npm run dev
```

### Production

**Backend + Agent**: DigitalOcean droplet ($6/month)
```bash
# On server
git clone https://github.com/yourusername/BubbleViews.git
cd BubbleViews/backend
python -m venv venv
source venv/bin/activate
pip install -e .
alembic upgrade head

# Set up systemd service (see docs/runbooks/deployment.md)
sudo systemctl start reddit-agent-api
sudo systemctl start reddit-agent-loop
sudo systemctl enable reddit-agent-api
sudo systemctl enable reddit-agent-loop
```

**Frontend**: Vercel (free tier)
```bash
# Connect GitHub repo to Vercel
# Set environment variables in Vercel dashboard
# Deploy automatically on push to main
```

### Cost Estimate

- **Infrastructure**: $6/month (DigitalOcean droplet)
- **LLM (10 responses/day)**: ~$0.22/month
- **Frontend**: $0/month (Vercel free tier)
- **Total**: ~$6.25/month

## 🔧 Development

### Code Quality

```bash
cd backend

# Format code
black . && ruff check --fix .

# Type checking
mypy app/

# Linting
ruff check .
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add new field to beliefs"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Makefile Commands

Backend includes a Makefile for common tasks:

```bash
make dev         # Install dev dependencies
make run         # Start API server
make run-agent   # Start agent loop
make test        # Run tests with coverage
make format      # Format code
make lint        # Run linting checks
make migrate     # Create new migration
make upgrade     # Apply migrations
make downgrade   # Rollback migration
```

## 📚 Documentation

Comprehensive documentation is available in the [docs/](docs/) directory:

### Architecture
- [Technical Specification](docs/MVP_Reddit_AI_Agent_Technical_Specification.md) - Full system design
- [Architecture Build Plan](docs/MVP%20Reddit%20AI%20Agent%20-%20Architecture%20Build.md) - Phase-by-phase implementation
- [System Diagram](docs/architecture/system-diagram.md) - Mermaid diagrams of data flows

### Development
- [0_dev.md](docs/0_dev.md) - Engineering quality guidelines
- [ADR-001: Tech Stack](docs/decisions/ADR-001-tech-stack.md) - Technology decisions
- [Week 2 Plan](docs/week2.md) - Foundation services
- [Week 3 Plan](docs/week3.md) - Core agent services
- [Week 4 Plan](docs/week4.md) - Agent loop & dashboard

### Operations
- [Deployment Runbook](docs/runbooks/deployment.md)
- [Database Migrations](docs/runbooks/database-migrations.md)
- [LLM Usage Guide](docs/runbooks/llm-usage.md)
- [Secrets Management](docs/runbooks/secrets.md)

### Brainstorming
- [Original Ideation](docs/brainstorming.md) - Concept exploration and UX ideas

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests and ensure they pass (`make test`)
4. Format code (`make format`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Standards

- **Test Coverage**: >80% for new code
- **Code Style**: Black + Ruff for Python, ESLint + Prettier for TypeScript
- **Type Safety**: Full type hints in Python, strict TypeScript mode
- **Commit Messages**: Conventional Commits format
- **Documentation**: Update README and docs/ for significant changes

## 🔒 Security

- **JWT Authentication**: Stateless tokens with bcrypt password hashing
- **Rate Limiting**: Token bucket (60 req/min) enforced in middleware
- **Input Validation**: Pydantic schemas on all API endpoints
- **SQL Injection**: Parameterized queries via SQLAlchemy ORM
- **Secret Management**: Environment variables, never committed to Git
- **Reddit TOS Compliance**: Respects rate limits, user privacy, content policies

## 📊 Observability

### Logging

Structured JSON logs with correlation IDs:
```json
{
  "timestamp": "2025-11-24T15:32:45.123Z",
  "level": "INFO",
  "correlation_id": "req_abc123",
  "message": "Generated response draft",
  "context": {
    "persona_id": "persona_1",
    "model": "openai/gpt-5.1-mini",
    "tokens_in": 456,
    "tokens_out": 89,
    "cost": 0.000081
  }
}
```

### Metrics

- **Cost Tracking**: Per-request LLM costs logged in interaction metadata
- **Error Rates**: Correlation IDs link errors to requests
- **Agent Status**: `/health/agent` endpoint reports loop status
- **Test Coverage**: HTML reports in `backend/htmlcov/`

## 🐛 Troubleshooting

### Database Locked

```bash
cd backend/data
sqlite3 reddit_agent.db
> PRAGMA journal_mode=WAL;
> .exit
```

### Import Errors

Ensure virtual environment is activated:
```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
which python  # Should point to venv/bin/python
```

### Reddit API 429 Errors

Rate limit exceeded. Agent includes exponential backoff with jitter:
- 1s delay after first failure
- 2s, 4s, 8s, etc. with ±25% jitter
- Max 60s delay
- Stops after 5 consecutive errors

Check `AGENT_POLL_INTERVAL` in `.env` (default 300s = 5 minutes).

### Frontend Build Errors

```bash
cd frontend
rm -rf .next node_modules
npm install
npm run build
```

### Agent Not Responding

Check agent loop status:
```bash
curl http://localhost:8000/health/agent
```

Expected response:
```json
{
  "status": "running",
  "last_check": "2025-11-24T15:32:45.123Z",
  "consecutive_errors": 0
}
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **OpenAI** - Agent best practices and cookbook patterns
- **Anthropic** - Claude Agent SDK and effective agents guide
- **Reddit** - API access and developer documentation
- **OpenRouter** - Model-agnostic LLM gateway

## 📬 Contact

For questions, issues, or feature requests, please open an issue on GitHub.

---

**Status**: ✅ MVP Complete (Weeks 1-4)

**Last Updated**: November 24, 2025

**Version**: 0.1.0
