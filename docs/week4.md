# Week 4 Plan — Agent Logic, Belief Updates, Dashboard Slice
Scope: wire perception → retrieval → decision → moderation → action loop; implement belief updater; deliver first dashboard slice (activity/moderation/belief snapshot); add governor chat stub if time permits. Aligns with technical spec, brainstorming UX, and 0_dev quality.

## Work Items (detailed tasks)
1) Agent loop  
   - Implement periodic poller for target subreddits (config per persona).  
   - Assemble context: thread/post data + retrieved beliefs (nodes/edges + current stance) + past self-comments (FAISS search).  
   - Draft via primary model; include persona prompt, stance, and past statements.  
   - Send draft through moderation scaffold; post or enqueue based on auto flag.  
   - Graceful shutdown, backoff on errors; ensure correlation IDs and cost logging.

2) Belief updater  
   - Map evidence strength → confidence delta; update stance_version; mark previous deprecated; respect locked stances.  
   - Consistency check with secondary model; if conflict, flag/update per policy.  
   - Log audit to `belief_updates` with before/after JSON and trigger type.  
   - Tests: deterministic updates per strength, locked stance blocked, audit row created.

3) Retrieval composition  
   - Implement retrieval pipeline: FAISS similar self-comments (k configurable), belief graph fetch (nodes/edges/current stance), evidence snippets if available.  
   - Compose prompt sections deterministically (persona, stances, past statements, current thread).  
   - Tests: retrieval returns expected items; prompt contains past statements when available; persona isolation enforced.

4) Dashboard slice (backend + frontend)  
   - Backend endpoints: `GET /activity`, `GET /moderation/pending`, `POST /moderation/approve`, `POST /moderation/reject`, `GET /belief-graph`.  
   - Frontend: activity list, moderation queue with approve/reject actions, simple belief graph view (nodes/edges), auto/manual toggle control surfaced.  
   - Tests: API integration for endpoints; frontend lint/build, basic render checks for pages/components.

5) Live updates (optional/bonus)  
   - SSE/WebSocket endpoint `GET /stream` for new activity/moderation events.  
   - Tests: connection established; event shape validated (if implemented).

6) Governor chat stub (if time allows)  
   - Add backend endpoint `POST /governor/query` to return summaries/explanations (no posting).  
   - Minimal frontend entry point (text area + response view).  
   - Tests: backend unit for prompt assembly; integration hitting stub.

## Definition of Done
- Agent loop posts to test subreddit in auto mode and enqueues in manual mode; logs include correlation IDs and cost.  
- Belief updates recorded with before/after JSON; evidence link stored when present; locked stances respected.  
- Dashboard shows activity, moderation queue, belief graph snapshot; auto/manual toggle works.  
- OpenAPI updated for new endpoints; frontend client regenerated.  
- Integration tests for loop + moderation + retrieval; unit tests for updater; frontend smoke tests pass.  
- Runbooks updated (deployment, rollback); optional live updates/governor stub documented if shipped.
