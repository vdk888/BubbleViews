# Week 3 Plan — Core Agent Services (Memory, Reddit Client, LLM, Moderation Scaffold)
Scope: build persona-scoped memory + belief graph, Reddit client, LLM client, and moderation scaffold per contract-first design, ready for multi-persona and self-consistency retrieval.

## Work Items (detailed tasks)
1) Data layer & migrations  
   - Finalize Alembic migration for personas, belief_nodes, belief_edges, stance_versions, evidence_links, interactions, pending_posts, agent_config.  
   - Add indices from architecture plan; ensure JSON validity checks in SQLite.  
   - Tests: migration apply/rollback on fresh DB.

2) Memory store implementation  
   - Implement `IMemoryStore`: `query_belief_graph(persona_id)`, `update_stance_version` (respect locked), `append_evidence`, `log_interaction` (store metadata), `search_history` (FAISS-backed).  
   - Persist FAISS index to `data/faiss_index.bin`; rebuild on missing file.  
   - Persona isolation in queries; enforce `persona_id` required.  
   - Tests: CRUD for nodes/edges/stances, lock enforcement, evidence append, interaction log, FAISS save/load round-trip, persona isolation.

3) Reddit client  
   - Implement interface wrapping asyncpraw with token bucket (60 req/min), retries on 429/5xx with jitter.  
   - Methods: `get_new_posts(subreddits)`, `search_posts`, `submit_post`, `reply`.  
   - Support persona-specific creds (future-ready selection by persona_id).  
   - Tests: mock asyncpraw to validate retry/backoff, rate limiter behavior, persona credential selection.

4) LLM client  
   - Assemble prompts per spec; generate (primary model) and consistency check (secondary).  
   - Add retry/backoff; cost calculation logged.  
   - Tests: prompt formatting, error handling, cost math, retry path; consistency checker returns parsed JSON.

5) Moderation scaffold  
   - Service to evaluate drafts (placeholder rules/LLM hook); enqueue to `pending_posts` when auto_posting_disabled; allow override for flagged content.  
   - API stubs for moderation endpoints: list pending, approve, reject, flag-override.  
   - Tests: flagged → queue, auto toggle true → immediate allow, false → pending; approve/reject flows update status.

## Definition of Done
- Interfaces under `services/interfaces`; concrete impls under `services/`.
- Migration applied; schema matches plan.
- FAISS index persists and reloads; fallback rebuild works.
- OpenAPI updated for moderation endpoints and settings.
- Unit/contract tests cover memory, Reddit client, LLM client, moderation scaffold; coverage tracked.
- Logs include cost per LLM call; correlation IDs retained.
