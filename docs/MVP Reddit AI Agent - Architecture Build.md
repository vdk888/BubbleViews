MVP Reddit AI Agent - Architecture Build Plan
Overview
Build a modular, contract-first Reddit AI Agent following Interface-First Design methodology from 0_dev.md, implementing the architecture specified in the technical specification document.
Phase 0: Indestructible Foundations (Week 1)
Day 1: Architecture Decision Records
Create docs/decisions/ADR-001-tech-stack.md documenting:
Backend: FastAPI (native async, OpenAPI generation, DI via Depends)
Frontend: Next.js 14 with TypeScript (SSR, type safety)
Database: PostgreSQL 15+ with JSONB (JSON-LD compatible belief graph)
LLM: Anthropic Claude 3.5 Sonnet (primary), OpenAI GPT-4 (fallback)
Deployment: DigitalOcean droplet + Vercel dashboard
Message Queue: Redis with job queues
Create docs/architecture/system-diagram.md with Mermaid diagrams
Document data flow: Reddit → Perception → Retrieval → Decision → Moderation → Action
Day 2: Project Structure Scaffolding
Create directory structure:
backend/app/{core,api/v1,services,models,schemas,agent,db}
frontend/src/{app,components,lib,hooks}
docs/{decisions,api,architecture,runbooks}
docker/, scripts/
Set up pyproject.toml with dependencies (FastAPI, asyncpraw, anthropic, SQLAlchemy, alembic)
Initialize Next.js frontend with TypeScript, Tailwind, App Router
Configure linting: ruff, black, mypy, prettier
Create Makefile with common commands
Day 3: Configuration & Secrets
Create backend/app/core/config.py (Pydantic Settings)
Define settings: database_url, redis_url, API keys (Reddit, Anthropic, OpenAI), agent config
Create .env.example with all required environment variables
Implement backend/app/core/security.py for JWT handling
Document secret rotation policy
Day 4: Database & Migrations
Create backend/app/models/base.py with SQLAlchemy base, TimestampMixin, UUIDMixin
Implement ORM models:
beliefs (JSONB for JSON-LD format, confidence float, tags array)
interactions (content, reddit_id, metadata JSONB, pgvector embedding)
belief_updates (audit log with old/new values, reason)
pending_posts (moderation queue)
agent_config (key-value store)
Initialize Alembic, create initial migration
Test migration rollback
Day 5: Docker & Environment Setup
Create backend/Dockerfile (Python 3.11-slim, multi-stage)
Create frontend/Dockerfile (Node 20, production build)
Write docker-compose.yml (postgres with pgvector, redis, backend, agent-worker, frontend)
Create docs/ONBOARDING.md with quick start guide
Test full stack startup, document troubleshooting
Phase 1: Core Services (Weeks 2-4)
Week 2: Foundation Services
Service 1: Health Checks (Days 1-2)
Endpoints: /health, /health/ready, /health/agent
Structured JSON logging
Prometheus metrics endpoint
Service 2: Auth Service (Days 3-5)
JWT token generation/validation
Admin user model (single admin for MVP)
Protected route middleware
Contract tests: token validation behavior
Week 3: Core Agent Services
Service 3: Memory Store (Days 1-2)
Implement IMemoryStore interface (ABC)
Methods: query_beliefs(), update_belief(), log_interaction(), search_history()
PostgreSQL backend with JSONB queries
Contract tests: CRUD maintains ACID properties
Service 4: Reddit Client (Days 3-4)
Implement IRedditClient interface
Wrap asyncpraw with rate limiting (60 req/min)
Methods: get_new_posts(), search_posts(), submit_post(), reply()
Contract tests: retry logic with mock Reddit API
Service 5: LLM Client (Day 5)
Implement ILLMClient interface
Anthropic Claude integration with prompt caching
System prompt builder (persona + beliefs)
OpenAI fallback
Contract tests: prompt formatting validation
Week 4: Agent Logic & Integration
Service 6: Agent Logic (Days 1-2)
Decision engine: perception → retrieval → decision
Context assembly from belief graph + memory
Draft response generation
Contract tests: context → valid response
Service 7: Belief Updater (Days 3-4)
Bayesian confidence update logic
Consistency checker (draft vs beliefs)
Audit logging
Contract tests: deterministic confidence updates
Service 8: Moderation (Day 5)
OpenAI Moderation API integration
Queue management (pending_posts table)
Admin approval workflow
Contract tests: flagged content → queue (not posted)
Service 9: Agent Event Loop (Days 6-7)
Main loop: monitor → perceive → decide → moderate → act
Graceful shutdown, error recovery
Integration tests: end-to-end with test subreddit
API Contracts (Interface-First Design)
OpenAPI Schema (docs/api/openapi.yaml)
GET /api/v1/activity - Recent agent activity
GET /api/v1/beliefs - Retrieve belief graph
PUT /api/v1/beliefs/{id} - Update belief
GET /api/v1/moderation/pending - Pending queue
POST /api/v1/moderation/approve - Approve post
POST /api/v1/settings - Update config
Python ABCs (contracts before implementation)
IMemoryStore - Memory operations
IRedditClient - Reddit API interactions
ILLMClient - LLM operations
IModerationService - Content filtering
Database Schema
PostgreSQL 15+ with extensions: pgvector, uuid-ossp Tables:
beliefs - JSONB belief_data (JSON-LD), confidence, tags[], timestamps
interactions - content, reddit_id, metadata JSONB, embedding VECTOR(1536)
belief_updates - audit log with old/new values, reason, trigger_type
pending_posts - moderation queue with status
agent_config - key-value configuration store
Technology Stack Justification
Backend: FastAPI
Native async for Reddit API + LLM calls
Automatic OpenAPI generation (contract-first)
Dependency injection via Depends()
Already using Pydantic in legacy code
Frontend: Next.js 14
SSR for dashboard performance
TypeScript contracts from OpenAPI (openapi-typescript-codegen)
React Server Components for data fetching
Can deploy to Vercel (free tier)
Database: PostgreSQL + JSONB
JSON-LD compatible (future RDF migration path)
JSONB queries handle 80% of graph needs
pgvector for semantic search
ACID guarantees for belief updates
Deployment: DigitalOcean + Vercel
DO droplet ($10/mo): agent core, PostgreSQL, Redis
Vercel (free): Next.js dashboard
Docker Compose for local dev parity
Success Criteria
Phase 0 (Week 1)
✅ Docker Compose stack starts successfully
✅ Database migrations apply cleanly
✅ OpenAPI spec validates
✅ Onboarding docs complete
Phase 1 (Weeks 2-4)
✅ Agent posts 1 comment/day in test subreddit
✅ Belief graph stores 10 initial beliefs
✅ Dashboard displays activity feed
✅ Moderation queue functional
✅ 80% unit test coverage on core services
Risk Mitigation
Reddit API Rate Limits: Token bucket limiter, caching, prioritization
LLM Costs: Prompt caching, use Haiku for checks, daily budget circuit breaker
Belief Graph Complexity: Start flat, add visualization, quarterly pruning
Moderation False Positives: Adjustable threshold, human-in-loop initially
First Actions (Day 1 Morning)
# Create project structure
mkdir -p docs/{decisions,api,architecture,runbooks}
mkdir -p backend/app/{core,api/v1,services,models,schemas,agent,db,tests}
mkdir -p frontend

# Initialize git tracking
git add docs/ backend/ frontend/
git commit -m "docs: Add ADR-001 and project structure"

# Create ADR-001
# Document architecture decisions in docs/decisions/ADR-001-tech-stack.md
This plan follows 0_dev.md quality standards: contract-first design, separation of concerns, explicit interfaces, and comprehensive documentation.