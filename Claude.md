# Claude Usage Guide (MVP Reddit AI Agent)

Practical guardrails and instructions for using Claude Code with this repository. Aligns with [0_dev.md](docs/0_dev.md), the MVP technical spec, week plans, and the architecture build plan.

> **Purpose**: This file provides Claude Code with project-specific context, standards, and workflows to maximize effectiveness when working in this codebase.

## Overview

This repo implements an autonomous Reddit AI agent with:
- **Belief graph**: Self-model with versioned stances, confidence tracking, evidence linking
- **Memory system**: Episodic memory (past Reddit interactions) + semantic retrieval via FAISS
- **Multi-persona**: All data keyed by `persona_id`, ready for multiple Reddit accounts
- **Moderation layer**: Auto/manual posting modes, review queue, content evaluation
- **Control panel**: Next.js dashboard for monitoring, belief editing, moderation, stats

## Project Structure

```
BubbleViews/
├── backend/                    # FastAPI + Python 3.11
│   ├── app/
│   │   ├── core/              # Config, database, logging, security
│   │   ├── api/v1/            # REST endpoints (health, auth, activity, beliefs, moderation, settings)
│   │   ├── services/          # Core logic (memory, reddit, llm, moderation, retrieval, belief_updater)
│   │   │   └── interfaces/    # ABC contracts (IMemoryStore, IRedditClient, ILLMClient)
│   │   ├── models/            # SQLAlchemy ORM (personas, beliefs, interactions, pending_posts)
│   │   ├── schemas/           # Pydantic validation
│   │   ├── agent/             # Agent loop (perception → retrieval → decision → action)
│   │   ├── middleware/        # Request ID, logging, rate limiting
│   │   └── repositories/      # Data access layer
│   ├── data/                  # SQLite DB + FAISS index
│   ├── tests/                 # Unit + integration tests (AAA style)
│   ├── alembic/               # Database migrations (forward-only)
│   ├── scripts/               # Seeding, utilities
│   └── pyproject.toml
├── frontend/                  # Next.js 14 + TypeScript + Tailwind
│   ├── app/                   # Pages (activity, beliefs, moderation, settings)
│   ├── components/            # Reusable UI (belief-graph, activity-feed, persona-selector)
│   ├── lib/                   # API client (generated from OpenAPI)
│   └── package.json
├── docs/
│   ├── decisions/             # ADRs (tech stack, architecture choices)
│   ├── api/                   # OpenAPI spec (openapi.yaml)
│   ├── architecture/          # System diagrams, data flows
│   └── runbooks/              # Operations guides (deployment, secrets, rollback)
└── .env.example               # Template for environment variables
```

## Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| **Backend** | FastAPI + Python 3.11 | Async, OpenAPI generation, DI via `Depends()` |
| **Frontend** | Next.js 14 + TypeScript | SSR-ready, type-safe, Vercel deployment |
| **Database** | SQLite + JSON1 | MVP choice; Postgres-ready contracts (migrations use Alembic) |
| **ORM** | SQLAlchemy + aiosqlite | Async sessions, WAL mode enabled |
| **LLM** | OpenRouter API | Model-agnostic; primary: `openai/gpt-5.1-mini`, secondary: `anthropic/claude-4.5-haiku` |
| **Embeddings** | sentence-transformers | Local generation (all-MiniLM-L6-v2), 384-dim |
| **Vector Search** | FAISS (CPU) | In-memory index, persists to `data/faiss_index.bin` |
| **Reddit API** | asyncpraw | Rate limiting (60 req/min token bucket), exponential backoff retries |
| **Auth** | JWT via python-jose | Stateless tokens, bcrypt for passwords |
| **Deployment** | DigitalOcean (backend/agent) + Vercel (dashboard) | Hybrid: always-on agent loop on DO, dashboard on Vercel |

## Key Commands

```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
cp .env.example .env      # Edit with real credentials
alembic upgrade head      # Apply migrations
python scripts/seed_admin.py
python scripts/seed_default_config.py
python scripts/seed_demo.py  # Optional: demo persona with beliefs

# Run backend
uvicorn app.main:app --reload --port 8000

# Run agent loop
python scripts/run_agent.py

# Run tests
pytest --cov=app --cov-report=html
```

```bash
# Frontend setup
cd frontend
npm install
cp .env.example .env      # Set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev               # Runs on localhost:3000
npm run build             # Production build
```

## Models & LLM Transport

- **Default**: OpenRouter with `anthropic/claude-4.5-haiku` for speed and consistency checks; `openai/gpt-5.1-mini` as fast path for drafting.
- **Switch models**: Only when task needs deeper reasoning (update `RESPONSE_MODEL` / `CONSISTENCY_MODEL` in `.env`).
- **Set explicit `max_tokens` and temperature**: ≤0.5 for production paths (drafts: 0.7, consistency: 0.3).
- **Stream replies**: When posting to Reddit or dashboard to cut off long generations.
- **Correlation IDs**: Always send from middleware into Claude calls; log `model`, `tokens_in/out`, `tool_calls`, `cost`.

## Prompt Shape (Claude-Aligned)

Follow structured prompt pattern:

1. **System**: Repository-level guardrails
   - Persona contract (tone, style, values)
   - Safety rules (Reddit TOS, refusal policy: "If unsure, say you don't know or ask for more input")
   - Moderation mode (auto/manual)
   - Cost-sensitivity ("be concise")
   - Reddit etiquette

2. **Developer**: Task recipe
   - Tools available (Reddit client, memory/belief store, embeddings)
   - Expected output shape (JSON schemas)
   - Constraints (no ad-hoc web calls; cite retrieved memories)

3. **Context**: Stitched from retrieval pipeline (Week 4)
   - Persona config
   - Belief/stance snapshot (current confidence, relations)
   - Recent Reddit thread (title, OP, parent comment)
   - Top FAISS matches of past comments (self-consistency)
   - Moderation flags

4. **User**: Live ask
   - Reddit post/comment to draft
   - Moderation decision
   - Belief update request

**Best practices**:
- Use delimiters (triple backticks or XML tags) for context blocks
- Avoid mixing instructions with user content
- Few-shot when useful: 1-2 exemplars for "good" Reddit replies and belief updates
- Prune old history aggressively to stay within context budget

## Tool Use & Structured Outputs

- **Prefer tool calls** for retrieval, memory writes, belief graph updates, Reddit actions; avoid free-form guesses about external state.
- **Use tight JSON schemas**: Include `persona_id`, `reddit_id`, `belief_id`, and confidence fields (Postgres upgrade-ready).
- **Validate tool outputs** before echoing to user (ensure required fields exist, handle 429/403 gracefully).
- **When tool fails**: Return compact, actionable error + retryable suggestion; never fabricate results.
- **For dashboards/APIs**: Return machine-friendly JSON (no Markdown) unless explicitly asked.

## Retrieval & Memory Discipline

**Retrieval order** (assemble_context in `retrieval.py`):
1. Persona config/governor flags
2. Belief graph (current stance + relations)
3. Semantic nearest past comments (FAISS top-k=5)
4. Live Reddit thread
5. Moderation status

**Cite retrieved self-history** when making claims; if nothing relevant found, say so and lower confidence.

**Keep snippets small** (<150 words each), deduplicate to avoid token bloat; summarize long chains before handing to LLM.

**Evidence linking**: Each belief can have evidence_links (source_type: `reddit_comment | external_link | note`, strength: `weak | moderate | strong`).

## Persona & Belief Consistency

- **Speak in persona voice** defined in config; avoid adopting user's tone unless allowed.
- **Update beliefs only via designated mutation tool** (no silent belief changes). Provide rationale and confidence deltas; capture evidence IDs when available.
- **If new evidence contradicts prior stances**: Mark previous stances as deprecated, log evolution (matches belief versioning in Week 3/4).
- **Bayesian updates**: Strong statements require strong proofs. Evidence strength mapping:
  ```python
  EVIDENCE_DELTA = {
      "weak": 0.05,
      "moderate": 0.10,
      "strong": 0.20
  }
  ```
- **Locked stances**: If `stance_version.status == "locked"`, reject automatic updates; require human approval.

## Reddit-Specific Guardrails

- **Respect subreddit rules and rate limits**: 60 req/min token bucket; avoid posting if moderation set to manual or readiness probes fail.
- **Never leak secrets or internal config** (`config.json`); strip PII and sensitive tokens from tool outputs before replying.
- **Keep responses concise**, cite sources when summarizing, avoid banned/controversial content unless persona explicitly allows.
- **Rate limiting**: Token bucket enforced in `rate_limiter.py`; retries with exponential backoff (1s, 2s, 4s) + jitter.

## Safety, Refusals, and Tone

- **Use Anthropic safety defaults**: Decline illegal or harmful content; de-escalate heated threads; avoid medical or financial advice unless persona is qualified.
- **When unsure or context is thin**: Ask for clarifying follow-up or reply "I don't know based on what I have."
- **Cap confidence claims**: Include short "why I think this" notes when acting autonomously.
- **Moderation layer**: Content evaluation rules in `moderation.py` (banned keywords, length limits, placeholder for LLM toxicity check).
- **Auto/manual mode**: Controlled via `agent_config.auto_posting_enabled`; review queue in `pending_posts` table.

## Testing & Ops

**Testing standards** (from `0_dev.md`):
- **Unit tests**: AAA style (Arrange, Act, Assert); isolate side effects behind mocks/fakes.
- **Coverage**: >80% on core, api, models; mutation testing for core algorithms.
- **Contract tests**: Prompt assembly, tool payloads, JSON schemas for belief/Reddit actions.
- **Integration tests**: End-to-end with test subreddit (mocked Reddit client).

**Observability**:
- **Structured logs**: JSON with correlation IDs, cost per request, `model`, `tokens_in/out`.
- **Health checks**: `/health`, `/health/ready` (DB + OpenRouter), `/health/agent` (loop status).
- **Cost tracking**: Log every LLM call with cost calculation (pricing table in `llm_client.py`).
- **Error metrics**: Alert on spikes in refusals, tool failures, token overages.

**Ops practices**:
- Run dry runs in staging persona before production.
- Snapshot belief graph after mutations and on deploys.
- Document rollback plans (see `docs/runbooks/`).

## Quickstart Prompt Skeleton

```
System: Persona + safety + moderation mode + refusal rules.
Developer: Tools available (reddit_client, memory_store, belief_graph, embedding_search), required JSON schema, cost guardrails.
Context:
  <persona>...</persona>
  <beliefs>...</beliefs>
  <past_comments>...</past_comments>
  <thread>...</thread>
  <moderation>auto|manual</moderation>
User: Draft a reply to this Reddit comment...
Expect: JSON {
  "persona_id": "...",
  "reply_markdown": "...",
  "confidence": 0.72,
  "references": ["comment:abc", "belief:xyz"]
}
```

## References

- [0_dev.md](docs/0_dev.md) - Engineering quality guidelines
- [MVP Technical Spec](docs/MVP_Reddit_AI_Agent_Technical_Specification.md) - Full system design
- [Architecture Build](docs/MVP%20Reddit%20AI%20Agent%20-%20Architecture%20Build.md) - Phase-by-phase build plan
- [Week 2 Plan](docs/week2.md) - Foundation services
- [Week 3 Plan](docs/week3.md) - Core agent services
- [Week 4 Plan](docs/week4.md) - Agent loop, belief updates, dashboard
- [Brainstorming](docs/brainstorming.md) - Original ideation and UX concepts
- [Diagram](docs/architecture/system-diagram.md) - Diagram of all flows
---

**Last updated**: 2025-11-24
**Version**: MVP (Weeks 1-4 scope)
