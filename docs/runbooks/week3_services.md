# Week 3 Services Runbook

Operations guide for Week 3 core services: Memory Store, Reddit Client, LLM Client, and Moderation.

**Version**: 1.0
**Last Updated**: 2025-11-24
**Status**: Production-ready for MVP

---

## Table of Contents

1. [Overview](#overview)
2. [Service Architecture](#service-architecture)
3. [Database Operations](#database-operations)
4. [Memory Store Operations](#memory-store-operations)
5. [Reddit Client Operations](#reddit-client-operations)
6. [LLM Client Operations](#llm-client-operations)
7. [Moderation Service Operations](#moderation-service-operations)
8. [FAISS Index Management](#faiss-index-management)
9. [Cost Tracking and Monitoring](#cost-tracking-and-monitoring)
10. [Troubleshooting](#troubleshooting)
11. [Maintenance Procedures](#maintenance-procedures)

---

## Overview

Week 3 implements the core agent services with contract-based design and persona isolation:

- **Memory Store**: Belief graph, interaction history, semantic search
- **Reddit Client**: Rate-limited API access, retry logic, post/reply operations
- **LLM Client**: OpenRouter integration, cost tracking, consistency checking
- **Moderation Service**: Content evaluation, queue management, auto-posting control

All services enforce strict persona isolation to prevent data leakage.

---

## Service Architecture

### Interface Contracts

All services implement abstract interfaces (ABC):

```
app/services/interfaces/
├── memory_store.py        # IMemoryStore
├── reddit_client.py       # IRedditClient
├── llm_client.py          # ILLMClient
└── moderation.py          # IModerationService
```

### Implementation

```
app/services/
├── memory_store.py        # SQLiteMemoryStore
├── reddit_client.py       # AsyncPRAWClient
├── llm_client.py          # OpenRouterClient
├── moderation.py          # ModerationService
├── embedding.py           # EmbeddingService (FAISS)
└── rate_limiter.py        # TokenBucket
```

---

## Database Operations

### Seed Default Persona

```bash
cd backend
python scripts/seed_persona.py
```

Creates default persona with initial beliefs.

### Seed Demo Data

```bash
python scripts/seed_demo.py
```

Adds sample beliefs, interactions, and config for testing.

### Apply Migrations

```bash
alembic upgrade head
```

### Rollback Migration

```bash
alembic downgrade -1
```

### Check Database Status

```python
from app.core.database import engine
from sqlalchemy import inspect

async with engine.connect() as conn:
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    print("Tables:", tables)
```

---

## Memory Store Operations

### Query Belief Graph

```python
from app.services.memory_store import SQLiteMemoryStore

async with async_session() as session:
    memory_store = SQLiteMemoryStore(session)
    graph = await memory_store.query_belief_graph("persona_id")
    print("Nodes:", len(graph["nodes"]))
    print("Edges:", len(graph["edges"]))
```

### Update Stance Version

```python
stance_id = await memory_store.update_stance_version(
    persona_id="persona_id",
    belief_id="belief_id",
    text="New stance text",
    confidence=0.85,
    rationale="New evidence from research"
)
```

### Log Interaction

```python
interaction_id = await memory_store.log_interaction(
    persona_id="persona_id",
    content="Comment content here",
    interaction_type="comment",
    metadata={
        "reddit_id": "t1_abc123",
        "subreddit": "technology",
        "parent_id": "t3_parent"
    }
)
```

### Search History (Semantic)

```python
results = await memory_store.search_history(
    persona_id="persona_id",
    query="artificial intelligence and ethics",
    limit=5
)
```

---

## Reddit Client Operations

### Fetch New Posts

```python
from app.services.reddit_client import AsyncPRAWClient

client = AsyncPRAWClient(
    client_id=settings.REDDIT_CLIENT_ID,
    client_secret=settings.REDDIT_CLIENT_SECRET,
    user_agent=settings.REDDIT_USER_AGENT,
    username=settings.REDDIT_USERNAME,
    password=settings.REDDIT_PASSWORD
)

posts = await client.get_new_posts(
    subreddits=["MachineLearning", "artificial"],
    limit=10
)
```

### Search Posts

```python
results = await client.search_posts(
    query="deep learning transformers",
    subreddit="MachineLearning",
    time_filter="week"
)
```

### Submit Post (Dry Run)

**WARNING**: Only use in test mode to avoid accidental posting.

```python
# Set test mode or use mocked client
post_id = await client.submit_post(
    subreddit="test",
    title="Test Post",
    content="This is a test"
)
```

### Reply to Comment

```python
reply_id = await client.reply(
    parent_id="t1_comment_id",
    content="Reply text here"
)
```

### Rate Limit Status

```python
from app.services.rate_limiter import TokenBucket

rate_limiter = TokenBucket(capacity=60, refill_rate=1.0)
print(f"Tokens available: {rate_limiter.tokens}")
```

---

## LLM Client Operations

### Generate Response

```python
from app.services.llm_client import OpenRouterClient

llm_client = OpenRouterClient(
    api_key=settings.OPENROUTER_API_KEY,
    base_url=settings.OPENROUTER_BASE_URL,
    primary_model="anthropic/claude-3.5-haiku",
    secondary_model="anthropic/claude-3.5-haiku"
)

result = await llm_client.generate_response(
    system_prompt="You are a helpful AI assistant.",
    context={"topic": "machine learning"},
    user_message="Explain transformers in simple terms"
)

print("Response:", result["response"])
print("Tokens:", result["tokens"])
print("Cost:", result["cost"])
```

### Check Consistency

```python
beliefs = [
    {"id": "b1", "text": "AI is beneficial", "confidence": 0.9},
    {"id": "b2", "text": "AI needs careful regulation", "confidence": 0.8}
]

result = await llm_client.check_consistency(
    draft_response="AI is completely unregulated and that's fine.",
    beliefs=beliefs
)

print("Consistent:", result["is_consistent"])
print("Conflicts:", result["conflicts"])
```

### Monitor LLM Costs

Check logs for cost tracking:

```bash
grep -i "cost" logs/app.log | tail -20
```

Or programmatically:

```python
import json

total_cost = 0
with open("logs/app.log") as f:
    for line in f:
        try:
            log_entry = json.loads(line)
            if "cost" in log_entry:
                total_cost += log_entry["cost"]
        except:
            pass

print(f"Total LLM cost: ${total_cost:.4f}")
```

---

## Moderation Service Operations

### Evaluate Content

```python
from app.services.moderation import ModerationService

async with async_session() as session:
    mod_service = ModerationService(session)

    evaluation = await mod_service.evaluate_content(
        persona_id="persona_id",
        content="This is a comment about technology trends.",
        context={"subreddit": "technology", "post_type": "comment"}
    )

    print("Approved:", evaluation["approved"])
    print("Flagged:", evaluation["flagged"])
    print("Flags:", evaluation["flags"])
    print("Action:", evaluation["action"])
```

### Enqueue for Review

```python
item_id = await mod_service.enqueue_for_review(
    persona_id="persona_id",
    content="Draft comment requiring approval",
    metadata={
        "post_type": "comment",
        "target_subreddit": "technology",
        "parent_id": "t3_parent",
        "evaluation": evaluation
    }
)
```

### Check Auto-Posting Status

```python
is_enabled = await mod_service.is_auto_posting_enabled("persona_id")
print(f"Auto-posting enabled: {is_enabled}")
```

### Enable/Disable Auto-Posting

```python
from app.models.agent_config import AgentConfig

config = AgentConfig(
    persona_id="persona_id",
    config_key="auto_posting_enabled"
)
config.set_value(True)  # or False to disable

session.add(config)
await session.commit()
```

### Posting Decision Logic

```python
should_post = await mod_service.should_post_immediately(
    persona_id="persona_id",
    evaluation=evaluation
)

if should_post:
    # Post directly
    await reddit_client.reply(parent_id, content)
else:
    # Enqueue for manual review
    await mod_service.enqueue_for_review(...)
```

---

## FAISS Index Management

### Location

```
backend/data/faiss_index.bin
backend/data/faiss_metadata.json
```

### Rebuild Index

```python
from app.services.embedding import EmbeddingService
from app.services.memory_store import SQLiteMemoryStore

# Initialize services
embedding_service = EmbeddingService(index_path="data/faiss_index.bin")
memory_store = SQLiteMemoryStore(session)

# Fetch all interactions
from sqlalchemy import select
from app.models.interaction import Interaction

stmt = select(Interaction).where(Interaction.persona_id == "persona_id")
result = await session.execute(stmt)
interactions = result.scalars().all()

# Rebuild index
for interaction in interactions:
    embedding = embedding_service.generate_embedding(interaction.content)
    embedding_service.add_to_index(embedding, interaction.id)

# Save
embedding_service.save_index()
print(f"Rebuilt index with {len(interactions)} interactions")
```

### Verify Index

```python
# Load index
embedding_service.load_index()

# Test search
query_emb = embedding_service.generate_embedding("test query")
results = embedding_service.search(query_emb, k=5)

print(f"Found {len(results)} results")
for interaction_id, distance in results:
    print(f"  {interaction_id}: distance={distance:.4f}")
```

### Backup Index

```bash
cp backend/data/faiss_index.bin backend/data/faiss_index_backup_$(date +%Y%m%d).bin
```

---

## Cost Tracking and Monitoring

### Daily Cost Report

```python
from datetime import datetime, timedelta
import json

start_date = datetime.now() - timedelta(days=1)
total_cost = 0
call_count = 0

with open("logs/app.log") as f:
    for line in f:
        try:
            log_entry = json.loads(line)
            if "cost" in log_entry and "timestamp" in log_entry:
                log_time = datetime.fromisoformat(log_entry["timestamp"])
                if log_time >= start_date:
                    total_cost += log_entry["cost"]
                    call_count += 1
        except:
            pass

print(f"Last 24h: {call_count} LLM calls, ${total_cost:.4f} total cost")
print(f"Average: ${total_cost/call_count:.6f} per call")
```

### Cost Alerts

Set up alerts for daily spend exceeding threshold:

```python
DAILY_COST_THRESHOLD = 5.00  # $5 per day

if total_cost > DAILY_COST_THRESHOLD:
    print(f"WARNING: Daily cost ${total_cost:.2f} exceeds threshold ${DAILY_COST_THRESHOLD:.2f}")
    # Send alert (email, Slack, etc.)
```

### Model Usage Breakdown

```python
from collections import defaultdict

model_costs = defaultdict(float)
model_calls = defaultdict(int)

with open("logs/app.log") as f:
    for line in f:
        try:
            log_entry = json.loads(line)
            if "cost" in log_entry and "model" in log_entry:
                model = log_entry["model"]
                model_costs[model] += log_entry["cost"]
                model_calls[model] += 1
        except:
            pass

for model, cost in model_costs.items():
    calls = model_calls[model]
    print(f"{model}: {calls} calls, ${cost:.4f} total, ${cost/calls:.6f} avg")
```

---

## Troubleshooting

### Database Connection Errors

**Symptom**: `OperationalError: database is locked`

**Solution**:
```bash
# Check for WAL mode
sqlite3 backend/data/agent.db "PRAGMA journal_mode;"

# Should output: wal
# If not, enable:
sqlite3 backend/data/agent.db "PRAGMA journal_mode=WAL;"
```

### Reddit API Rate Limiting

**Symptom**: `429 Too Many Requests`

**Solution**:
```python
# Check rate limiter status
from app.services.rate_limiter import TokenBucket

rate_limiter = client.rate_limiter
print(f"Tokens available: {rate_limiter.tokens}")

# Wait for tokens to refill (1 per second)
import asyncio
await asyncio.sleep(10)
```

### FAISS Index Corruption

**Symptom**: `RuntimeError: Error loading FAISS index`

**Solution**:
```bash
# Restore from backup
cp backend/data/faiss_index_backup_YYYYMMDD.bin backend/data/faiss_index.bin

# Or rebuild from scratch (see FAISS Index Management)
```

### LLM Client Authentication Errors

**Symptom**: `AuthenticationError: Invalid API key`

**Solution**:
```bash
# Verify API key in .env
cat backend/.env | grep OPENROUTER_API_KEY

# Test key directly
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $OPENROUTER_API_KEY"
```

### Memory Leak Detection

**Symptom**: Increasing memory usage over time

**Solution**:
```python
import tracemalloc

tracemalloc.start()

# Run operations

current, peak = tracemalloc.get_traced_memory()
print(f"Current memory usage: {current / 10**6:.2f} MB")
print(f"Peak memory usage: {peak / 10**6:.2f} MB")

tracemalloc.stop()
```

### Persona Isolation Verification

**Symptom**: Concerned about data leakage

**Solution**:
```bash
# Run isolation tests
pytest backend/tests/integration/test_persona_isolation.py -v
```

---

## Maintenance Procedures

### Weekly Tasks

1. **Backup Database**
   ```bash
   sqlite3 backend/data/agent.db ".backup backend/data/agent_backup_$(date +%Y%m%d).db"
   ```

2. **Backup FAISS Index**
   ```bash
   cp backend/data/faiss_index.bin backend/data/faiss_index_backup_$(date +%Y%m%d).bin
   ```

3. **Review Logs for Errors**
   ```bash
   grep -i "error" logs/app.log | tail -50
   ```

4. **Check Cost Trends**
   ```bash
   python scripts/cost_report.py
   ```

### Monthly Tasks

1. **Vacuum Database**
   ```bash
   sqlite3 backend/data/agent.db "VACUUM;"
   ```

2. **Optimize FAISS Index**
   ```python
   # Rebuild with optimized parameters if index is large
   embedding_service.save_index()
   ```

3. **Review and Archive Old Logs**
   ```bash
   gzip logs/app.log.$(date -d "last month" +%Y%m).log
   ```

4. **Update Dependencies**
   ```bash
   pip list --outdated
   pip install -U package_name
   ```

### Before Deployment

1. **Run Full Test Suite**
   ```bash
   pytest backend/tests/ --cov=app --cov-report=html
   ```

2. **Export Updated OpenAPI Schema**
   ```bash
   python backend/scripts/export_openapi.py
   ```

3. **Verify All Services**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/health/ready
   ```

4. **Check Configuration**
   ```bash
   # Verify all required env vars
   python backend/scripts/check_config.py
   ```

---

## Quick Reference

### Service Dependencies

```
SQLiteMemoryStore
  ├── AsyncSession (database)
  └── EmbeddingService (FAISS)

AsyncPRAWClient
  └── TokenBucket (rate limiting)

OpenRouterClient
  └── AsyncOpenAI (API client)

ModerationService
  └── AsyncSession (database)
```

### Key Configuration

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./data/agent.db

# Reddit API
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=...
REDDIT_PASSWORD=...

# LLM
OPENROUTER_API_KEY=...
RESPONSE_MODEL=anthropic/claude-3.5-haiku
CONSISTENCY_MODEL=anthropic/claude-3.5-haiku

# Moderation
AUTO_POSTING_ENABLED=false
```

### Common Queries

```sql
-- Count interactions by persona
SELECT persona_id, COUNT(*) FROM interactions GROUP BY persona_id;

-- Recent pending posts
SELECT * FROM pending_posts WHERE status='pending' ORDER BY created_at DESC LIMIT 10;

-- Beliefs with low confidence
SELECT * FROM belief_nodes WHERE current_confidence < 0.5;

-- Auto-posting status per persona
SELECT persona_id, config_value FROM agent_config WHERE config_key='auto_posting_enabled';
```

---

**Next Steps**: See Week 4 runbook for agent loop, belief updates, and dashboard operations.

**Questions?** Review docs/0_dev.md for engineering standards and docs/MVP_Reddit_AI_Agent_Technical_Specification.md for architecture details.
