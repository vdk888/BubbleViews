# Week 2 Plan — Foundation Services (Health, Auth, Config, Logging)

**Scope**: Implement baseline API health, auth, and configuration plumbing to support later agent services. SQLite for MVP, Postgres-ready contracts. Align with 0_dev quality: tests, DI, observability, secrets hygiene.

**Estimated effort**: 5 days, 30 micro-tasks

---

## Day 1: Health Endpoints & Observability Setup

### Task 1.1: Health Endpoint Base Structure
**Input**: FastAPI app skeleton
**Action**:
1. Create `backend/app/api/v1/health.py`
2. Define basic `/health` endpoint returning `{"status": "ok", "timestamp": "..."}`
3. Add router to main app
4. Run server and verify 200 response

**Output**: Working liveness endpoint
**Tests**: Integration test for 200 status
**DoD**: `curl http://localhost:8000/health` returns 200

### Task 1.2: Database Readiness Probe
**Input**: SQLite connection configured
**Action**:
1. Create `backend/app/core/probes.py`
2. Implement `async def check_database() -> bool` executing `SELECT 1`
3. Handle connection errors gracefully (return False)
4. Add timeout (2 seconds)

**Output**: Reusable DB probe function
**Tests**: Unit test with mock DB (success/failure paths)
**DoD**: Function returns True on success, False on timeout/error

### Task 1.3: OpenRouter Readiness Probe
**Input**: OpenRouter config in settings
**Action**:
1. Add `async def check_openrouter() -> bool` in probes.py
2. Execute HEAD request to `OPENROUTER_BASE_URL/models`
3. Consider 200-299 status as healthy
4. Add 3-second timeout

**Output**: OpenRouter connectivity probe
**Tests**: Unit test with httpx mock
**DoD**: Function validates API reachability

### Task 1.4: Readiness Endpoint with Dependencies
**Input**: DB and OpenRouter probes
**Action**:
1. Add `GET /health/ready` endpoint
2. Inject probes as FastAPI dependencies
3. Execute both checks in parallel using `asyncio.gather()`
4. Return 503 if any check fails, 200 if all pass
5. Include probe details in response: `{"status": "ready", "checks": {"db": true, "openrouter": true}}`

**Output**: Comprehensive readiness endpoint
**Tests**: Integration test with mocked probes (all pass, one fails, all fail)
**DoD**: Endpoint returns correct status codes based on probe results

### Task 1.5: Agent Status Stub
**Input**: None
**Action**:
1. Add `GET /health/agent` endpoint
2. Return stub response: `{"status": "not_started", "last_activity": null}`
3. Document this will be implemented in Week 4

**Output**: Agent status placeholder
**Tests**: Integration test for 200 response
**DoD**: Endpoint exists and returns expected shape

### Task 1.6: Request ID Middleware
**Input**: FastAPI app
**Action**:
1. Create `backend/app/middleware/request_id.py`
2. Implement middleware that:
   - Reads `X-Request-ID` header or generates UUID
   - Adds to request state: `request.state.request_id`
   - Includes in response header: `X-Request-ID`
3. Register middleware in app

**Output**: Request correlation support
**Tests**: Unit test verifying header propagation (provided/generated)
**DoD**: All requests have X-Request-ID in response

### Task 1.7: Structured JSON Logging Configuration
**Input**: Python logging module
**Action**:
1. Create `backend/app/core/logging_config.py`
2. Configure JSON formatter with fields:
   - timestamp, level, message, path, status_code, latency_ms
   - request_id, persona_id (if present)
   - cost (placeholder, to be populated by LLM calls)
3. Set up handlers for stdout
4. Initialize on app startup

**Output**: JSON logging configuration
**Tests**: Unit test that log output matches expected JSON keys
**DoD**: Logs are valid JSON with all required fields

### Task 1.8: Logging Middleware
**Input**: Request ID middleware, logging config
**Action**:
1. Create middleware to log every request/response
2. Capture: method, path, status, latency
3. Extract request_id from state
4. Log exceptions with traceback included
5. Register after request ID middleware

**Output**: Request/response logging
**Tests**: Integration test checking log output for sample request
**DoD**: Every API call produces structured log entry

---

## Day 2: Authentication Foundation

### Task 2.1: Admin User Model
**Input**: SQLAlchemy base
**Action**:
1. Create `backend/app/models/user.py`
2. Define `Admin` model:
   - id (UUID primary key)
   - username (unique)
   - hashed_password
   - created_at, updated_at (ISO timestamps)
3. Add to Alembic migration

**Output**: Admin user table
**Tests**: Migration test (apply/rollback)
**DoD**: Table created in SQLite with constraints

### Task 2.2: Password Hashing Utilities
**Input**: passlib dependency
**Action**:
1. Create `backend/app/core/security.py`
2. Implement `hash_password(plain: str) -> str` using bcrypt
3. Implement `verify_password(plain: str, hashed: str) -> bool`
4. Use bcrypt context with configurable rounds (default: 12)

**Output**: Password utilities
**Tests**: Unit test hash/verify round-trip, failure on mismatch
**DoD**: Functions work correctly with bcrypt

### Task 2.3: JWT Token Generation
**Input**: python-jose dependency, secret key from config
**Action**:
1. Add to `security.py`:
   - `create_access_token(data: dict, expires_delta: timedelta) -> str`
   - Include claims: sub (username), exp (expiry), iat (issued at)
   - Use HS256 algorithm
2. Load SECRET_KEY from settings

**Output**: JWT generation function
**Tests**: Unit test decoding token, verifying claims
**DoD**: Token can be decoded with secret key

### Task 2.4: JWT Token Validation
**Input**: JWT generation function
**Action**:
1. Add `verify_token(token: str) -> dict | None` to security.py
2. Decode with SECRET_KEY, algorithm HS256
3. Handle ExpiredSignatureError, InvalidTokenError → return None
4. Return decoded payload on success

**Output**: Token validation
**Tests**: Unit test with valid, expired, and invalid tokens
**DoD**: Function returns correct results for all cases

### Task 2.5: Seed Admin User Script
**Input**: Admin model, password hashing
**Action**:
1. Create `backend/scripts/seed_admin.py`
2. Insert default admin:
   - username: "admin"
   - password: hash_password("changeme123")
3. Check if admin exists before inserting
4. Add instructions to README

**Output**: Database seeding script
**Tests**: Manual verification after running
**DoD**: Admin user exists in database

### Task 2.6: Token Endpoint
**Input**: Admin model, JWT functions
**Action**:
1. Create `backend/app/api/v1/auth.py`
2. Add `POST /api/v1/auth/token` endpoint
3. Accept username/password in request body (Pydantic schema)
4. Query admin user, verify password
5. Return JWT token with expiry (60 minutes default)
6. Return 401 on invalid credentials

**Output**: Token issuance endpoint
**Tests**: Integration test (valid login → token, invalid → 401)
**DoD**: Endpoint returns valid JWT on correct credentials

### Task 2.7: Authentication Dependency
**Input**: JWT validation
**Action**:
1. Create `backend/app/api/dependencies.py`
2. Implement `get_current_user()` dependency:
   - Extract Bearer token from Authorization header
   - Validate using `verify_token()`
   - Return username or raise 401 HTTPException
3. Support FastAPI `Depends()` injection

**Output**: Reusable auth dependency
**Tests**: Unit test with valid/missing/expired tokens
**DoD**: Dependency raises 401 on invalid auth

### Task 2.8: Protected Route Example
**Input**: Auth dependency
**Action**:
1. Add endpoint `GET /api/v1/protected/test`
2. Inject `current_user: str = Depends(get_current_user)`
3. Return `{"message": "Hello {username}"}`

**Output**: Sample protected endpoint
**Tests**: Integration test (with token → 200, without → 401)
**DoD**: Authorization works end-to-end

---

## Day 3: Configuration & Settings API

### Task 3.1: Agent Config Schema
**Input**: Pydantic models
**Action**:
1. Create `backend/app/schemas/config.py`
2. Define `AgentConfigSchema`:
   - target_subreddits: List[str]
   - auto_posting_enabled: bool
   - safety_flags: Dict[str, Any]
   - persona_style: Dict[str, float] (sliders, e.g., directness, formality)
3. Add validation (non-empty subreddit list)

**Output**: Configuration schema
**Tests**: Unit test schema validation (valid/invalid)
**DoD**: Schema enforces business rules

### Task 3.2: Agent Config Model
**Input**: SQLAlchemy base, personas table
**Action**:
1. Create `backend/app/models/config.py`
2. Define `AgentConfig` model:
   - id (UUID PK)
   - persona_id (FK to personas)
   - config_key (TEXT, e.g., "target_subreddits")
   - config_value (JSON TEXT)
   - updated_at
   - Unique constraint on (persona_id, config_key)
3. Add JSON validity check

**Output**: Config storage model
**Tests**: Migration test
**DoD**: Table schema matches design

### Task 3.3: Settings Repository
**Input**: Agent config model
**Action**:
1. Create `backend/app/repositories/config.py`
2. Implement class `ConfigRepository`:
   - `get_config(persona_id: str, key: str) -> dict | None`
   - `set_config(persona_id: str, key: str, value: dict)`
   - `delete_config(persona_id: str, key: str)`
3. Use SQLAlchemy async sessions
4. Parse JSON from config_value column

**Output**: Config data access layer
**Tests**: Unit test CRUD operations with in-memory DB
**DoD**: Repository implements contract

### Task 3.4: Settings GET Endpoint
**Input**: ConfigRepository, auth dependency
**Action**:
1. Add to `backend/app/api/v1/settings.py`
2. Create `GET /api/v1/settings?persona_id={id}`
3. Inject auth and repository as dependencies
4. Fetch all config keys for persona
5. Return as JSON dict: `{key: value, ...}`
6. Return empty dict if no config

**Output**: Settings retrieval endpoint
**Tests**: Integration test (with/without data)
**DoD**: Endpoint returns persona-scoped config

### Task 3.5: Settings POST Endpoint
**Input**: ConfigRepository, AgentConfigSchema
**Action**:
1. Add `POST /api/v1/settings`
2. Accept persona_id, key, value in request body
3. Validate value against appropriate schema (if key known)
4. Deny unsafe keys (hardcoded blocklist)
5. Call repository to upsert config
6. Return updated config

**Output**: Settings update endpoint
**Tests**: Integration test (valid update, invalid key, validation failure)
**DoD**: Settings persist correctly

### Task 3.6: Persona Isolation Enforcement
**Input**: Settings endpoints
**Action**:
1. Review all config queries
2. Ensure persona_id is always required (no global queries)
3. Add validation that persona exists (FK constraint helps)
4. Document persona_id requirement in OpenAPI

**Output**: Guaranteed persona isolation
**Tests**: Test attempting cross-persona access (should fail)
**DoD**: No endpoint leaks data across personas

### Task 3.7: Default Config Seeding
**Input**: ConfigRepository
**Action**:
1. Create `backend/scripts/seed_default_config.py`
2. For default persona, seed:
   - target_subreddits: ["test", "bottest"]
   - auto_posting_enabled: false
   - safety_flags: {"require_approval": true}
3. Run during initial setup

**Output**: Default configuration
**Tests**: Manual verification
**DoD**: Default persona has working config

---

## Day 4: Security Hardening

### Task 4.1: Rate Limiting Middleware
**Input**: FastAPI app
**Action**:
1. Create `backend/app/middleware/rate_limit.py`
2. Implement simple token bucket per IP:
   - 10 requests/minute for auth endpoints
   - 60 requests/minute for other endpoints
3. Use in-memory dict (acceptable for MVP)
4. Return 429 when limit exceeded

**Output**: Basic rate limiting
**Tests**: Integration test hitting endpoint repeatedly
**DoD**: 429 returned after threshold

### Task 4.2: CORS Configuration
**Input**: FastAPI app
**Action**:
1. Add `CORSMiddleware` to app
2. Configure allowed origins from environment (default: localhost:3000 for frontend)
3. Allow credentials, common headers
4. Document in config

**Output**: CORS policy
**Tests**: Manual test from frontend dev server
**DoD**: Frontend can call API

### Task 4.3: Secrets Rotation Runbook
**Input**: None
**Action**:
1. Create `docs/runbooks/secrets.md`
2. Document:
   - How to rotate JWT secret (regenerate, deploy, invalidates all tokens)
   - Reddit API credentials rotation
   - OpenRouter API key rotation
   - No real secrets in .env.example or git
3. Include rollback procedures

**Output**: Secrets management documentation
**Tests**: N/A (docs)
**DoD**: Runbook complete and reviewed

### Task 4.4: Environment Validation
**Input**: Pydantic settings
**Action**:
1. Update `backend/app/core/config.py`
2. Add validators ensuring:
   - SECRET_KEY is at least 32 chars
   - DATABASE_URL is valid
   - Required Reddit/OpenRouter keys present
3. Raise clear error on startup if validation fails

**Output**: Config validation
**Tests**: Unit test with missing/invalid env vars
**DoD**: App won't start with bad config

### Task 4.5: Security Headers Middleware
**Input**: FastAPI app
**Action**:
1. Create middleware adding headers:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `X-XSS-Protection: 1; mode=block`
   - Basic CSP (document relaxed for MVP)
2. Register middleware

**Output**: Security headers
**Tests**: Integration test verifying headers in response
**DoD**: Headers present on all responses

### Task 4.6: .env.example Audit
**Input**: Current .env.example
**Action**:
1. Review file for actual secrets
2. Replace with placeholders:
   - `SECRET_KEY=CHANGE_ME_32_CHARS_MIN`
   - `REDDIT_PASSWORD=YOUR_PASSWORD_HERE`
   - `OPENROUTER_API_KEY=sk-or-...`
3. Add comments for each variable

**Output**: Safe example file
**Tests**: Manual review
**DoD**: No real credentials in example file

---

## Day 5: Testing & Documentation

### Task 5.1: Health Endpoints Integration Tests
**Input**: Health endpoints
**Action**:
1. Create `backend/tests/integration/test_health.py`
2. Test cases:
   - `/health` returns 200
   - `/health/ready` returns 200 when DB/OpenRouter up
   - `/health/ready` returns 503 when DB down (mock failure)
   - `/health/agent` returns stub response
3. Use pytest fixtures for app client

**Output**: Health test suite
**Tests**: Self-validating
**DoD**: All tests pass, coverage >90%

### Task 5.2: Auth Flow Integration Tests
**Input**: Auth endpoints
**Action**:
1. Create `backend/tests/integration/test_auth.py`
2. Test cases:
   - Valid credentials → token with correct expiry
   - Invalid credentials → 401
   - Token refresh (not implemented, document)
   - Protected endpoint with valid token → 200
   - Protected endpoint without token → 401
   - Protected endpoint with expired token → 401

**Output**: Auth test suite
**Tests**: Self-validating
**DoD**: All auth flows covered

### Task 5.3: Settings API Integration Tests
**Input**: Settings endpoints
**Action**:
1. Create `backend/tests/integration/test_settings.py`
2. Test cases:
   - GET empty config → {}
   - POST new config → persisted
   - GET after POST → returns correct data
   - POST unsafe key → rejected
   - POST invalid JSON → validation error
   - Cross-persona isolation (two personas)

**Output**: Settings test suite
**Tests**: Self-validating
**DoD**: CRUD and isolation verified

### Task 5.4: Logging Verification Test
**Input**: Logging middleware
**Action**:
1. Create test capturing log output
2. Make sample request
3. Parse JSON log
4. Assert fields present:
   - timestamp, level, path, status_code, latency_ms, request_id
5. Verify request_id matches response header

**Output**: Logging test
**Tests**: Self-validating
**DoD**: Structured logging validated

### Task 5.5: OpenAPI Specification Update
**Input**: All endpoints
**Action**:
1. Generate OpenAPI schema from FastAPI
2. Add descriptions for each endpoint
3. Document authentication requirement (BearerAuth)
4. Export to `docs/api/openapi.yaml`
5. Generate TypeScript client for frontend (optional)

**Output**: API documentation
**Tests**: Validate schema with openapi-spec-validator
**DoD**: Schema is valid and complete

### Task 5.6: Week 2 Runbook
**Input**: All implemented services
**Action**:
1. Create `docs/runbooks/week2_services.md`
2. Document:
   - How to seed admin user
   - How to test auth flow with curl
   - How to check health endpoints
   - How to update settings
   - Common troubleshooting (DB locked, wrong secret key)

**Output**: Operational runbook
**Tests**: Follow runbook manually
**DoD**: New developer can run all services

### Task 5.7: Coverage Report
**Input**: All tests
**Action**:
1. Run pytest with coverage:
   ```bash
   pytest --cov=app --cov-report=html
   ```
2. Review report, ensure >80% coverage on core, api, models
3. Document gaps (acceptable for MVP)
4. Add coverage badge to README

**Output**: Coverage metrics
**Tests**: Automated
**DoD**: Coverage threshold met

---

## Definition of Done (Week 2)

**Endpoints**:
- ✅ `GET /health` (200)
- ✅ `GET /health/ready` (200 when ready, 503 when not)
- ✅ `GET /health/agent` (stub)
- ✅ `POST /api/v1/auth/token` (JWT issuance)
- ✅ `GET /api/v1/protected/test` (protected example)
- ✅ `GET /api/v1/settings` (persona-scoped config)
- ✅ `POST /api/v1/settings` (config update)

**Infrastructure**:
- ✅ Structured JSON logging with request IDs
- ✅ JWT authentication working end-to-end
- ✅ Admin user seeded in database
- ✅ Rate limiting on auth endpoints
- ✅ Security headers on all responses
- ✅ CORS configured for frontend

**Quality**:
- ✅ OpenAPI spec complete and valid
- ✅ >80% test coverage on implemented code
- ✅ Integration tests pass for all endpoints
- ✅ Secrets runbook documented
- ✅ No real secrets in repository
- ✅ Week 2 runbook complete

**Next Steps**:
Ready for Week 3 (Memory Store, Reddit Client, LLM Client)
