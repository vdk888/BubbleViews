# ADR-001: Technology Stack Selection

## Status
Accepted

## Context
We are building an MVP Reddit AI Agent that autonomously engages on Reddit with a consistent persona and evolving belief system. The system must:

- Support autonomous Reddit interaction with persona consistency
- Maintain a structured belief graph with Bayesian-style confidence updates
- Provide a web dashboard for monitoring and moderation
- Scale from single to multiple personas
- Operate within a minimal budget constraint (~$10/month target)
- Follow quality standards from docs/0_dev.md (contract-based design, migration discipline, observability)

The architecture must balance rapid MVP delivery with maintainability and a clear upgrade path to production-grade infrastructure.

## Decision

### Backend Framework: FastAPI + Python 3.11

**Rationale:**
- **Native async support**: Critical for concurrent Reddit API calls, LLM requests, and database operations
- **OpenAPI generation**: Automatic API documentation aligns with contract-first design principle
- **Dependency Injection**: Built-in via `Depends()` enables clean separation of concerns
- **Type safety**: Pydantic integration provides runtime validation and clear contracts
- **Mature ecosystem**: Rich async libraries (asyncpraw, aiosqlite, httpx)

**Alternatives considered:**
- Node.js/Express: Less mature async patterns for ML/AI workflows
- Django: Heavier framework, less natural async support
- Flask: No built-in async, requires additional tooling

**Consequences:**
- Must maintain Python 3.11+ for optimal async performance
- Team needs FastAPI expertise (acceptable learning curve)
- OpenAPI spec becomes source of truth for API contracts

### Frontend: Next.js 14 with TypeScript

**Rationale:**
- **Server-Side Rendering (SSR)**: Fast initial page loads for dashboard
- **App Router**: Modern routing with React Server Components
- **Type safety**: TypeScript prevents runtime errors, enables API client generation from OpenAPI
- **Vercel deployment**: Free tier sufficient for MVP dashboard
- **Developer experience**: Hot reload, built-in optimization

**Alternatives considered:**
- React SPA: No SSR, slower initial loads
- Vue.js: Smaller ecosystem for complex dashboards
- Svelte: Less mature TypeScript support

**Consequences:**
- Dashboard must be deployed separately from backend (hybrid architecture)
- Next.js version updates may require migration work
- TypeScript types generated from OpenAPI spec

### Database: SQLite with JSON1 Extension

**Rationale:**
- **Zero setup**: File-based database (`data/reddit_agent.db`), no separate server
- **JSON support**: JSON1 extension enables belief graph queries (similar to PostgreSQL's JSONB)
- **ACID guarantees**: Built-in transactions ensure data consistency
- **Easy backup**: Simple file copy for backups
- **Sufficient scale**: Handles <10K interactions/beliefs for MVP
- **WAL mode**: Write-Ahead Logging enables concurrent readers with single writer
- **Migration path**: SQLAlchemy ORM abstracts database, enabling PostgreSQL upgrade

**Alternatives considered:**
- **PostgreSQL**:
  - Pros: Better concurrency, JSON indexing, full-text search
  - Cons: +$10-15/month hosting, requires separate droplet management
  - Decision: Over-engineered for MVP; upgrade when multi-agent scaling required
- **MongoDB**:
  - Pros: Native document storage
  - Cons: No ACID guarantees, less mature Python async support
  - Decision: Relational model better fits belief graph relationships

**Upgrade path:**
```python
# Change single line in config.py:
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
# Run: alembic upgrade head
```

**Consequences:**
- Single writer constraint (acceptable: one agent loop writes, API reads)
- Embedding storage via FAISS (separate from SQLite) for vector search
- Must use `json_extract()` for belief graph queries instead of native JSON operators
- Migrations must be PostgreSQL-compatible (no SQLite-specific features)

### LLM Provider: OpenRouter API

**Rationale:**
- **Model agnostic**: Switch between GPT, Claude, Llama without code changes
- **Unified billing**: Single API key for all models
- **Cost optimization**: Access to budget models (mini/Haiku tier)
- **OpenAI-compatible**: Drop-in replacement using OpenAI SDK
- **No vendor lock-in**: Can migrate to direct APIs if needed

**Model selection:**
- **Primary (response generation)**: `openai/gpt-5.1-mini`
  - Pricing: $0.15/1M input tokens, $0.60/1M output tokens
  - Fast response times (~500ms)
  - Sufficient quality for Reddit comments
- **Secondary (consistency checks)**: `anthropic/claude-4.5-haiku`
  - Pricing: $0.25/1M input tokens, $1.25/1M output tokens
  - Strong reasoning for belief alignment checks
  - Lower cost than Sonnet/Opus

**Alternatives considered:**
- **Direct OpenAI API**:
  - Pros: -50ms latency
  - Cons: No model flexibility, GPT-4 too expensive ($30/1M)
- **Direct Anthropic API**:
  - Pros: Native Claude features
  - Cons: Locked to single provider
- **Ollama (local)**:
  - Pros: Zero API cost
  - Cons: Requires GPU droplet (+$50/month), lower quality models

**Cost comparison (10 interactions/day):**
```
OpenRouter (mini/Haiku): ~$0.25/month
Direct GPT-4:             ~$15/month
Direct Claude-3-Opus:     ~$20/month
```

**Consequences:**
- +50-100ms latency vs direct APIs (acceptable for async Reddit interactions)
- Must monitor OpenRouter API reliability
- Cost tracking required per model/request

### Deployment: DigitalOcean Droplet

**Rationale:**
- **Always-on requirement**: Agent loop must monitor Reddit 24/7
- **Predictable costs**: $6/month for 1GB RAM droplet (vs serverless per-request pricing)
- **Full control**: Can run background processes, scheduled tasks
- **Simple ops**: No Docker/Kubernetes complexity for MVP
- **Sufficient resources**: 1GB RAM handles FastAPI + SQLite + FAISS (40MB for 10K embeddings)

**Hybrid architecture:**
- **Frontend**: Vercel (Next.js dashboard)
  - Free tier: 100GB bandwidth/month
  - CDN + auto-deployments
- **Backend + Agent**: DigitalOcean droplet
  - FastAPI server (port 8000)
  - Agent event loop (background process via systemd)
  - Nginx reverse proxy

**Alternatives considered:**
- **Vercel for everything**:
  - Pros: Simplest deployment
  - Cons: Serverless functions unsuitable for 24/7 agent loop, hidden bandwidth limits
- **Netlify**:
  - Pros: Similar to Vercel
  - Cons: Same serverless limitations
- **AWS/GCP**:
  - Pros: Scalability
  - Cons: Complex pricing, overkill for MVP

**Consequences:**
- Must maintain systemd service configuration
- Manual deployments to droplet (automate in Phase 1)
- Dashboard and backend on separate domains (CORS configuration required)

### Message Queue: In-Memory (asyncio.Queue)

**Rationale:**
- **Simplicity**: No external service for MVP
- **Sufficient**: Single agent instance, low volume (<10 posts/day)
- **Zero cost**: Built into Python async runtime

**Use cases:**
- Moderation queue: Draft posts awaiting approval
- Event processing: Reddit notifications to agent logic

**Alternatives considered:**
- **Redis**:
  - Pros: Persistent, pub/sub support
  - Cons: +$5-10/month, adds deployment complexity
  - Decision: Defer until multi-agent scaling
- **RabbitMQ/Kafka**:
  - Decision: Massive overkill for MVP

**Upgrade path:**
```python
# Replace asyncio.Queue with Redis in services/moderation.py
# No API contract changes
```

**Consequences:**
- Queue state lost on restart (acceptable: auto-recover on next Reddit poll)
- No cross-instance communication (single agent only)
- Must implement Redis when scaling to multiple personas

### Vector Search: FAISS (In-Memory)

**Rationale:**
- **Local embeddings**: Use sentence-transformers (no API costs)
- **Fast**: In-memory index, <10ms search for 10K vectors
- **Portable**: Save/load index to `data/faiss_index.bin`
- **Sufficient scale**: 384-dim embeddings, 4MB per 1K interactions

**Model:** `sentence-transformers/all-MiniLM-L6-v2`
- 384 dimensions
- Good semantic similarity for short texts
- No GPU required

**Alternatives considered:**
- **pgvector (PostgreSQL extension)**:
  - Pros: Integrated with database
  - Cons: Requires PostgreSQL, slower than in-memory FAISS
- **Pinecone/Weaviate**:
  - Pros: Managed service
  - Cons: +$10-25/month, network latency

**Consequences:**
- Load FAISS index on startup (~100ms for 10K vectors)
- Rebuild index when crossing 50K interactions (add incremental updates)
- Embeddings stored separately from SQLite (future: migrate to pgvector with PostgreSQL)

## Cost Analysis

### Monthly Costs (MVP)

| Component | Technology | Cost |
|-----------|-----------|------|
| Compute | DigitalOcean 1GB Droplet | $6.00 |
| Frontend | Vercel Free Tier | $0.00 |
| LLM (10 responses/day) | OpenRouter GPT-5.1-mini | $0.18 |
| LLM (10 checks/day) | OpenRouter Claude-4.5-Haiku | $0.04 |
| Database | SQLite (local file) | $0.00 |
| Vector DB | FAISS (in-memory) | $0.00 |
| Message Queue | asyncio.Queue | $0.00 |
| **Total** | | **$6.22/month** |

### Comparison with Original Plan

| Component | Original | Selected | Savings |
|-----------|----------|----------|---------|
| Database | PostgreSQL droplet ($12) | SQLite ($0) | $12 |
| Message Queue | Redis ($5) | asyncio.Queue ($0) | $5 |
| LLM | GPT-4 + Claude-3-Opus ($30) | mini + Haiku ($0.22) | $30 |
| Vector DB | Pinecone ($10) | FAISS ($0) | $10 |
| **Total** | **$57/month** | **$6.22/month** | **$50.78 (89% reduction)** |

### Scaling Costs (Future)

**Upgrade to PostgreSQL + Redis (5 personas, 50 posts/day):**
- DigitalOcean: 2GB Droplet ($12/month)
- PostgreSQL: Managed DB ($15/month)
- Redis: Managed instance ($5/month)
- LLM: ~$3/month (increased volume)
- **Total: ~$35/month** (still 39% cheaper than original MVP plan)

## Key Decision Rationales

### SQLite vs PostgreSQL

**Why SQLite for MVP:**
1. **Development velocity**: Zero configuration enables immediate schema iteration
2. **Sufficient scale**: Single agent, <10K interactions, <100 beliefs fits comfortably
3. **Cost**: Eliminates $12-15/month managed database
4. **Backup simplicity**: `cp data/reddit_agent.db backups/` vs complex pg_dump automation
5. **Migration path**: SQLAlchemy ORM + PostgreSQL-compatible schema = one-line change

**When to upgrade:**
- Multiple agent instances requiring true concurrent writes
- Crossing 50K interactions (SQLite performance degrades)
- Advanced JSON indexing needs (GIN indexes)
- Full-text search requirements

### OpenRouter vs Direct APIs

**Why OpenRouter:**
1. **Flexibility**: Experiment with models without code changes (change env var)
2. **Cost**: Access to mini/Haiku tier (50x cheaper than premium models)
3. **Unified billing**: Single invoice for multi-provider usage
4. **Risk mitigation**: Switch providers if one has outages

**Trade-offs accepted:**
- +50-100ms latency (async Reddit workflow absorbs this)
- Dependency on OpenRouter uptime (monitoring required)
- Slight markup over direct API pricing (~10%)

### In-Memory Queue vs Redis

**Why asyncio.Queue:**
1. **MVP scope**: Single agent instance, <10 posts/day, simple moderation flow
2. **Zero ops**: No external service to monitor/backup
3. **Sufficient reliability**: Restart on failure recovers state from Reddit API

**When to add Redis:**
- Multi-instance deployment (need shared state)
- High-volume posting (>50/day)
- Cross-service communication (e.g., separate scheduler service)

## Quality Alignment (per docs/0_dev.md)

### Contract-Based Design
- ABCs for all services (`IMemoryStore`, `IRedditClient`, `ILLMClient`)
- OpenAPI spec as API contract
- Pydantic schemas for data validation
- Contract tests validate interface behavior

### Migration Discipline
- Alembic for forward-only migrations
- PostgreSQL-compatible schema (no SQLite-specific features)
- Transactional DDL where possible
- Dry-run migrations against production snapshots (future)

### Observability
- Structured logging (JSON) with correlation IDs
- Cost tracking per LLM request
- Health check endpoints (`/health`, `/health/ready`)
- Token usage metrics in dashboard

### Separation of Concerns
- Services layer (business logic)
- Models layer (data)
- API layer (HTTP interface)
- Agent layer (autonomous loop)

### Security
- Environment-based secrets (never commit to git)
- JWT for dashboard authentication
- Reddit API credentials in encrypted config
- Secret rotation policy documented in runbooks

## Risks and Mitigations

### Risk: SQLite Concurrency Limitations
- **Mitigation**: WAL mode enables multiple readers + single writer (sufficient for MVP)
- **Monitoring**: Alert on write contention in logs
- **Escape hatch**: PostgreSQL upgrade path documented and tested

### Risk: OpenRouter API Reliability
- **Mitigation**: Exponential backoff retry logic (3 attempts)
- **Monitoring**: Track API uptime, switch to direct APIs if <99% reliability
- **Escape hatch**: `ILLMClient` abstraction enables swapping implementations

### Risk: FAISS Memory Growth
- **Mitigation**: 4MB per 1K interactions = 400MB at 100K (acceptable)
- **Monitoring**: Log index size on startup
- **Escape hatch**: Migrate to pgvector with PostgreSQL upgrade

### Risk: Vercel Bandwidth Limits
- **Mitigation**: Dashboard is admin-only (low traffic)
- **Monitoring**: Vercel dashboard usage metrics
- **Escape hatch**: Host frontend on same DigitalOcean droplet

### Risk: In-Memory Queue Data Loss
- **Mitigation**: Acceptable for MVP (recover from Reddit API on restart)
- **Monitoring**: Track queue restarts in logs
- **Escape hatch**: Redis upgrade adds persistence

## Success Criteria

### Phase 0 Validation (Week 1)
- [ ] SQLite database created with JSON1 extension enabled (`SELECT json('{}')` succeeds)
- [ ] OpenRouter client successfully calls both models (GPT-5.1-mini + Claude-4.5-Haiku)
- [ ] FAISS index saves/loads correctly (test with 100 dummy embeddings)
- [ ] Credentials imported from config.json to .env
- [ ] Alembic migrations apply cleanly (`alembic upgrade head`)
- [ ] OpenAPI spec validates (Swagger UI accessible)
- [ ] Cost tracking logs correct values (test with mock requests)

### Phase 1 Validation (Weeks 2-4)
- [ ] Agent posts 1 comment/day in test subreddit using GPT-5.1-mini
- [ ] Belief graph stores 10 initial beliefs in SQLite (query via JSON1)
- [ ] Consistency check using Claude-4.5-Haiku detects contradictions
- [ ] Dashboard displays activity feed and belief graph
- [ ] Moderation queue functional with auto/manual toggle
- [ ] Total cost <$1/week measured via OpenRouter usage logs

## Implementation Notes

### Database Setup
```bash
# Enable JSON1 extension (usually built-in)
sqlite3 data/reddit_agent.db
> SELECT json('{"test": true}');  # Should return {"test": true}

# Enable WAL mode
> PRAGMA journal_mode=WAL;
```

### OpenRouter Configuration
```python
# backend/app/core/config.py
class Settings(BaseSettings):
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    response_model: str = "openai/gpt-5.1-mini"
    consistency_model: str = "anthropic/claude-4.5-haiku"

# backend/app/services/llm_client.py
client = AsyncOpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url
)
```

### FAISS Setup
```python
# backend/app/services/memory_store.py
import faiss
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
index = faiss.IndexFlatL2(384)  # 384-dim embeddings

# Save/load
faiss.write_index(index, "data/faiss_index.bin")
index = faiss.read_index("data/faiss_index.bin")
```

## References
- Technical Specification: `docs/MVP_Reddit_AI_Agent_Technical_Specification.md`
- Quality Standards: `docs/0_dev.md`
- Architecture Build Plan: `docs/MVP Reddit AI Agent - Architecture Build.md`
- OpenRouter Pricing: https://openrouter.ai/pricing
- SQLite JSON1 Docs: https://www.sqlite.org/json1.html
- FastAPI Best Practices: https://fastapi.tiangolo.com/
- Anthropic Agent Guidelines: https://www.anthropic.com/engineering/building-effective-agents

## Revision History
- 2025-11-24: Initial version (Phase 0, Day 1)
