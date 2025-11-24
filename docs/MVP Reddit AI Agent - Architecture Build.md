# MVP Reddit AI Agent - Architecture Build Plan

## Key Architecture Decisions
- **Database**: SQLite with JSON1 extension (simpler setup, file-based, good for MVP)
- **LLM Provider**: OpenRouter (model-agnostic) with GPT-4o-mini and Claude-3.5-Haiku
- **Deployment**: Single DigitalOcean droplet (simplified, no Docker for MVP)
- **Cost**: ~$6.25/month total (vs $50+ for PostgreSQL + premium LLMs)

---

## Phase 0: Indestructible Foundations (Week 1)

### Day 1: Architecture Decision Records

Create `docs/decisions/ADR-001-tech-stack.md` documenting:

**Backend**: FastAPI (native async, OpenAPI generation, DI via Depends)
**Frontend**: Next.js 14 with TypeScript (SSR, type safety)
**Database**: SQLite with JSON1 extension (JSON support for belief graph, zero setup)
**LLM**: OpenRouter API (model-agnostic gateway)
  - Primary: `openai/gpt-4o-mini` (fast, cheap responses - $0.15/1M tokens)
  - Secondary: `anthropic/claude-3.5-haiku` (consistency checks - $0.25/1M tokens)
**Deployment**: DigitalOcean droplet ($6/month, 1GB RAM)
**Message Queue**: In-memory (asyncio.Queue) for MVP, upgrade to Redis later

#### Key Decision Rationale

**SQLite vs PostgreSQL**:
- ✅ Zero setup/maintenance (file-based: `data/reddit_agent.db`)
- ✅ JSON1 extension for belief graph queries (like JSONB in PostgreSQL)
- ✅ ACID transactions built-in
- ✅ Easy backup (copy .db file)
- ✅ Sufficient for single-agent MVP (<10K interactions)
- ⚠️ Migration to PostgreSQL when scaling to multiple agents

**OpenRouter vs Direct APIs**:
- ✅ Already have API key (from config.json)
- ✅ Model-agnostic: switch models without code changes
- ✅ Unified billing across providers
- ✅ 50x cheaper than premium models (mini/Haiku vs Sonnet/GPT-4)
- ⚠️ +50-100ms latency vs direct API (acceptable for MVP)

**Semantic Search**: FAISS (in-memory) instead of pgvector
- Load embeddings on startup, persist to `data/faiss_index.bin`
- Use sentence-transformers for local embedding generation

Create `docs/architecture/system-diagram.md` with Mermaid diagrams
Document data flow: Reddit → Perception → Retrieval → Decision → Moderation → Action

---

### Day 2: Project Structure Scaffolding

Create directory structure:
```
backend/
├── app/
│   ├── core/
│   │   ├── config.py          # Pydantic settings (OpenRouter key, SQLite path)
│   │   ├── database.py        # SQLAlchemy SQLite setup with aiosqlite
│   │   └── security.py        # JWT handling
│   ├── api/v1/
│   │   ├── activity.py
│   │   ├── beliefs.py
│   │   ├── moderation.py
│   │   └── settings.py
│   ├── services/
│   │   ├── interfaces/        # ABCs (contract-first)
│   │   │   ├── memory_store.py
│   │   │   ├── reddit_client.py
│   │   │   └── llm_client.py
│   │   ├── memory_store.py    # SQLite implementation
│   │   ├── reddit_client.py   # asyncpraw wrapper
│   │   ├── llm_client.py      # OpenRouter client (OpenAI-compatible)
│   │   ├── belief_updater.py
│   │   └── moderation.py
│   ├── models/                # SQLAlchemy ORM models
│   │   ├── base.py
│   │   ├── belief.py
│   │   ├── interaction.py
│   │   └── pending_post.py
│   ├── schemas/               # Pydantic validation schemas
│   └── agent/
│       ├── loop.py            # Main event loop
│       ├── perception.py
│       ├── decision.py
│       └── action.py
├── data/                      # SQLite database + embeddings
│   ├── reddit_agent.db
│   └── faiss_index.bin
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── alembic/                   # Database migrations
│   └── versions/
└── pyproject.toml

frontend/
├── src/
│   ├── app/                   # Next.js 14 App Router
│   │   ├── activity/
│   │   ├── beliefs/
│   │   ├── moderation/
│   │   └── settings/
│   ├── components/
│   │   ├── ui/
│   │   ├── belief-graph.tsx
│   │   └── activity-feed.tsx
│   ├── lib/
│   │   └── api-client.ts      # Generated from OpenAPI
│   └── hooks/
└── package.json

docs/
├── decisions/
│   ├── ADR-001-tech-stack.md
│   ├── ADR-002-sqlite-schema.md
│   └── ADR-003-openrouter-integration.md
├── api/
│   └── openapi.yaml
├── architecture/
│   └── system-diagram.md
└── runbooks/
    ├── deployment.md
    └── rollback.md
```

**Dependencies** (`backend/pyproject.toml`):
```toml
[project]
name = "reddit-ai-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "asyncpraw>=7.8.1",
    "openai>=1.12.0",              # OpenRouter is OpenAI-compatible
    "sqlalchemy>=2.0.25",
    "aiosqlite>=0.19.0",           # Async SQLite driver
    "alembic>=1.13.1",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "sentence-transformers>=2.3.0", # For embeddings
    "faiss-cpu>=1.7.4",            # Vector search (in-memory)
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "httpx>=0.26.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.3",
    "pytest-asyncio>=0.23.3",
    "pytest-cov>=4.1.0",
    "black>=23.12.1",
    "ruff>=0.1.9",
    "mypy>=1.8.0",
]
```

Set up linting: `ruff.toml`, `pyproject.toml` (black/mypy config)
Initialize Next.js frontend with TypeScript, Tailwind, App Router
Create `Makefile` with common commands

---

### Day 3: Configuration & Secrets

Create `backend/app/core/config.py` (Pydantic Settings):
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # API
    api_v1_prefix: str = "/api/v1"
    project_name: str = "Reddit AI Agent"

    # Database (SQLite)
    database_url: str = "sqlite+aiosqlite:///./data/reddit_agent.db"

    # Reddit API (from config.json)
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str
    reddit_username: str
    reddit_password: str

    # OpenRouter LLM
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model selection (can switch without code changes)
    response_model: str = "openai/gpt-4o-mini"
    consistency_model: str = "anthropic/claude-3.5-haiku"

    # Agent config
    target_subreddits: List[str] = ["test", "bottest"]
    auto_posting_enabled: bool = False

    # Security
    secret_key: str
    access_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )

settings = Settings()
```

Create `.env.example`:
```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./data/reddit_agent.db

# Reddit API (from config.json)
REDDIT_CLIENT_ID=yJIWsD6xd1GPaM40E2toog
REDDIT_CLIENT_SECRET=ZJYksoThu9qp_FefTTPFDVonpkrofg
REDDIT_USER_AGENT=python:MyRedditBot:v1.0 (by /u/ImprovementMain7109)
REDDIT_USERNAME=ImprovementMain7109
REDDIT_PASSWORD=ImprovementMain7109

# OpenRouter LLM (from config.json)
OPENROUTER_API_KEY=sk-proj-guyaw7kLKumUkummEC6T3B1bkFJ...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Model selection (switch models here)
RESPONSE_MODEL=openai/gpt-4o-mini
CONSISTENCY_MODEL=anthropic/claude-3.5-haiku

# Agent config
TARGET_SUBREDDITS=["test","bottest"]
AUTO_POSTING_ENABLED=false

# Security
SECRET_KEY=generate-with-openssl-rand-hex-32
```

Implement `backend/app/core/security.py` for JWT handling
Document secret rotation policy in `docs/runbooks/secrets.md`

---

### Day 4: Database & Migrations

**SQLite Schema** (uses JSON1 extension for JSON support):

```sql
-- Enable JSON1 extension (built-in since SQLite 3.38)
-- Beliefs table with JSON support
CREATE TABLE beliefs (
    id TEXT PRIMARY KEY,               -- UUID as text
    belief_data TEXT NOT NULL,         -- JSON string
    confidence REAL CHECK (confidence >= 0 AND confidence <= 1),
    tags TEXT,                         -- Comma-separated or JSON array
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CHECK (json_valid(belief_data))    -- Validate JSON
);

CREATE INDEX idx_beliefs_confidence ON beliefs(confidence);
CREATE INDEX idx_beliefs_updated ON beliefs(updated_at DESC);

-- Query examples:
-- SELECT * FROM beliefs WHERE json_extract(belief_data, '$.text') LIKE '%climate%';
-- SELECT * FROM beliefs WHERE json_extract(belief_data, '$.confidence') > 0.8;

-- Interactions table
CREATE TABLE interactions (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    interaction_type TEXT NOT NULL,    -- 'post', 'comment', 'reply'
    reddit_id TEXT UNIQUE NOT NULL,
    subreddit TEXT NOT NULL,
    metadata TEXT,                     -- JSON string
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CHECK (json_valid(metadata))
);

CREATE INDEX idx_interactions_subreddit ON interactions(subreddit);
CREATE INDEX idx_interactions_created ON interactions(created_at DESC);
CREATE INDEX idx_interactions_reddit_id ON interactions(reddit_id);

-- Belief updates audit log
CREATE TABLE belief_updates (
    id TEXT PRIMARY KEY,
    belief_id TEXT,
    old_value TEXT,                    -- JSON
    new_value TEXT,                    -- JSON
    reason TEXT NOT NULL,
    trigger_type TEXT,                 -- 'manual', 'evidence', 'conflict'
    updated_by TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (belief_id) REFERENCES beliefs(id) ON DELETE CASCADE,
    CHECK (json_valid(old_value)),
    CHECK (json_valid(new_value))
);

CREATE INDEX idx_belief_updates_belief ON belief_updates(belief_id);
CREATE INDEX idx_belief_updates_created ON belief_updates(created_at DESC);

-- Moderation queue
CREATE TABLE pending_posts (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    post_type TEXT,
    target_subreddit TEXT,
    parent_id TEXT,
    draft_metadata TEXT,               -- JSON
    status TEXT DEFAULT 'pending',     -- 'pending', 'approved', 'rejected'
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CHECK (json_valid(draft_metadata))
);

CREATE INDEX idx_pending_posts_status ON pending_posts(status);
CREATE INDEX idx_pending_posts_created ON pending_posts(created_at DESC);

-- Agent config (key-value store)
CREATE TABLE agent_config (
    id TEXT PRIMARY KEY,
    config_key TEXT UNIQUE NOT NULL,
    config_value TEXT NOT NULL,        -- JSON
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CHECK (json_valid(config_value))
);

-- Enable WAL mode for better concurrency (single writer, multiple readers)
PRAGMA journal_mode=WAL;
```

**SQLAlchemy Models** (`backend/app/models/base.py`):
```python
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, DateTime
from datetime import datetime
import uuid

Base = declarative_base()

class TimestampMixin:
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat(),
                       onupdate=lambda: datetime.utcnow().isoformat())

class UUIDMixin:
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
```

**Belief Model** (`backend/app/models/belief.py`):
```python
from sqlalchemy import Column, String, Float, Text
from app.models.base import Base, UUIDMixin, TimestampMixin
import json

class Belief(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "beliefs"

    belief_data = Column(Text, nullable=False)  # JSON string
    confidence = Column(Float)
    tags = Column(Text)  # Comma-separated or JSON array

    def get_belief_json(self) -> dict:
        """Parse belief_data JSON string"""
        return json.loads(self.belief_data)

    def set_belief_json(self, data: dict):
        """Set belief_data from dict"""
        self.belief_data = json.dumps(data)
```

Initialize Alembic:
```bash
cd backend
alembic init alembic
# Edit alembic.ini to use SQLite
# Create initial migration with schema above
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

Test migration rollback:
```bash
alembic downgrade -1
alembic upgrade head
```

---

### Day 5: OpenRouter LLM Client

**Interface** (`backend/app/services/interfaces/llm_client.py`):
```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class ILLMClient(ABC):
    """Contract for LLM interactions"""

    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        context: Dict,
        user_message: str,
        tools: Optional[List[Dict]] = None
    ) -> Dict:
        """Generate LLM response with optional tool use"""
        pass

    @abstractmethod
    async def check_consistency(
        self,
        draft_response: str,
        beliefs: List[Dict]
    ) -> Dict:
        """Check if draft aligns with belief graph"""
        pass
```

**Implementation** (`backend/app/services/llm_client.py`):
```python
from openai import AsyncOpenAI
from typing import Dict, List, Optional
from app.core.config import settings
from app.services.interfaces.llm_client import ILLMClient
import json

class OpenRouterClient(ILLMClient):
    """OpenRouter LLM client (OpenAI-compatible API)"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url
        )
        self.response_model = settings.response_model
        self.consistency_model = settings.consistency_model

    async def generate_response(
        self,
        system_prompt: str,
        context: Dict,
        user_message: str,
        tools: Optional[List[Dict]] = None
    ) -> Dict:
        """Generate response using GPT-4o-mini (fast, cheap)"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context: {json.dumps(context)}\n\nMessage: {user_message}"}
        ]

        response = await self.client.chat.completions.create(
            model=self.response_model,
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        return {
            "text": response.choices[0].message.content,
            "model": self.response_model,
            "tokens": response.usage.total_tokens,
            "cost": self._calculate_cost(response.usage, self.response_model)
        }

    async def check_consistency(
        self,
        draft_response: str,
        beliefs: List[Dict]
    ) -> Dict:
        """Check consistency using Claude-3.5-Haiku (cheaper for checks)"""

        belief_summary = "\n".join([
            f"- {b['text']} (confidence: {b['confidence']})"
            for b in beliefs
        ])

        prompt = f"""You are a consistency checker. Analyze if the draft response contradicts any beliefs.

Beliefs:
{belief_summary}

Draft Response:
{draft_response}

Respond with JSON:
{{
  "is_consistent": true/false,
  "conflicts": ["belief_id1", ...],
  "explanation": "brief explanation"
}}"""

        response = await self.client.chat.completions.create(
            model=self.consistency_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        result["tokens"] = response.usage.total_tokens
        result["cost"] = self._calculate_cost(response.usage, self.consistency_model)

        return result

    def _calculate_cost(self, usage, model: str) -> float:
        """Calculate cost based on token usage and model pricing"""
        # OpenRouter pricing (approximate)
        pricing = {
            "openai/gpt-4o-mini": {"input": 0.15/1_000_000, "output": 0.60/1_000_000},
            "anthropic/claude-3.5-haiku": {"input": 0.25/1_000_000, "output": 1.25/1_000_000}
        }

        if model in pricing:
            cost = (usage.prompt_tokens * pricing[model]["input"] +
                   usage.completion_tokens * pricing[model]["output"])
            return round(cost, 6)
        return 0.0
```

Create test script to verify OpenRouter connectivity:
```python
# backend/tests/test_openrouter.py
import asyncio
from app.services.llm_client import OpenRouterClient

async def test_openrouter():
    client = OpenRouterClient()

    # Test GPT-4o-mini
    response = await client.generate_response(
        system_prompt="You are a helpful assistant.",
        context={},
        user_message="Say hello!"
    )
    print(f"Response: {response['text']}")
    print(f"Cost: ${response['cost']}")

    # Test Claude-3.5-Haiku
    consistency = await client.check_consistency(
        draft_response="Climate change is fake.",
        beliefs=[{"text": "Climate change is real", "confidence": 0.9}]
    )
    print(f"Consistency check: {consistency}")

if __name__ == "__main__":
    asyncio.run(test_openrouter())
```

---

## Phase 1: Core Services (Weeks 2-4)

### Week 2: Foundation Services

**Service 1: Health Checks** (Days 1-2)
- Endpoints: `/health`, `/health/ready`, `/health/agent`
- Structured JSON logging
- Check SQLite: `SELECT 1`
- Check OpenRouter: HEAD request to base_url

**Service 2: Auth Service** (Days 3-5)
- JWT token generation/validation
- Single admin user (stored in SQLite)
- Protected route middleware via `Depends()`
- Contract tests: token validation behavior

### Week 3: Core Agent Services

**Service 3: Memory Store** (Days 1-2)
- Implement `IMemoryStore` interface (ABC)
- Methods: `query_beliefs()`, `update_belief()`, `log_interaction()`, `search_history()`
- SQLite backend with JSON queries via `json_extract()`
- FAISS index for semantic search (load/save to `data/faiss_index.bin`)
- Contract tests: CRUD maintains ACID properties

**Service 4: Reddit Client** (Days 3-4)
- Implement `IRedditClient` interface
- Wrap asyncpraw with rate limiting (60 req/min token bucket)
- Methods: `get_new_posts()`, `search_posts()`, `submit_post()`, `reply()`
- Use credentials from config.json
- Contract tests: retry logic with mock Reddit API

**Service 5: LLM Client** (Day 5)
- Already implemented above (OpenRouterClient)
- Add retry logic with exponential backoff
- Log token usage and cost per request
- Contract tests: prompt formatting validation

### Week 4: Agent Logic & Integration

**Service 6: Agent Logic** (Days 1-2)
- Decision engine: perception → retrieval → decision
- Context assembly from belief graph + memory
- Draft response generation using GPT-4o-mini
- Contract tests: context → valid response

**Service 7: Belief Updater** (Days 3-4)
- Bayesian confidence update logic
- Consistency checker (draft vs beliefs) using Claude-3.5-Haiku
- Audit logging to belief_updates table
- Contract tests: deterministic confidence updates

**Service 8: Moderation** (Day 5)
- Content filter (can use OpenRouter for moderation too)
- Queue management (pending_posts table)
- Admin approval workflow
- Contract tests: flagged content → queue (not posted)

**Service 9: Agent Event Loop** (Days 6-7)
- Main loop: monitor → perceive → decide → moderate → act
- Graceful shutdown, error recovery
- Log all actions with cost tracking
- Integration tests: end-to-end with test subreddit

---

## API Contracts (Interface-First Design)

### OpenAPI Schema (`docs/api/openapi.yaml`)

Key endpoints:
- `GET /api/v1/activity?since={timestamp}&limit={N}` - Recent agent activity
- `GET /api/v1/beliefs?tags={tag1,tag2}` - Retrieve belief graph
- `PUT /api/v1/beliefs/{id}` - Update belief (confidence, text)
- `GET /api/v1/moderation/pending` - Pending moderation queue
- `POST /api/v1/moderation/approve` - Approve post (publish to Reddit)
- `POST /api/v1/moderation/reject` - Reject post
- `POST /api/v1/settings` - Update agent config
- `GET /api/v1/stats` - Token usage, costs, interaction counts

### Python ABCs (contracts before implementation)
- `IMemoryStore` - Memory operations (query, update, log)
- `IRedditClient` - Reddit API interactions (get, post, reply)
- `ILLMClient` - LLM operations (generate, check consistency)
- `IModerationService` - Content filtering

---

## Technology Stack Summary

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Backend | FastAPI + Python 3.11 | Async, OpenAPI generation, DI |
| Frontend | Next.js 14 + TypeScript | SSR, type safety, Vercel deployment |
| Database | SQLite + JSON1 | Zero setup, JSON support, ACID |
| ORM | SQLAlchemy + aiosqlite | Async, migrations via Alembic |
| LLM | OpenRouter API | Model-agnostic, cost-effective |
| Models | GPT-4o-mini + Claude-3.5-Haiku | $0.15-0.25/1M tokens |
| Embeddings | sentence-transformers | Local generation (all-MiniLM-L6-v2) |
| Vector Search | FAISS (CPU) | In-memory, <10K vectors |
| Reddit API | asyncpraw | Rate limiting, async support |
| Auth | JWT via python-jose | Stateless, standard |

---

## Deployment Strategy

### Development (Local)
```bash
# Start backend
cd backend
python -m uvicorn app.main:app --reload --port 8000

# Start frontend
cd frontend
npm run dev
```

### Production (DigitalOcean)
- Single droplet: $6/month (1GB RAM, 25GB SSD)
- No Docker needed for MVP (simpler debugging)
- systemd service for agent loop
- nginx reverse proxy for API
- Vercel for frontend (optional, or serve via nginx)

**Deployment steps**:
```bash
# On droplet
git clone <repo>
cd backend
python -m venv venv
source venv/bin/activate
pip install -e .
alembic upgrade head

# Run agent as systemd service
sudo systemctl start reddit-agent
sudo systemctl enable reddit-agent
```

---

## Cost Analysis

**OpenRouter LLM Costs** (estimated for MVP):
- GPT-4o-mini: $0.15/1M input, $0.60/1M output
  - 10 responses/day × 1000 tokens avg = 0.3M tokens/month = **$0.18/month**
- Claude-3.5-Haiku: $0.25/1M input, $1.25/1M output
  - 10 checks/day × 500 tokens avg = 0.15M tokens/month = **$0.04/month**
- **Total LLM cost**: ~$0.25/month

**Infrastructure**:
- DigitalOcean: $6/month (1GB droplet)
- Vercel: $0 (free tier)
- **Total infrastructure**: $6/month

**Grand Total**: ~$6.25/month

**Savings vs Original Plan**:
- PostgreSQL droplet: -$10/month (SQLite is file-based)
- Redis: -$0 (using asyncio.Queue)
- Premium LLMs: -$15/month (Haiku/mini vs Sonnet/GPT-4)
- **Total savings**: ~$25/month (80% cost reduction)

---

## Success Criteria

### Phase 0 (Week 1)
- ✅ SQLite database created with JSON1 extension enabled
- ✅ OpenRouter client successfully calls both models (GPT-4o-mini + Haiku)
- ✅ FAISS index saves/loads correctly
- ✅ Credentials imported from config.json to .env
- ✅ Docker Compose stack starts (optional)
- ✅ Database migrations apply cleanly
- ✅ OpenAPI spec validates
- ✅ Onboarding docs complete

### Phase 1 (Weeks 2-4)
- ✅ Agent posts 1 comment/day in test subreddit using GPT-4o-mini
- ✅ Belief graph stores 10 initial beliefs in SQLite
- ✅ Belief consistency check using Claude-3.5-Haiku
- ✅ Dashboard displays activity feed (queries SQLite)
- ✅ Moderation queue functional (pending_posts table)
- ✅ 80% unit test coverage on core services
- ✅ <200ms p95 latency for API endpoints
- ✅ Total cost <$1/week (extremely low with mini/Haiku)

---

## Risk Mitigation

1. **SQLite Concurrency**:
   - Enable WAL mode (Write-Ahead Logging)
   - Single writer (agent loop), multiple readers (API)
   - Acceptable for MVP, migrate to PostgreSQL at scale

2. **No Redis**:
   - Use asyncio.Queue for moderation queue (in-memory)
   - Lost on restart (acceptable for MVP)
   - Can add Redis later if needed

3. **FAISS Memory Usage**:
   - ~4MB per 1K interactions with 384-dim embeddings
   - 10K interactions = 40MB (well within limits)

4. **OpenRouter Latency**:
   - Add +50-100ms vs direct API
   - Mitigated by using fast models (Haiku/mini)
   - Cache frequently used prompts

5. **Belief Graph Complexity**:
   - Start with flat list (no graph traversal needed)
   - Add visualization in dashboard
   - Quarterly pruning of low-confidence beliefs

6. **Reddit API Rate Limits**:
   - 60 requests/minute with token bucket
   - Cache subreddit data for 5 minutes
   - Prioritize replies over new posts

---

## First Actions (Day 1 Morning)

```bash
# 1. Create project structure
mkdir -p docs/{decisions,api,architecture,runbooks}
mkdir -p backend/app/{core,api/v1,services/{interfaces},models,schemas,agent,tests}
mkdir -p backend/data backend/alembic/versions
mkdir -p frontend

# 2. Initialize Python project
cd backend
cat > pyproject.toml << EOF
[project]
name = "reddit-ai-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "asyncpraw>=7.8.1",
    "openai>=1.12.0",
    "sqlalchemy>=2.0.25",
    "aiosqlite>=0.19.0",
    "alembic>=1.13.1",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "sentence-transformers>=2.3.0",
    "faiss-cpu>=1.7.4",
    "python-jose[cryptography]>=3.3.0",
    "httpx>=0.26.0",
]
EOF

# 3. Create .env from config.json
cat > .env << EOF
DATABASE_URL=sqlite+aiosqlite:///./data/reddit_agent.db
REDDIT_CLIENT_ID=yJIWsD6xd1GPaM40E2toog
REDDIT_CLIENT_SECRET=ZJYksoThu9qp_FefTTPFDVonpkrofg
REDDIT_USER_AGENT=python:MyRedditBot:v1.0 (by /u/ImprovementMain7109)
REDDIT_USERNAME=ImprovementMain7109
REDDIT_PASSWORD=ImprovementMain7109
OPENROUTER_API_KEY=sk-proj-guyaw7kLKumUkummEC6T3B1bkFJ...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
RESPONSE_MODEL=openai/gpt-4o-mini
CONSISTENCY_MODEL=anthropic/claude-3.5-haiku
TARGET_SUBREDDITS=["test","bottest"]
AUTO_POSTING_ENABLED=false
SECRET_KEY=$(openssl rand -hex 32)
EOF

# 4. Initialize git
git add .
git commit -m "docs: Initialize project with SQLite + OpenRouter architecture"

# 5. Create ADR-001
# Document architecture decisions in docs/decisions/ADR-001-tech-stack.md
```

---

## Next Steps

After Phase 0 completion:
1. Implement health checks and auth (Week 2)
2. Build core services with contract tests (Week 3)
3. Integrate agent logic and event loop (Week 4)
4. Deploy to DigitalOcean and monitor costs
5. Iterate based on real-world usage

This architecture prioritizes **simplicity, cost-effectiveness, and rapid iteration** while maintaining the modular, contract-first design principles from 0_dev.md.
