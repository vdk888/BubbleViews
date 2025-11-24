# Week 4 Plan — Agent Logic, Belief Updates, Dashboard Slice

**Scope**: Wire perception → retrieval → decision → moderation → action loop; implement Bayesian belief updater; deliver first dashboard slice (activity/moderation/belief snapshot); add governor chat stub if time permits. Aligns with technical spec, brainstorming UX, and 0_dev quality.

**Estimated effort**: 7 days, 48 micro-tasks

---

## Day 1: Retrieval Pipeline & Context Assembly

### Task 1.1: Retrieval Coordinator Service
**Input**: Memory store, embedding service
**Action**:
1. Create `backend/app/services/retrieval.py`
2. Implement `RetrievalCoordinator` class with dependencies:
   - IMemoryStore
   - EmbeddingService
3. Define method signatures:
   - `async def assemble_context(persona_id, thread_context) -> Dict`

**Output**: Retrieval service skeleton
**Tests**: Dependency injection test
**DoD**: Service initializes with dependencies

### Task 1.2: Belief Graph Retrieval for Context
**Input**: Memory store
**Action**:
1. Implement method to fetch relevant beliefs:
   - Query belief_nodes with tag filtering if thread has topic hints
   - Fetch current stances for each node
   - Fetch related edges (supports/contradicts/depends)
2. Format as context dict:
   ```python
   {
     "beliefs": [
       {"id": "...", "title": "...", "stance": "...", "confidence": 0.8}
     ],
     "relations": [
       {"source": "...", "target": "...", "type": "supports"}
     ]
   }
   ```

**Output**: Belief context retrieval
**Tests**: Unit test with seeded beliefs
**DoD**: Returns structured belief context

### Task 1.3: Past Self-Comments Retrieval
**Input**: FAISS index, interaction history
**Action**:
1. Implement semantic search for past comments:
   - Generate embedding for current thread (title + OP)
   - Search FAISS index with k=5
   - Fetch interaction details from DB
   - Filter by persona_id
2. Return list of relevant past statements:
   ```python
   [
     {"content": "...", "subreddit": "...", "created_at": "...", "reddit_id": "..."}
   ]
   ```

**Output**: Self-history retrieval
**Tests**: Integration test with sample interactions
**DoD**: Returns semantically similar past comments

### Task 1.4: Evidence Snippet Retrieval
**Input**: Belief graph, evidence_links
**Action**:
1. For each belief in context, fetch top 2 evidence links
2. Include source_type and source_ref
3. Format as part of belief context

**Output**: Evidence inclusion
**Tests**: Unit test evidence fetching
**DoD**: Evidence attached to beliefs

### Task 1.5: Prompt Assembly Logic
**Input**: Retrieved context components
**Action**:
1. Implement `assemble_prompt()` method:
   - Build sections:
     - Persona description (from config)
     - Current beliefs with confidence levels
     - Past relevant statements
     - Thread context (title, OP, parent comment if reply)
   - Enforce token budget (max ~3000 tokens for context)
   - Prioritize: persona > high-confidence beliefs > recent past statements
2. Return structured prompt dict

**Output**: Prompt composer
**Tests**: Unit test with various inputs, token counting
**DoD**: Generates well-formed prompts within budget

### Task 1.6: Context Assembly Integration Test
**Input**: All retrieval components
**Action**:
1. Create integration test with:
   - Seeded persona with beliefs
   - Logged past interactions
   - Sample thread context
2. Call `assemble_context()`
3. Verify output contains:
   - Relevant beliefs
   - Past statements
   - Evidence
   - Properly formatted

**Output**: E2E retrieval test
**Tests**: Self-validating
**DoD**: Full context assembly works

---

## Day 2: Agent Decision Loop Core

### Task 2.1: Agent Loop Service Structure
**Input**: All services (retrieval, LLM, Reddit, moderation, memory)
**Action**:
1. Create `backend/app/agent/loop.py`
2. Implement `AgentLoop` class with injected dependencies
3. Define main loop method signature:
   ```python
   async def run(persona_id: str, stop_event: asyncio.Event)
   ```
4. Set up graceful shutdown handling

**Output**: Agent loop skeleton
**Tests**: Initialization test
**DoD**: Service structure in place

### Task 2.2: Perception Phase - Post Monitoring
**Input**: Reddit client, config
**Action**:
1. Implement `async def perceive(persona_id) -> List[Dict]`:
   - Load target_subreddits from config
   - Call reddit_client.get_new_posts(subreddits, limit=10)
   - Filter already-seen posts (check against interactions table)
   - Return list of new posts

**Output**: Perception implementation
**Tests**: Mock Reddit client, verify filtering
**DoD**: Returns unseen posts

### Task 2.3: Decision Phase - Should Respond Logic
**Input**: Post context, persona config
**Action**:
1. Implement `async def should_respond(post) -> bool`:
   - Check if post matches interest keywords (optional config)
   - Check if not own post (username match)
   - Random sampling if too many posts (configurable rate)
   - Return decision
2. Log skipped posts with reason

**Output**: Response decision
**Tests**: Unit test various scenarios
**DoD**: Correctly filters posts

### Task 2.4: Draft Generation via LLM
**Input**: Assembled context, LLM client
**Action**:
1. Implement `async def generate_draft(context) -> str`:
   - Build system prompt from persona
   - Call llm_client.generate_response()
   - Extract draft text
   - Log tokens and cost
2. Include correlation ID in logs

**Output**: Draft generation
**Tests**: Mock LLM client
**DoD**: Generates draft responses

### Task 2.5: Consistency Check Integration
**Input**: Draft, beliefs, LLM client
**Action**:
1. Implement `async def check_draft_consistency(draft, beliefs) -> Dict`:
   - Call llm_client.check_consistency()
   - Parse result (is_consistent, conflicts, explanation)
   - If conflicts found, log warning
   - Return result for belief update consideration

**Output**: Consistency validation
**Tests**: Mock consistency check
**DoD**: Detects conflicts correctly

### Task 2.6: Moderation Decision
**Input**: Draft, moderation service
**Action**:
1. Implement `async def moderate_draft(draft, persona_id) -> Dict`:
   - Call moderation_service.evaluate_content()
   - Check auto_posting_enabled flag
   - Decide action: "post_now" | "queue" | "drop"
   - Return decision dict

**Output**: Moderation integration
**Tests**: Unit test all moderation paths
**DoD**: Correct moderation decisions

### Task 2.7: Action Phase - Post or Enqueue
**Input**: Draft, moderation decision, Reddit client, memory
**Action**:
1. Implement `async def execute_action(draft, decision) -> str`:
   - If "post_now": call reddit_client.reply() → log_interaction()
   - If "queue": call moderation_service.enqueue_for_review()
   - If "drop": log reason, skip
   - Return reddit_id or queue_id
2. Handle errors (Reddit API failures)

**Output**: Action execution
**Tests**: Mock Reddit and moderation
**DoD**: Posts or queues correctly

### Task 2.8: Main Loop Integration
**Input**: All phase implementations
**Action**:
1. Wire all phases in `run()` method:
   ```python
   while not stop_event.is_set():
       posts = await perceive(persona_id)
       for post in posts:
           if await should_respond(post):
               context = await retrieval.assemble_context(persona_id, post)
               draft = await generate_draft(context)
               consistency = await check_draft_consistency(draft, context['beliefs'])
               decision = await moderate_draft(draft, persona_id)
               result = await execute_action(draft, decision)
       await asyncio.sleep(poll_interval)
   ```
2. Add error handling and logging per phase
3. Include backoff on repeated errors

**Output**: Complete agent loop
**Tests**: Integration test with mocked dependencies
**DoD**: Loop runs end-to-end

---

## Day 3: Bayesian Belief Updater

### Task 3.1: Belief Updater Service Structure
**Input**: Memory store
**Action**:
1. Create `backend/app/services/belief_updater.py`
2. Implement `BeliefUpdater` class
3. Define methods:
   - `async def update_from_evidence(persona_id, belief_id, evidence_strength, reason) -> float`
   - `async def update_from_conflict(persona_id, belief_id, conflict_info) -> bool`

**Output**: Updater service skeleton
**Tests**: Initialization test
**DoD**: Service structure ready

### Task 3.2: Evidence Strength Mapping
**Input**: None
**Action**:
1. Define evidence strength enum and confidence deltas:
   ```python
   EVIDENCE_DELTA = {
       "weak": 0.05,
       "moderate": 0.10,
       "strong": 0.20
   }
   ```
2. Implement `calculate_new_confidence(current, delta, direction) -> float`:
   - direction: "increase" | "decrease"
   - Clamp result to [0, 1]
   - Use logistic-like update for smooth transitions

**Output**: Confidence calculation
**Tests**: Unit test various scenarios
**DoD**: Deterministic confidence updates

### Task 3.3: Locked Stance Check
**Input**: Memory store
**Action**:
1. Implement check in `update_from_evidence()`:
   - Query current stance for belief
   - Check status field
   - If "locked", raise error or return without update
   - Log locked update attempt

**Output**: Lock enforcement
**Tests**: Unit test locked stance rejection
**DoD**: Locked stances cannot be updated

### Task 3.4: Stance Version Creation
**Input**: Memory store, updated confidence
**Action**:
1. Implement stance update logic:
   - Mark current stance as "deprecated"
   - Create new stance_version:
     - belief_id, text (can copy from current or modify), new confidence
     - status: "current", rationale
   - Update belief_node.current_confidence
2. Ensure atomic transaction

**Output**: Versioning logic
**Tests**: Unit test version history
**DoD**: Stance versions tracked correctly

### Task 3.5: Audit Log Writing
**Input**: Belief update details
**Action**:
1. Implement audit logging to belief_updates table:
   - Store old_value and new_value as JSON (confidence + text)
   - Include reason, trigger_type (evidence | conflict | manual)
   - Store updated_by (system or admin username)
   - Timestamp automatically

**Output**: Audit trail
**Tests**: Unit test audit log creation
**DoD**: All updates logged

### Task 3.6: Conflict-Based Update Logic
**Input**: Consistency check results
**Action**:
1. Implement `update_from_conflict()`:
   - If draft conflicts with high-confidence belief (>0.8):
     - If evidence is strong, propose update (admin approval)
     - If evidence is weak, revise draft instead
   - If belief confidence is moderate, allow automatic adjustment
   - Return whether update was applied

**Output**: Conflict resolution
**Tests**: Unit test conflict scenarios
**DoD**: Handles conflicts per policy

### Task 3.7: Bayesian Update Algorithm
**Input**: Current confidence, evidence list
**Action**:
1. Implement more sophisticated Bayesian update (optional enhancement):
   - Track prior P(belief)
   - For new evidence E, calculate likelihood ratio
   - Update posterior using Bayes' rule approximation
2. Document formula in code comments
3. Keep simple delta approach as fallback

**Output**: Bayesian updater
**Tests**: Unit test with evidence scenarios
**DoD**: Confidence updates follow Bayesian principles

### Task 3.8: Integration Test - Full Belief Update Flow
**Input**: All updater components
**Action**:
1. Seed belief with initial confidence 0.6
2. Apply evidence updates:
   - Weak counter-evidence → 0.55
   - Strong supporting evidence → 0.75
   - Try locked update → rejected
3. Verify stance versions and audit log
4. Check belief_node.current_confidence matches

**Output**: E2E belief update test
**Tests**: Self-validating
**DoD**: Full flow works correctly

---

## Day 4: Dashboard Backend APIs

### Task 4.1: Activity Feed API
**Input**: Interactions table
**Action**:
1. Create `backend/app/api/v1/activity.py`
2. Implement `GET /api/v1/activity?persona_id={id}&since={ts}&limit={N}`:
   - Query interactions table
   - Filter by persona_id and created_at > since
   - Order by created_at DESC
   - Include: content snippet, interaction_type, subreddit, reddit_id, karma (if available)
3. Support pagination (offset/limit)

**Output**: Activity endpoint
**Tests**: Integration test with seeded data
**DoD**: Returns activity feed

### Task 4.2: Stats Summary API
**Input**: Interactions, pending_posts
**Action**:
1. Add `GET /api/v1/stats?persona_id={id}`:
   - Count total interactions (lifetime)
   - Count interactions last 7 days
   - Sum karma (if tracked in metadata)
   - Count pending posts
   - Count subreddits engaged
2. Return JSON:
   ```json
   {
     "total_interactions": 42,
     "last_7_days": 5,
     "total_karma": 120,
     "pending_count": 2,
     "subreddits_engaged": 3
   }
   ```

**Output**: Stats endpoint
**Tests**: Integration test
**DoD**: Accurate statistics

### Task 4.3: Belief Graph Data API
**Input**: Memory store
**Action**:
1. Add `GET /api/v1/belief-graph?persona_id={id}`:
   - Call memory_store.query_belief_graph()
   - Return nodes and edges in JSON format suitable for visualization:
     ```json
     {
       "nodes": [
         {"id": "...", "title": "...", "confidence": 0.8, "tags": [...]}
       ],
       "edges": [
         {"source": "...", "target": "...", "relation": "supports", "weight": 0.5}
       ]
     }
     ```

**Output**: Belief graph endpoint
**Tests**: Integration test
**DoD**: Returns graph data

### Task 4.4: Stance History API
**Input**: stance_versions, evidence_links
**Action**:
1. Add `GET /api/v1/beliefs/{belief_id}/history?persona_id={id}`:
   - Query stance_versions for belief_id ordered by created_at DESC
   - Include evidence_links per stance
   - Return timeline:
     ```json
     {
       "versions": [
         {
           "text": "...",
           "confidence": 0.8,
           "status": "current",
           "created_at": "...",
           "rationale": "...",
           "evidence": [...]
         }
       ]
     }
     ```

**Output**: History endpoint
**Tests**: Integration test with version history
**DoD**: Shows stance evolution

### Task 4.5: Belief Update API (Manual Override)
**Input**: BeliefUpdater
**Action**:
1. Add `PUT /api/v1/beliefs/{belief_id}`:
   - Accept: persona_id, confidence (new), text (optional), rationale
   - Require authentication
   - Call belief_updater with trigger_type="manual"
   - Log admin username in audit
   - Return updated belief

**Output**: Manual belief update
**Tests**: Integration test
**DoD**: Admin can update beliefs

### Task 4.6: Belief Lock/Unlock API
**Input**: Memory store
**Action**:
1. Add `POST /api/v1/beliefs/{belief_id}/lock`:
   - Set current stance status to "locked"
   - Log action
2. Add `POST /api/v1/beliefs/{belief_id}/unlock`:
   - Set stance status back to "current"
   - Log action

**Output**: Lock management
**Tests**: Integration test lock/unlock flow
**DoD**: Locking mechanism accessible

### Task 4.7: Nudge API (Soft Adjustment)
**Input**: BeliefUpdater
**Action**:
1. Add `POST /api/v1/beliefs/{belief_id}/nudge`:
   - Accept: direction ("more_confident" | "less_confident"), amount (0.1 default)
   - Apply confidence delta
   - Record as manual trigger with "nudge" in rationale
   - Return updated belief

**Output**: Nudge functionality
**Tests**: Integration test
**DoD**: Nudging works

### Task 4.8: Personas List API (Multi-Persona Support)
**Input**: Personas table
**Action**:
1. Add `GET /api/v1/personas`:
   - Return list of all personas:
     ```json
     {
       "personas": [
         {
           "id": "...",
           "reddit_username": "...",
           "display_name": "...",
           "created_at": "..."
         }
       ]
     }
     ```
2. Require authentication

**Output**: Persona listing
**Tests**: Integration test
**DoD**: Lists all personas

### Task 4.9: OpenAPI Update for Dashboard APIs
**Input**: All new endpoints
**Action**:
1. Generate updated OpenAPI spec
2. Document request/response schemas
3. Add descriptions for dashboard workflows
4. Export to `docs/api/openapi.yaml`
5. Validate

**Output**: API documentation update
**Tests**: Schema validation
**DoD**: All endpoints documented

---

## Day 5: Dashboard Frontend (Next.js)

### Task 5.1: Next.js Project Setup
**Input**: None
**Action**:
1. Initialize Next.js 14 app in `frontend/`:
   ```bash
   npx create-next-app@latest frontend --typescript --tailwind --app
   ```
2. Configure paths, linting, prettier
3. Install dependencies:
   - axios or fetch for API calls
   - recharts or similar for graphs
   - react-force-graph for belief graph visualization
4. Create basic layout with navigation

**Output**: Frontend skeleton
**Tests**: Build succeeds
**DoD**: App runs on localhost:3000

### Task 5.2: API Client Generation
**Input**: OpenAPI spec
**Action**:
1. Use openapi-typescript-codegen or similar to generate TypeScript client from OpenAPI
2. Configure base URL (env variable: NEXT_PUBLIC_API_URL)
3. Add authentication token handling (localStorage or cookies)
4. Create `lib/api-client.ts` with typed methods

**Output**: Type-safe API client
**Tests**: Build type-checks
**DoD**: API client available for use

### Task 5.3: Activity Feed Page
**Input**: Activity API, API client
**Action**:
1. Create `app/activity/page.tsx`
2. Fetch activity data on load
3. Display list of interactions:
   - Date/time
   - Subreddit
   - Content snippet (truncate)
   - Link to Reddit (open in new tab)
   - Karma (if available)
4. Add pagination controls
5. Style with Tailwind

**Output**: Activity feed UI
**Tests**: Manual browser test, lint/build check
**DoD**: Activity displayed correctly

### Task 5.4: Stats Dashboard Widget
**Input**: Stats API
**Action**:
1. Create `components/StatsSummary.tsx`
2. Fetch stats for selected persona
3. Display cards:
   - Total interactions
   - Last 7 days activity
   - Karma
   - Pending posts count
4. Add to homepage or activity page

**Output**: Stats widget
**Tests**: Manual test
**DoD**: Stats visible

### Task 5.5: Moderation Queue Page
**Input**: Moderation API, API client
**Action**:
1. Create `app/moderation/page.tsx`
2. Fetch pending posts
3. Display queue items with:
   - Content preview
   - Target subreddit
   - Timestamp
   - Approve/Reject buttons
4. Implement approve action (call API, refresh list)
5. Implement reject action (optionally with reason input)

**Output**: Moderation queue UI
**Tests**: Manual test approve/reject
**DoD**: Queue management works

### Task 5.6: Auto/Manual Toggle Control
**Input**: Settings API
**Action**:
1. Add toggle switch on moderation page or settings
2. Fetch auto_posting_enabled setting
3. On toggle, call settings API to update
4. Show current state clearly
5. Confirm before enabling auto-posting

**Output**: Auto-post control
**Tests**: Manual test toggle
**DoD**: Setting updates correctly

### Task 5.7: Belief Graph Visualization
**Input**: Belief graph API, react-force-graph
**Action**:
1. Create `app/beliefs/page.tsx`
2. Fetch belief graph data
3. Render force-directed graph:
   - Nodes: beliefs (color by confidence, size by centrality)
   - Edges: relations (color by type: supports, contradicts, depends_on)
4. Add click handler to show belief details (modal or sidebar)
5. Support zoom/pan

**Output**: Belief graph view
**Tests**: Manual test, verify interactivity
**DoD**: Graph renders and is interactive

### Task 5.8: Belief Detail Modal/Panel
**Input**: Belief history API
**Action**:
1. Create `components/BeliefDetail.tsx`
2. Display for selected belief:
   - Title, current stance, confidence
   - Tags
   - Timeline of stance versions (list with dates)
   - Evidence links
   - Lock/Unlock button (if admin)
   - Manual update form (confidence slider, text area)
3. Implement update submission

**Output**: Belief detail view
**Tests**: Manual test
**DoD**: Can view and edit beliefs

### Task 5.9: Persona Selector
**Input**: Personas API
**Action**:
1. Create `components/PersonaSelector.tsx`
2. Fetch personas list
3. Display dropdown to select active persona
4. Store selection in React state or context
5. Pass selected persona_id to all API calls
6. Persist selection in localStorage

**Output**: Persona switcher
**Tests**: Manual test multi-persona
**DoD**: Can switch between personas

### Task 5.10: Frontend Build & Deployment Config
**Input**: Next.js app
**Action**:
1. Configure production build:
   - Environment variables for API URL
   - Output: static export or server build
2. Create `.env.example` for frontend
3. Document deployment to Vercel:
   - Connect GitHub repo
   - Set env vars in Vercel dashboard
   - Deploy
4. Add instructions to README

**Output**: Deployment config
**Tests**: Production build succeeds
**DoD**: Deployable to Vercel

---

## Day 6: Optional Features & Polish

### Task 6.1: SSE/WebSocket Live Updates (Optional)
**Input**: Backend event system
**Action**:
1. Add SSE endpoint `GET /api/v1/stream?persona_id={id}`:
   - Stream events: new_interaction, new_pending_post, belief_updated
   - Use FastAPI StreamingResponse
2. In frontend, use EventSource to listen
3. Update UI in real-time (activity feed, pending count)

**Output**: Live updates
**Tests**: Manual test event streaming
**DoD**: Dashboard updates without refresh

### Task 6.2: Governor Chat Stub (Optional)
**Input**: LLM client, memory store
**Action**:
1. Add `POST /api/v1/governor/query`:
   - Accept: persona_id, question
   - Use LLM to answer based on persona's beliefs/history
   - Do NOT post to Reddit, read-only
   - Return explanation text
2. Create frontend page `app/governor/page.tsx`:
   - Text input for questions
   - Display answers

**Output**: Governor chat interface
**Tests**: Manual test queries
**DoD**: Can query agent's reasoning

### Task 6.3: Cost Monitoring Dashboard
**Input**: LLM logs, cost tracking
**Action**:
1. Aggregate costs from logs (sum by day/week)
2. Add `GET /api/v1/stats/costs?persona_id={id}&period={7d}`:
   - Return total cost, cost per model
3. Display on frontend stats page:
   - Chart of daily costs
   - Model breakdown

**Output**: Cost visibility
**Tests**: Manual verification
**DoD**: Costs tracked and displayed

### Task 6.4: Error Toast Notifications
**Input**: API errors
**Action**:
1. Add toast library (react-hot-toast or similar)
2. Show error messages on API failures
3. Show success messages on actions (approve, update)

**Output**: User feedback
**Tests**: Manual test error handling
**DoD**: User sees error/success feedback

### Task 6.5: Loading States & Skeletons
**Input**: All frontend pages
**Action**:
1. Add loading skeletons for:
   - Activity feed (while fetching)
   - Belief graph (while loading)
   - Moderation queue
2. Use Tailwind for skeleton styles

**Output**: Better UX
**Tests**: Manual test loading states
**DoD**: Loading indicators present

### Task 6.6: Dark Mode Support (Optional)
**Input**: Tailwind dark mode
**Action**:
1. Enable dark mode in Tailwind config
2. Add theme toggle button in header
3. Persist preference in localStorage
4. Apply dark: variants to components

**Output**: Dark mode
**Tests**: Manual test theme switching
**DoD**: Dark mode works

---

## Day 7: Integration Testing & Documentation

### Task 7.1: End-to-End Integration Test
**Input**: Full system (backend + frontend)
**Action**:
1. Start backend locally
2. Seed default persona with beliefs
3. Run agent loop for 1 minute (dry run, no real posts)
4. Verify:
   - Perceives posts
   - Generates drafts
   - Queues for moderation (if manual mode)
   - Logs interactions (if auto mode and mocked post)
5. Open dashboard, verify data appears

**Output**: E2E validation
**Tests**: Manual full-stack test
**DoD**: Complete flow works

### Task 7.2: Agent Loop Startup Script
**Input**: Agent loop service
**Action**:
1. Create `backend/scripts/run_agent.py`:
   - Load persona from config
   - Initialize agent loop
   - Handle Ctrl+C gracefully (stop_event)
   - Log startup/shutdown
2. Document usage in README

**Output**: Agent runner script
**Tests**: Manual start/stop
**DoD**: Agent can run standalone

### Task 7.3: Health Check for Agent Loop
**Input**: Agent loop, health API
**Action**:
1. Update `GET /health/agent` endpoint:
   - Check if loop is running
   - Return last_activity timestamp
   - Return status: "running" | "stopped" | "error"
2. Agent loop updates shared state (in-memory flag)

**Output**: Agent status monitoring
**Tests**: Integration test
**DoD**: Health check reflects agent state

### Task 7.4: Week 4 Runbook
**Input**: All implementations
**Action**:
1. Create `docs/runbooks/week4_agent_loop.md`
2. Document:
   - How to start agent loop
   - How to stop gracefully
   - How to switch between auto/manual mode
   - How to review pending posts in dashboard
   - How to manually update beliefs
   - Troubleshooting common issues
3. Include example workflows

**Output**: Operations guide
**Tests**: Follow runbook manually
**DoD**: Runbook complete

### Task 7.5: Architecture Diagram Update
**Input**: Final architecture
**Action**:
1. Update `docs/architecture/system-diagram.md`
2. Add Mermaid diagram showing:
   - Agent loop phases
   - Data flow (Reddit → Perception → Retrieval → Decision → Moderation → Action)
   - Dashboard communication (API calls)
   - Belief update flow
3. Document each component

**Output**: Updated architecture docs
**Tests**: N/A (docs)
**DoD**: Diagram reflects implementation

### Task 7.6: API Documentation Polish
**Input**: OpenAPI spec
**Action**:
1. Review all endpoints for completeness
2. Add example requests/responses
3. Document error codes and handling
4. Add authentication requirements clearly
5. Export to `docs/api/openapi.yaml`
6. Generate Swagger UI (optional)

**Output**: Polished API docs
**Tests**: Validate with tools
**DoD**: Docs are comprehensive

### Task 7.7: README Update
**Input**: All project components
**Action**:
1. Update main README with:
   - Project overview and goals
   - Architecture summary
   - Setup instructions (backend + frontend)
   - How to run agent
   - How to access dashboard
   - Cost estimates
   - Links to detailed docs
2. Add badges (build status, coverage if available)

**Output**: Complete README
**Tests**: Follow setup instructions fresh
**DoD**: New user can onboard

### Task 7.8: Demo Persona Seeding
**Input**: Seeding scripts
**Action**:
1. Create `backend/scripts/seed_demo.py`:
   - Create demo persona with interesting beliefs
   - Seed 5-10 diverse beliefs with relations
   - Add sample past interactions (10-20)
   - Generate embeddings and FAISS index
2. Document in setup guide

**Output**: Demo data
**Tests**: Run script, verify in dashboard
**DoD**: Demo persona ready for showcase

---

## Integration & Quality Assurance

### Task QA.1: Coverage Report for Week 4
**Input**: All week 4 code
**Action**:
1. Run pytest with coverage
2. Ensure >80% coverage on:
   - Retrieval pipeline
   - Agent loop logic
   - Belief updater
   - Dashboard APIs
3. Document gaps (UI, integration tests)
4. Generate HTML report

**Output**: Coverage metrics
**Tests**: Automated
**DoD**: Coverage threshold met

### Task QA.2: Performance Testing (Basic)
**Input**: Full system
**Action**:
1. Test agent loop performance:
   - Time to process 10 posts
   - Memory usage over 10 minutes
   - Cost per cycle
2. Test API response times (p95 <200ms)
3. Test FAISS search latency (<50ms)
4. Document results

**Output**: Performance baseline
**Tests**: Manual + scripted
**DoD**: Performance acceptable for MVP

### Task QA.3: Security Audit Checklist
**Input**: All code
**Action**:
1. Review checklist from 0_dev.md:
   - No secrets in code/logs
   - Authentication on all sensitive endpoints
   - Persona isolation enforced
   - Input validation on all APIs
   - Rate limiting in place
2. Document any findings
3. Fix critical issues

**Output**: Security review
**Tests**: Manual audit
**DoD**: No critical vulnerabilities

### Task QA.4: User Acceptance Test Plan
**Input**: Dashboard, agent loop
**Action**:
1. Create UAT scenarios:
   - Scenario 1: Admin reviews and approves pending post
   - Scenario 2: Admin manually updates belief confidence
   - Scenario 3: Admin locks stance to prevent auto-updates
   - Scenario 4: Agent autonomously posts (auto mode)
   - Scenario 5: View belief evolution over time
2. Execute tests, document results

**Output**: UAT report
**Tests**: Manual with checklist
**DoD**: All scenarios pass

---

## Definition of Done (Week 4)

**Agent Loop**:
- ✅ Perception phase fetches new posts
- ✅ Retrieval assembles context (beliefs + past statements + evidence)
- ✅ Decision phase generates drafts via LLM
- ✅ Consistency check validates against beliefs
- ✅ Moderation evaluates and routes (post/queue/drop)
- ✅ Action phase posts or enqueues
- ✅ Loop runs continuously with graceful shutdown
- ✅ Correlation IDs and cost logged per cycle

**Belief Updater**:
- ✅ Evidence-based confidence updates (Bayesian-style)
- ✅ Locked stance enforcement
- ✅ Stance versioning with history
- ✅ Audit log for all updates
- ✅ Conflict resolution logic
- ✅ Manual update support (admin override)

**Retrieval Pipeline**:
- ✅ Belief graph context assembly
- ✅ Semantic search for past self-comments (FAISS)
- ✅ Evidence snippet inclusion
- ✅ Prompt assembly within token budget
- ✅ Persona isolation in retrieval

**Dashboard Backend**:
- ✅ Activity feed API (`GET /activity`)
- ✅ Stats summary API (`GET /stats`)
- ✅ Belief graph data API (`GET /belief-graph`)
- ✅ Stance history API (`GET /beliefs/{id}/history`)
- ✅ Manual belief update API (`PUT /beliefs/{id}`)
- ✅ Lock/unlock API (`POST /beliefs/{id}/lock`)
- ✅ Nudge API (`POST /beliefs/{id}/nudge`)
- ✅ Personas list API (`GET /personas`)
- ✅ All moderation APIs from Week 3

**Dashboard Frontend**:
- ✅ Activity feed page (Next.js)
- ✅ Stats summary widget
- ✅ Moderation queue page with approve/reject
- ✅ Auto/manual posting toggle
- ✅ Belief graph visualization (force-directed)
- ✅ Belief detail modal with history
- ✅ Persona selector (multi-persona support)
- ✅ Type-safe API client (generated from OpenAPI)
- ✅ Responsive design (mobile-friendly)
- ✅ Error handling and loading states

**Optional Features** (if time permits):
- ⚪ SSE/WebSocket live updates
- ⚪ Governor chat interface
- ⚪ Cost monitoring dashboard
- ⚪ Dark mode

**Quality & Documentation**:
- ✅ >80% test coverage on agent logic and APIs
- ✅ Integration tests for full loop
- ✅ OpenAPI spec complete and validated
- ✅ Week 4 runbook with agent operations
- ✅ Architecture diagram updated
- ✅ README comprehensive
- ✅ Demo persona seeded
- ✅ Performance baseline documented
- ✅ Security audit completed
- ✅ UAT scenarios passed

**Deployment Ready**:
- ✅ Backend deployable to DigitalOcean
- ✅ Frontend deployable to Vercel
- ✅ Environment configuration documented
- ✅ Health checks operational
- ✅ Logs structured with correlation IDs
- ✅ Cost tracking active
- ✅ Rollback procedures documented

**Next Steps**:
MVP complete! Ready for:
- Real-world testing in test subreddits
- Iteration based on agent behavior
- Scale planning (PostgreSQL migration, Redis queue)
- Additional features (multi-agent coordination, advanced visualization)
