# Week 3 Plan — Core Agent Services (Memory, Reddit Client, LLM, Moderation)

**Scope**: Build persona-scoped memory + belief graph, Reddit client, LLM client, and moderation scaffold per contract-first design. Ready for multi-persona and self-consistency retrieval. Align with MVP Technical Specification and 0_dev quality standards.

**Estimated effort**: 5 days, 42 micro-tasks

---

## Day 1: Database Schema & Migrations

### Task 1.1: Persona Table Migration
**Input**: Alembic setup from Week 1
**Action**:
1. Create migration file for personas table
2. Define schema:
   ```sql
   CREATE TABLE personas (
       id TEXT PRIMARY KEY,
       reddit_username TEXT NOT NULL UNIQUE,
       display_name TEXT,
       config JSON NOT NULL,
       created_at TEXT DEFAULT CURRENT_TIMESTAMP,
       updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
       CHECK (json_valid(config))
   );
   ```
3. Add index on reddit_username
4. Test migration apply/rollback

**Output**: Personas table
**Tests**: Migration test suite
**DoD**: Table exists with all constraints

### Task 1.2: Belief Graph Core Tables
**Input**: Personas table
**Action**:
1. Create migration for belief_nodes table:
   - id, persona_id (FK), title, summary, current_confidence
   - tags (JSON array), created_at, updated_at
   - Indices: persona_id, current_confidence
2. Create belief_edges table:
   - id, persona_id (FK), source_id (FK), target_id (FK)
   - relation (enum: supports, contradicts, depends_on, evidence_for)
   - weight (0-1), created_at, updated_at
   - Indices: persona_id, relation
3. Add FK constraints with CASCADE delete

**Output**: Belief graph storage
**Tests**: Migration test, FK constraint validation
**DoD**: Can create nodes and edges with relationships

### Task 1.3: Stance Versioning Tables
**Input**: Belief nodes
**Action**:
1. Create stance_versions table:
   - id, persona_id (FK), belief_id (FK)
   - text, confidence (0-1)
   - status (current | deprecated | locked)
   - rationale, created_at
   - Index on status
2. Create evidence_links table:
   - id, persona_id (FK), belief_id (FK)
   - source_type (reddit_comment | external_link | note)
   - source_ref, strength (weak | moderate | strong)
   - created_at

**Output**: Stance history tracking
**Tests**: Version history queries
**DoD**: Can store multiple stance versions per belief

### Task 1.4: Interactions & Memory Tables
**Input**: Personas table
**Action**:
1. Create interactions table:
   - id, persona_id (FK), content, interaction_type
   - reddit_id (unique), subreddit, parent_id
   - metadata (JSON), embedding (BLOB), created_at
   - Indices: persona_id, subreddit, created_at DESC
2. Create belief_updates table (audit log):
   - id, persona_id (FK), belief_id (FK)
   - old_value (JSON), new_value (JSON)
   - reason, trigger_type, updated_by, created_at
   - Index on belief_id, created_at DESC

**Output**: Episodic memory and audit trail
**Tests**: Interaction logging, audit queries
**DoD**: Full interaction history queryable

### Task 1.5: Moderation Queue Table
**Input**: Personas table
**Action**:
1. Create pending_posts table:
   - id, persona_id (FK), content, post_type
   - target_subreddit, parent_id, draft_metadata (JSON)
   - status (pending | approved | rejected)
   - reviewed_by, reviewed_at, created_at
   - Indices: status, created_at DESC

**Output**: Moderation workflow storage
**Tests**: Queue CRUD operations
**DoD**: Posts can be queued and reviewed

### Task 1.6: Agent Config Table
**Input**: Personas table
**Action**:
1. Create agent_config table:
   - id, persona_id (FK), config_key, config_value (JSON)
   - updated_at
   - UNIQUE constraint on (persona_id, config_key)
   - JSON validity check
2. Enable WAL mode for SQLite:
   ```sql
   PRAGMA journal_mode=WAL;
   ```

**Output**: Configuration storage
**Tests**: Config CRUD, uniqueness constraint
**DoD**: Per-persona key-value config works

### Task 1.7: Seed Default Persona
**Input**: All tables
**Action**:
1. Create `backend/scripts/seed_persona.py`
2. Insert default persona:
   - id: generate UUID
   - reddit_username: from config
   - config: default settings
3. Seed initial beliefs (5-10 core beliefs)
4. Add to setup instructions

**Output**: Default persona with beliefs
**Tests**: Manual verification
**DoD**: Default persona ready for use

---

## Day 2: Memory Store Implementation

### Task 2.1: Memory Store Interface (IMemoryStore)
**Input**: None
**Action**:
1. Create `backend/app/services/interfaces/memory_store.py`
2. Define abstract base class `IMemoryStore`:
   ```python
   class IMemoryStore(ABC):
       @abstractmethod
       async def query_belief_graph(persona_id: str) -> Dict

       @abstractmethod
       async def update_stance_version(
           persona_id: str, belief_id: str,
           text: str, confidence: float, rationale: str
       ) -> str

       @abstractmethod
       async def append_evidence(
           persona_id: str, belief_id: str,
           source_type: str, source_ref: str, strength: str
       )

       @abstractmethod
       async def log_interaction(
           persona_id: str, content: str,
           interaction_type: str, metadata: dict
       ) -> str

       @abstractmethod
       async def search_history(
           persona_id: str, query: str, limit: int
       ) -> List[Dict]
   ```
3. Document each method's contract

**Output**: Memory interface contract
**Tests**: N/A (interface only)
**DoD**: Interface defines all required operations

### Task 2.2: SQLite Session Management
**Input**: Database configuration
**Action**:
1. Create `backend/app/core/database.py`
2. Set up async SQLAlchemy engine with aiosqlite
3. Create session factory with:
   - WAL mode enabled
   - Foreign key constraints enabled
   - Timeout configured (5 seconds)
4. Implement `get_db()` dependency

**Output**: Database session management
**Tests**: Connection pool test
**DoD**: Sessions acquired/released correctly

### Task 2.3: Belief Graph Query Implementation
**Input**: IMemoryStore interface, DB sessions
**Action**:
1. Create `backend/app/services/memory_store.py`
2. Implement `SQLiteMemoryStore` class
3. Implement `query_belief_graph()`:
   - Query all nodes for persona
   - Query all edges for persona
   - Return as dict: `{nodes: [...], edges: [...]}`
4. Support optional tag filtering

**Output**: Belief graph retrieval
**Tests**: Unit test with seeded beliefs
**DoD**: Returns complete graph structure

### Task 2.4: Stance Update with Lock Enforcement
**Input**: Belief graph queries
**Action**:
1. Implement `update_stance_version()`:
   - Check if current stance is locked
   - If locked, reject update with error
   - Mark current stance as deprecated
   - Insert new stance with "current" status
   - Log to belief_updates table
2. Ensure atomic transaction

**Output**: Stance versioning logic
**Tests**: Unit tests (normal update, locked stance, concurrent updates)
**DoD**: Lock enforcement works correctly

### Task 2.5: Evidence Linking
**Input**: Belief nodes
**Action**:
1. Implement `append_evidence()`:
   - Validate source_type enum
   - Validate strength enum
   - Insert evidence_link record
   - Update belief node updated_at
2. Return evidence ID

**Output**: Evidence tracking
**Tests**: Unit test appending evidence
**DoD**: Evidence linked to beliefs

### Task 2.6: Interaction Logging
**Input**: Interactions table
**Action**:
1. Implement `log_interaction()`:
   - Insert interaction record with metadata
   - Extract reddit_id from metadata
   - Store subreddit, parent_id if present
   - Return interaction ID for embedding association

**Output**: Interaction persistence
**Tests**: Unit test logging different interaction types
**DoD**: Interactions stored with metadata

### Task 2.7: FAISS Index Setup
**Input**: sentence-transformers library
**Action**:
1. Create `backend/app/services/embedding.py`
2. Initialize FAISS index (IndexFlatL2, 384 dimensions)
3. Load sentence-transformers model (all-MiniLM-L6-v2)
4. Implement `generate_embedding(text: str) -> np.array`
5. Implement `add_to_index(embedding, interaction_id)`
6. Persist index to `data/faiss_index.bin` on update

**Output**: Embedding service
**Tests**: Unit test embedding generation and indexing
**DoD**: Embeddings generated and stored

### Task 2.8: Semantic History Search
**Input**: FAISS index, embedding service
**Action**:
1. Implement `search_history()`:
   - Generate query embedding
   - Search FAISS index for top k matches
   - Fetch interaction details from DB by IDs
   - Return list of matching interactions
2. Handle empty index gracefully
3. Auto-rebuild index if missing

**Output**: Semantic search capability
**Tests**: Integration test with sample interactions
**DoD**: Returns relevant past interactions

### Task 2.9: Persona Isolation Tests
**Input**: All memory operations
**Action**:
1. Create test with 2 personas
2. Test cases:
   - Persona A can't query Persona B's beliefs
   - Persona A can't update Persona B's stances
   - Persona A can't see Persona B's interactions
3. Verify FK constraints enforce isolation

**Output**: Isolation validation
**Tests**: Self-validating
**DoD**: No data leakage between personas

---

## Day 3: Reddit Client Implementation

### Task 3.1: Reddit Client Interface (IRedditClient)
**Input**: None
**Action**:
1. Create `backend/app/services/interfaces/reddit_client.py`
2. Define abstract class `IRedditClient`:
   ```python
   class IRedditClient(ABC):
       @abstractmethod
       async def get_new_posts(
           subreddits: List[str], limit: int
       ) -> List[Dict]

       @abstractmethod
       async def search_posts(
           query: str, subreddit: str, time_filter: str
       ) -> List[Dict]

       @abstractmethod
       async def submit_post(
           subreddit: str, title: str, content: str
       ) -> str

       @abstractmethod
       async def reply(
           parent_id: str, content: str
       ) -> str
   ```

**Output**: Reddit interface contract
**Tests**: N/A (interface)
**DoD**: Contract defined for Reddit operations

### Task 3.2: Token Bucket Rate Limiter
**Input**: None
**Action**:
1. Create `backend/app/services/rate_limiter.py`
2. Implement `TokenBucket` class:
   - capacity: 60 tokens
   - refill_rate: 60 tokens/minute (1/second)
   - `async acquire()` method (waits if empty)
   - Thread-safe using asyncio.Lock
3. Support burst allowance

**Output**: Rate limiting utility
**Tests**: Unit test token consumption and refill
**DoD**: Enforces 60 req/min limit

### Task 3.3: AsyncPRAW Client Wrapper
**Input**: asyncpraw library, Reddit credentials
**Action**:
1. Create `backend/app/services/reddit_client.py`
2. Implement `AsyncPRAWClient` class
3. Initialize asyncpraw.Reddit with credentials from settings
4. Inject TokenBucket for rate limiting
5. Add connection validation method

**Output**: Basic Reddit client
**Tests**: Mock test for client initialization
**DoD**: Client authenticates successfully

### Task 3.4: Get New Posts Implementation
**Input**: AsyncPRAW client
**Action**:
1. Implement `get_new_posts()`:
   - Iterate over subreddits
   - Fetch subreddit.new(limit=N)
   - Rate limit each request
   - Extract: id, title, selftext, author, score, url, subreddit
   - Return list of post dicts
2. Handle deleted/removed posts gracefully

**Output**: Post fetching
**Tests**: Integration test with test subreddit (mocked)
**DoD**: Returns structured post data

### Task 3.5: Search Posts Implementation
**Input**: AsyncPRAW client
**Action**:
1. Implement `search_posts()`:
   - Use subreddit.search(query, time_filter)
   - Support time filters: hour, day, week, month, year
   - Rate limit
   - Return same structure as get_new_posts
2. Handle empty results

**Output**: Post search
**Tests**: Mock test with search query
**DoD**: Search returns relevant posts

### Task 3.6: Submit Post Implementation
**Input**: AsyncPRAW client
**Action**:
1. Implement `submit_post()`:
   - Submit to subreddit.submit(title, selftext)
   - Rate limit
   - Capture submission ID
   - Return reddit ID (e.g., "t3_...")
2. Handle submission errors (banned, rate limit)

**Output**: Post submission
**Tests**: Mock test (don't actually post)
**DoD**: Submission logic correct

### Task 3.7: Reply Implementation
**Input**: AsyncPRAW client
**Action**:
1. Implement `reply()`:
   - Fetch parent by fullname (e.g., t1_xxx, t3_xxx)
   - Call parent.reply(content)
   - Rate limit
   - Return comment ID
2. Handle reply errors (deleted parent, locked thread)

**Output**: Comment reply
**Tests**: Mock test for reply logic
**DoD**: Reply mechanism works

### Task 3.8: Retry Logic with Exponential Backoff
**Input**: Reddit client methods
**Action**:
1. Create decorator `@retry_with_backoff(max_retries=3)`
2. Apply to all Reddit API calls
3. Retry on:
   - 429 (rate limit exceeded)
   - 5xx server errors
   - Network timeouts
4. Use exponential backoff: 1s, 2s, 4s
5. Add jitter (±20%)

**Output**: Resilient API calls
**Tests**: Mock test simulating failures
**DoD**: Retries work as expected

---

## Day 4: LLM Client & Cost Tracking

### Task 4.1: LLM Client Interface (ILLMClient)
**Input**: None (already defined in architecture doc)
**Action**:
1. Review interface from architecture
2. Update if needed for clarity:
   ```python
   class ILLMClient(ABC):
       @abstractmethod
       async def generate_response(
           system_prompt: str, context: Dict,
           user_message: str, tools: List[Dict] = None
       ) -> Dict

       @abstractmethod
       async def check_consistency(
           draft_response: str, beliefs: List[Dict]
       ) -> Dict
   ```

**Output**: LLM interface
**Tests**: N/A
**DoD**: Contract matches implementation needs

### Task 4.2: OpenRouter Client Setup
**Input**: OpenAI SDK, OpenRouter credentials
**Action**:
1. Create `backend/app/services/llm_client.py`
2. Implement `OpenRouterClient` class
3. Initialize AsyncOpenAI client:
   - api_key from settings
   - base_url: https://openrouter.ai/api/v1
4. Load model names from settings (primary & secondary)

**Output**: LLM client foundation
**Tests**: Connectivity test (mock or real)
**DoD**: Client configured correctly

### Task 4.3: Prompt Assembly for Response Generation
**Input**: OpenRouter client
**Action**:
1. Implement `generate_response()`:
   - Build messages array:
     ```json
     [
       {"role": "system", "content": system_prompt},
       {"role": "user", "content": "Context: {...}\n\nMessage: ..."}
     ]
     ```
   - Use primary model (gpt-5.1-mini)
   - Set temperature: 0.7, max_tokens: 500
2. Extract response text from completion

**Output**: Response generation
**Tests**: Unit test with mock completion
**DoD**: Generates coherent responses

### Task 4.4: Token Usage Tracking
**Input**: OpenRouter responses
**Action**:
1. Extract usage from response:
   - prompt_tokens, completion_tokens, total_tokens
2. Calculate cost based on model pricing:
   ```python
   pricing = {
       "openai/gpt-5.1-mini": {"input": 0.15/1M, "output": 0.60/1M},
       "anthropic/claude-4.5-haiku": {"input": 0.25/1M, "output": 1.25/1M}
   }
   ```
3. Return cost in response dict

**Output**: Cost calculation
**Tests**: Unit test cost math
**DoD**: Accurate cost per request

### Task 4.5: Consistency Check Implementation
**Input**: OpenRouter client, secondary model
**Action**:
1. Implement `check_consistency()`:
   - Format belief summary from list
   - Build prompt asking for conflict analysis
   - Use secondary model (claude-4.5-haiku)
   - Request JSON response:
     ```json
     {
       "is_consistent": bool,
       "conflicts": ["belief_id1", ...],
       "explanation": "..."
     }
     ```
   - Temperature: 0.3 (more deterministic)
2. Parse and return result

**Output**: Consistency checking
**Tests**: Unit test with mock conflicts
**DoD**: Detects belief conflicts

### Task 4.6: Request/Response Logging with Cost
**Input**: LLM client methods
**Action**:
1. Add logging to each LLM call:
   - Log prompt (truncated if >500 chars)
   - Log response
   - Log tokens and cost
   - Include request_id from context
2. Use structured logger

**Output**: LLM observability
**Tests**: Log capture test
**DoD**: All LLM calls logged with cost

### Task 4.7: Error Handling & Retries
**Input**: LLM client
**Action**:
1. Wrap calls in try/except for:
   - AuthenticationError → raise with clear message
   - RateLimitError → retry with backoff
   - APIError → retry once, then fail
   - TimeoutError → retry once
2. Use same retry decorator as Reddit client
3. Log all errors

**Output**: Robust LLM client
**Tests**: Mock error scenarios
**DoD**: Handles failures gracefully

---

## Day 5: Moderation Scaffold & Integration

### Task 5.1: Moderation Service Interface
**Input**: None
**Action**:
1. Create `backend/app/services/interfaces/moderation.py`
2. Define `IModerationService`:
   ```python
   class IModerationService(ABC):
       @abstractmethod
       async def evaluate_content(
           persona_id: str, content: str, context: Dict
       ) -> Dict[str, Any]

       @abstractmethod
       async def enqueue_for_review(
           persona_id: str, content: str, metadata: Dict
       ) -> str

       @abstractmethod
       async def is_auto_posting_enabled(
           persona_id: str
       ) -> bool
   ```

**Output**: Moderation interface
**Tests**: N/A
**DoD**: Contract defined

### Task 5.2: Content Evaluation Rules
**Input**: None
**Action**:
1. Create `backend/app/services/moderation.py`
2. Implement `ModerationService` class
3. Add `evaluate_content()` with basic rules:
   - Check for banned keywords (hardcoded list)
   - Check length limits (min 10, max 10000 chars)
   - Placeholder for LLM-based toxicity check
4. Return dict:
   ```python
   {
     "approved": bool,
     "flagged": bool,
     "flags": ["reason1", "reason2"],
     "action": "allow" | "review" | "block"
   }
   ```

**Output**: Content evaluation
**Tests**: Unit tests for various content types
**DoD**: Rules enforced correctly

### Task 5.3: Auto-Posting Flag Check
**Input**: ConfigRepository
**Action**:
1. Implement `is_auto_posting_enabled()`:
   - Query agent_config for "auto_posting_enabled"
   - Return boolean (default: False if not set)
2. Inject ConfigRepository as dependency

**Output**: Auto-posting check
**Tests**: Unit test with different configs
**DoD**: Correctly reads persona config

### Task 5.4: Moderation Queue Enqueue
**Input**: pending_posts table
**Action**:
1. Implement `enqueue_for_review()`:
   - Insert record to pending_posts
   - Set status: "pending"
   - Store content and metadata (draft context)
   - Return queue item ID
2. Ensure persona_id isolation

**Output**: Queue management
**Tests**: Unit test enqueueing
**DoD**: Posts added to queue

### Task 5.5: Moderation API - List Pending
**Input**: ModerationService
**Action**:
1. Create `backend/app/api/v1/moderation.py`
2. Add `GET /api/v1/moderation/pending?persona_id={id}`
3. Return list of pending posts:
   ```json
   {
     "items": [
       {
         "id": "...",
         "content": "...",
         "target_subreddit": "...",
         "created_at": "...",
         "metadata": {...}
       }
     ]
   }
   ```
4. Require authentication

**Output**: Pending queue endpoint
**Tests**: Integration test
**DoD**: Returns queued items

### Task 5.6: Moderation API - Approve
**Input**: ModerationService, RedditClient
**Action**:
1. Add `POST /api/v1/moderation/approve`
2. Accept: item_id, persona_id
3. Fetch pending post from DB
4. Call RedditClient to post/reply
5. Update status to "approved", set reviewed_by, reviewed_at
6. Return reddit_id

**Output**: Approval workflow
**Tests**: Integration test (mock Reddit call)
**DoD**: Posts when approved

### Task 5.7: Moderation API - Reject
**Input**: ModerationService
**Action**:
1. Add `POST /api/v1/moderation/reject`
2. Accept: item_id, persona_id, reason (optional)
3. Update status to "rejected"
4. Store rejection reason in metadata
5. Return success

**Output**: Rejection workflow
**Tests**: Integration test
**DoD**: Marks item as rejected

### Task 5.8: Moderation API - Flag Override
**Input**: ModerationService
**Action**:
1. Add `POST /api/v1/moderation/override-flag`
2. Accept: item_id, flag_name
3. Update draft_metadata to mark flag as overridden
4. Allow admin to approve despite flag
5. Log override action

**Output**: Override capability
**Tests**: Integration test
**DoD**: Overrides work correctly

### Task 5.9: Auto/Manual Mode Decision Logic
**Input**: ModerationService, all components
**Action**:
1. Create unified decision function:
   ```python
   async def should_post_immediately(
       persona_id: str,
       evaluation: Dict
   ) -> bool:
       auto_enabled = await is_auto_posting_enabled(persona_id)
       if not auto_enabled:
           return False
       if evaluation["flagged"]:
           return False
       return evaluation["approved"]
   ```
2. Use in posting flow

**Output**: Posting decision logic
**Tests**: Unit test all combinations
**DoD**: Respects auto flag and evaluations

---

## Integration & Testing (Throughout Week)

### Task INT.1: Service Integration Tests
**Input**: All services
**Action**:
1. Create `backend/tests/integration/test_services.py`
2. Test memory store with real SQLite DB
3. Test Reddit client with mocked asyncpraw
4. Test LLM client with mocked OpenRouter
5. Test moderation service end-to-end

**Output**: Service integration suite
**Tests**: Self-validating
**DoD**: All services work together

### Task INT.2: Persona Isolation End-to-End
**Input**: All services
**Action**:
1. Create 2 personas in test DB
2. Perform operations for each:
   - Create beliefs
   - Log interactions
   - Enqueue posts
   - Update config
3. Verify no cross-contamination

**Output**: E2E isolation test
**Tests**: Self-validating
**DoD**: Isolation guaranteed

### Task INT.3: FAISS Persistence Test
**Input**: Memory store, embedding service
**Action**:
1. Add interactions with embeddings
2. Save FAISS index to file
3. Restart service (reload index)
4. Verify search still works
5. Test index rebuild on missing file

**Output**: Persistence validation
**Tests**: Integration test
**DoD**: Index survives restart

### Task INT.4: Cost Tracking Validation
**Input**: LLM client, logging
**Action**:
1. Make several LLM calls
2. Parse logs and sum costs
3. Verify calculations match expected
4. Test with different models
5. Document typical daily cost

**Output**: Cost accuracy verification
**Tests**: Manual + automated
**DoD**: Cost tracking accurate

### Task INT.5: OpenAPI Schema Update
**Input**: All new endpoints
**Action**:
1. Generate updated OpenAPI spec
2. Add endpoint descriptions
3. Document moderation workflow
4. Export to `docs/api/openapi.yaml`
5. Validate schema

**Output**: Updated API docs
**Tests**: Schema validation
**DoD**: Spec matches implementation

### Task INT.6: Week 3 Runbook
**Input**: All implementations
**Action**:
1. Create `docs/runbooks/week3_services.md`
2. Document:
   - How to seed beliefs
   - How to rebuild FAISS index
   - How to test Reddit client (without posting)
   - How to monitor LLM costs
   - Troubleshooting guide
3. Include example queries

**Output**: Operations guide
**Tests**: Follow manual steps
**DoD**: Runbook complete

---

## Definition of Done (Week 3)

**Database**:
- ✅ All tables created (personas, belief_nodes, belief_edges, stance_versions, evidence_links, interactions, belief_updates, pending_posts, agent_config)
- ✅ Migrations tested (apply/rollback)
- ✅ WAL mode enabled on SQLite
- ✅ Default persona seeded with initial beliefs

**Memory Store**:
- ✅ IMemoryStore interface implemented
- ✅ Belief graph queries work (nodes + edges)
- ✅ Stance versioning with lock enforcement
- ✅ Evidence linking functional
- ✅ Interaction logging persistent
- ✅ FAISS semantic search operational
- ✅ Index persists to disk and reloads

**Reddit Client**:
- ✅ IRedditClient interface implemented
- ✅ Rate limiting enforced (60 req/min)
- ✅ Retry logic with exponential backoff
- ✅ Can fetch posts and search
- ✅ Can submit posts and replies (mocked)

**LLM Client**:
- ✅ OpenRouter client configured
- ✅ Response generation works
- ✅ Consistency checking functional
- ✅ Token usage tracked
- ✅ Cost calculated per request
- ✅ All calls logged with cost

**Moderation**:
- ✅ IModerationService interface implemented
- ✅ Content evaluation rules enforced
- ✅ Queue management working
- ✅ Auto/manual mode decision logic
- ✅ API endpoints for pending/approve/reject/override
- ✅ Respects persona config

**Quality**:
- ✅ All services have contract tests
- ✅ Integration tests pass
- ✅ Persona isolation verified end-to-end
- ✅ >80% coverage on new code
- ✅ OpenAPI spec updated
- ✅ Week 3 runbook complete

**Next Steps**:
Ready for Week 4 (Agent Loop, Belief Updates, Dashboard)
