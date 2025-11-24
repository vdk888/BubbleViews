# Week 2 Plan — Foundation Services (Health, Auth, Config, Logging)
Scope: implement baseline API health, auth, and configuration plumbing to support later agent services. SQLite for MVP, Postgres-ready contracts. Align with 0_dev quality: tests, DI, observability, secrets hygiene.

## Work Items (detailed tasks)
1) Health endpoints
   - Add `/health` (liveness), `/health/ready` (DB + OpenRouter), `/health/agent` (loop/queue status stub).
   - Implement DB probe (`SELECT 1`), OpenRouter HEAD/ping, queue readiness flag.
   - Wire FastAPI dependencies for checks to keep testability.
   - Tests: unit for probe functions (success/failure), integration for 200 vs 503 paths.

2) Structured logging + request IDs
   - Add middleware to generate/propagate correlation/request IDs (header `X-Request-ID`).
   - Configure JSON logging format: timestamp, level, path, status, latency, request_id, persona_id (if present), cost placeholder.
   - Ensure exceptions are logged with request_id.
   - Tests: unit asserting header propagation; log line matches expected keys (regex).

3) Auth service
   - Create admin user store (SQLite table or config seeding) with hashed password (bcrypt).
   - Implement `POST /api/v1/auth/token` (JWT issuance) with expiry; no refresh for MVP.
   - Add password hashing/verification helpers; secret from env.
   - Protect sample endpoint via dependency; return 401/403 correctly.
   - Tests: unit for token generation/expiry/invalid; integration for 401/200 paths on protected route.

4) Config surface (persona-aware)
   - Add Pydantic schemas for settings: target_subreddits, auto_posting_enabled, safety flags.
   - Implement `GET/POST /api/v1/settings` (persona-scoped) backed by `agent_config`.
   - Validate/disallow unsafe keys; enforce JSON validity.
   - Tests: CRUD round-trip, validation errors, persona isolation.

5) Security hygiene
   - Add basic rate limit middleware for auth endpoints (per-IP small bucket).
   - Write/update `docs/runbooks/secrets.md` for rotation and no-real-secrets policy.
   - Verify `.env.example` contains placeholders (not live secrets).

## Definition of Done
- OpenAPI documents health/auth/settings; client regenerated.
- Health endpoints return correct status for fail/success probes.
- Structured JSON logs include request_id; validated by test.
- Auth protected route works; tests cover happy/deny cases.
- Settings CRUD works per persona; validation enforced.
- Secret handling runbook updated; rate limiting active on auth.
