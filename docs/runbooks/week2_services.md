# Week 2 Services Runbook

Operational guide for Week 2 foundation services (Health, Auth, Config, Logging).

**Last Updated**: 2025-11-24
**Status**: Week 2 Complete - Ready for Production

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Service Overview](#service-overview)
3. [Initial Setup](#initial-setup)
4. [Testing Authentication](#testing-authentication)
5. [Health Check Operations](#health-check-operations)
6. [Settings Management](#settings-management)
7. [Troubleshooting](#troubleshooting)
8. [Monitoring](#monitoring)
9. [Security Checklist](#security-checklist)

---

## Quick Start

```bash
# 1. Install dependencies
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .

# 2. Set up environment
cp .env.example .env
# Edit .env with your credentials

# 3. Initialize database
alembic upgrade head

# 4. Seed admin user
python scripts/seed_admin.py

# 5. Run server
uvicorn app.main:app --reload --port 8000

# 6. Test health
curl http://localhost:8000/api/v1/health
```

---

## Service Overview

### Implemented Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/health` | GET | No | Liveness probe (always returns 200) |
| `/health/ready` | GET | No | Readiness probe (checks DB + OpenRouter) |
| `/health/agent` | GET | No | Agent status (stub - Week 4) |
| `/api/v1/auth/token` | POST | No | JWT token issuance |
| `/api/v1/auth/me` | GET | Yes | Get current user info |
| `/api/v1/protected/test` | GET | Yes | Protected endpoint example |
| `/api/v1/settings` | GET | Yes | Get persona settings |
| `/api/v1/settings` | POST | Yes | Update persona settings |

### Infrastructure

- **Database**: SQLite with async driver (aiosqlite)
- **Auth**: JWT tokens (60 minute expiry)
- **Rate Limiting**: 10 req/min (auth), 60 req/min (other)
- **Logging**: Structured JSON with request IDs
- **Security Headers**: CSP, X-Frame-Options, X-Content-Type-Options

---

## Initial Setup

### 1. Environment Configuration

Create `.env` file from template:

```bash
cd backend
cp .env.example .env
```

Required environment variables:

```env
# Security (CHANGE THESE!)
SECRET_KEY=your_secret_key_at_least_32_characters_long
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/reddit_agent.db

# Reddit API (get from https://www.reddit.com/prefs/apps)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=python:YourAppName:v1.0 (by /u/YourUsername)
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password

# OpenRouter API (get from https://openrouter.ai)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Agent Configuration
TARGET_SUBREDDITS=["test", "bottest"]
AUTO_POSTING_ENABLED=false

# CORS (frontend origin)
CORS_ORIGINS=["http://localhost:3000"]
```

**IMPORTANT**: Never commit real secrets to git. Verify `.env` is in `.gitignore`.

### 2. Database Initialization

```bash
# Apply migrations
alembic upgrade head

# Verify database was created
ls data/reddit_agent.db
```

### 3. Seed Admin User

```bash
# Create default admin user
python scripts/seed_admin.py

# Default credentials:
# Username: admin
# Password: changeme123
```

**IMPORTANT**: Change the default password immediately in production!

### 4. Seed Default Configuration (Optional)

```bash
# Create default persona config
python scripts/seed_default_config.py
```

---

## Testing Authentication

### 1. Get JWT Token

```bash
# Using curl
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=changeme123"

# Response:
# {
#   "access_token": "eyJhbGc...",
#   "token_type": "bearer"
# }
```

### 2. Use Token with Protected Endpoint

```bash
# Save token to variable
TOKEN="eyJhbGc..."

# Test protected endpoint
curl http://localhost:8000/api/v1/protected/test \
  -H "Authorization: Bearer $TOKEN"

# Response:
# {
#   "message": "Hello admin"
# }
```

### 3. Get Current User

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"

# Response:
# {
#   "username": "admin",
#   "full_name": "Admin User"
# }
```

### 4. Test Token Expiry

Tokens expire after 60 minutes (default). After expiry:

```bash
curl http://localhost:8000/api/v1/protected/test \
  -H "Authorization: Bearer $EXPIRED_TOKEN"

# Response: 401 Unauthorized
# {
#   "detail": "Could not validate credentials"
# }
```

---

## Health Check Operations

### 1. Liveness Probe

Always returns 200 if service is running:

```bash
curl http://localhost:8000/api/v1/health

# Response:
# {
#   "status": "ok",
#   "timestamp": "2025-11-24T12:00:00Z"
# }
```

**Use Case**: Kubernetes liveness probe, uptime monitoring

### 2. Readiness Probe

Checks database and OpenRouter connectivity:

```bash
curl http://localhost:8000/api/v1/health/ready

# All healthy:
# {
#   "status": "ready",
#   "timestamp": "2025-11-24T12:00:00Z",
#   "checks": {
#     "db": {"healthy": true, "latency_ms": 2.5},
#     "openrouter": {"healthy": true, "latency_ms": 150}
#   }
# }

# Dependency failure (returns 503):
# {
#   "status": "not_ready",
#   "timestamp": "2025-11-24T12:00:00Z",
#   "checks": {
#     "db": {"healthy": false, "error": "Database connection failed"},
#     "openrouter": {"healthy": true, "latency_ms": 150}
#   }
# }
```

**Use Case**: Kubernetes readiness probe, deployment gates

### 3. Agent Status

Returns stub response (implemented in Week 4):

```bash
curl http://localhost:8000/api/v1/health/agent

# Response:
# {
#   "status": "not_started",
#   "last_activity": null
# }
```

---

## Settings Management

Settings are persona-scoped configuration values stored in the database.

### 1. Get Persona Settings

```bash
# Get settings for persona
curl "http://localhost:8000/api/v1/settings?persona_id=<PERSONA_ID>" \
  -H "Authorization: Bearer $TOKEN"

# Response (empty):
# {
#   "persona_id": "...",
#   "config": {}
# }

# Response (with config):
# {
#   "persona_id": "...",
#   "config": {
#     "target_subreddits": ["test", "bottest"],
#     "auto_posting_enabled": false
#   }
# }
```

### 2. Update Settings

```bash
# Create/update a setting
curl -X POST http://localhost:8000/api/v1/settings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "<PERSONA_ID>",
    "key": "auto_posting_enabled",
    "value": true
  }'

# Response:
# {
#   "persona_id": "...",
#   "key": "auto_posting_enabled",
#   "value": true,
#   "updated": true
# }
```

### 3. Settings Validation

Unsafe keys are blocked:

```bash
# Attempt to set unsafe key
curl -X POST http://localhost:8000/api/v1/settings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "<PERSONA_ID>",
    "key": "admin_password",
    "value": "hack"
  }'

# Response: 400 Bad Request
# {
#   "detail": "Setting key 'admin_password' is not allowed"
# }
```

---

## Troubleshooting

### Issue: Database Locked

**Symptom**: `database is locked` error in logs

**Cause**: Multiple processes accessing SQLite without WAL mode

**Solution**:
1. Ensure WAL mode is enabled (should be automatic)
2. Check no other processes have file lock
3. Restart server

```bash
# Check database file
ls -la data/reddit_agent.db*

# Restart server
pkill -f "uvicorn app.main:app"
uvicorn app.main:app --reload --port 8000
```

### Issue: Invalid Credentials (401)

**Symptom**: Login fails with 401 even with correct password

**Causes**:
1. Wrong password
2. Admin user not seeded
3. Database migration not applied

**Solution**:

```bash
# Re-seed admin user
python scripts/seed_admin.py

# Verify admin exists
sqlite3 data/reddit_agent.db "SELECT username FROM admins;"
```

### Issue: Secret Key Error

**Symptom**: `SECRET_KEY must be at least 32 characters` error on startup

**Cause**: Invalid or missing SECRET_KEY in `.env`

**Solution**:

```bash
# Generate secure key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update .env
SECRET_KEY=<generated_key>
```

### Issue: Token Expired

**Symptom**: 401 error on protected endpoints after initial success

**Cause**: JWT token expired (60 minute default)

**Solution**: Request new token via `/api/v1/auth/token`

### Issue: Rate Limit Exceeded (429)

**Symptom**: `429 Too Many Requests` error

**Cause**: Exceeded rate limit (10 req/min for auth, 60 req/min for others)

**Solution**: Wait 60 seconds and retry. For testing, increase limits in `app/main.py`:

```python
app.add_middleware(
    RateLimitMiddleware,
    auth_limit=100,  # Increase for testing
    default_limit=600
)
```

### Issue: CORS Error in Frontend

**Symptom**: Browser console shows CORS error when calling API

**Cause**: Frontend origin not in CORS_ORIGINS

**Solution**: Add frontend URL to `.env`:

```env
CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"]
```

### Issue: Readiness Probe Failing

**Symptom**: `/health/ready` returns 503

**Causes**:
1. Database not initialized
2. OpenRouter API key invalid
3. Network connectivity issue

**Diagnosis**:

```bash
# Check detailed probe response
curl http://localhost:8000/api/v1/health/ready | jq

# Check logs for errors
tail -f logs/app.log  # If logging to file
```

**Solutions**:
- **DB issue**: Run `alembic upgrade head`
- **OpenRouter issue**: Verify API key in `.env`
- **Network issue**: Check firewall, internet connection

---

## Monitoring

### Request IDs

Every request has a correlation ID:

```bash
# Custom request ID
curl http://localhost:8000/api/v1/health \
  -H "X-Request-ID: custom-123"

# Response includes same ID
# Headers: X-Request-ID: custom-123
```

### Structured Logs

All requests produce JSON logs with:
- `timestamp`: ISO 8601 timestamp
- `level`: Log level (INFO, ERROR, etc.)
- `path`: Request path
- `status_code`: HTTP status code
- `latency_ms`: Request latency in milliseconds
- `request_id`: Correlation ID

**Example log entry**:

```json
{
  "timestamp": "2025-11-24T12:00:00Z",
  "level": "INFO",
  "path": "/api/v1/health",
  "status_code": 200,
  "latency_ms": 2.5,
  "request_id": "abc-123-def"
}
```

### Health Monitoring

Set up monitoring on:
- `/health` - every 10 seconds (liveness)
- `/health/ready` - every 30 seconds (readiness)

Alert on:
- 5+ consecutive failures of liveness probe
- 3+ consecutive failures of readiness probe
- 95th percentile latency > 1000ms

### Rate Limit Monitoring

Monitor 429 responses:

```bash
# Count 429s in logs
grep '"status_code": 429' logs/app.log | wc -l
```

Alert if 429 rate > 5% of requests.

---

## Security Checklist

### Before Production Deployment

- [ ] Changed default admin password from `changeme123`
- [ ] Generated secure `SECRET_KEY` (32+ characters)
- [ ] Verified no secrets in `.env.example` or git
- [ ] Enabled HTTPS (if deployed)
- [ ] Configured proper CORS origins (no wildcards)
- [ ] Set up API key for OpenRouter
- [ ] Reviewed rate limits for production load
- [ ] Enabled security headers (already configured)
- [ ] Set up log rotation
- [ ] Configured database backups
- [ ] Tested token expiry and refresh flow
- [ ] Verified persona isolation (no cross-persona data leaks)

### Security Headers Enabled

Automatically added to all responses:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- Basic CSP (can be customized)

### Password Policy

- Admin passwords hashed with bcrypt (12 rounds)
- Never log passwords (even failed attempts)
- Use strong passwords (12+ characters, mixed case, numbers, symbols)

### Token Security

- Tokens expire after 60 minutes
- Tokens include `sub` (username), `exp` (expiry), `iat` (issued at)
- Algorithm: HS256
- Tokens are stateless (server doesn't store them)

**Token Refresh**: Not yet implemented. Users must re-authenticate after expiry.

---

## Common Operations

### Change Admin Password

Currently requires direct database access:

```bash
# Generate hash
python -c "from app.core.security import get_password_hash; print(get_password_hash('new_password'))"

# Update in database
sqlite3 data/reddit_agent.db
> UPDATE admins SET hashed_password='<new_hash>' WHERE username='admin';
> .quit
```

**TODO**: Add password change endpoint in Week 3.

### Add New Admin User

```bash
# Create script or modify seed_admin.py
python -c "
from app.models.user import Admin
from app.core.security import get_password_hash
from app.core.database import async_session_maker
import asyncio

async def add_admin():
    async with async_session_maker() as session:
        admin = Admin(
            username='newadmin',
            hashed_password=get_password_hash('secure_password')
        )
        session.add(admin)
        await session.commit()

asyncio.run(add_admin())
"
```

### Clear Rate Limit Bucket

Rate limits are in-memory (resets on server restart):

```bash
# Restart server to clear limits
pkill -f "uvicorn app.main:app"
uvicorn app.main:app --reload --port 8000
```

### View All Settings for Persona

```bash
# Get persona ID first (from database or API)
PERSONA_ID="<uuid>"

# Get all settings
curl "http://localhost:8000/api/v1/settings?persona_id=$PERSONA_ID" \
  -H "Authorization: Bearer $TOKEN" | jq
```

---

## Next Steps

Week 2 foundation services are complete and production-ready. Ready for Week 3:

1. **Memory Store** - Episodic memory with FAISS retrieval
2. **Reddit Client** - asyncpraw with rate limiting and retry logic
3. **LLM Client** - OpenRouter integration with cost tracking
4. **Belief Graph** - Initial schema and CRUD operations

Refer to `docs/week3.md` for implementation plan.

---

## References

- **API Documentation**: `/docs` (Swagger UI) or `/redoc` (ReDoc)
- **OpenAPI Spec**: `docs/api/openapi.yaml`
- **Technical Spec**: `docs/MVP_Reddit_AI_Agent_Technical_Specification.md`
- **Quality Standards**: `docs/0_dev.md`
- **Secrets Runbook**: `docs/runbooks/secrets.md`
- **Week 2 Plan**: `docs/week2.md`

---

**Document Version**: 1.0
**Last Reviewed**: 2025-11-24
**Reviewer**: Claude Code
**Status**: Production Ready
