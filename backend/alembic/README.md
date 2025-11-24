# Database Migrations

This directory contains Alembic database migrations for the Reddit AI Agent project.

## Overview

We use Alembic for database schema versioning and migrations. All migrations are:
- **Forward-only**: Never modify existing migrations after they've been applied in production
- **Transactional**: Each migration runs in a transaction (SQLite DDL support)
- **Tested**: All migrations have been tested for both upgrade and downgrade

## Current Schema (Week 3 Day 1)

### Core Tables

#### personas
Stores persona/account information for multi-account support.
- `id`: UUID primary key
- `reddit_username`: Unique Reddit username
- `display_name`: Human-friendly display name
- `config`: JSON configuration (tone, style, values)
- `created_at`, `updated_at`: Timestamps

#### belief_nodes
Represents individual beliefs in the belief graph.
- `id`: UUID primary key
- `persona_id`: Foreign key to personas
- `title`: Belief title (max 500 chars)
- `summary`: Detailed belief summary
- `current_confidence`: Float 0-1 (Bayesian confidence)
- `tags`: JSON array of tags
- `created_at`, `updated_at`: Timestamps

Constraints:
- Confidence must be between 0 and 1
- Persona deletion cascades to beliefs

#### belief_edges
Represents relationships between beliefs in the graph.
- `id`: UUID primary key
- `persona_id`: Foreign key to personas
- `source_id`: Source belief node ID
- `target_id`: Target belief node ID
- `relation`: Type of relationship (supports, contradicts, depends_on, evidence_for)
- `weight`: Strength of relationship (0-1)
- `created_at`, `updated_at`: Timestamps

Constraints:
- Cascades on persona or node deletion

#### stance_versions
Tracks evolution of beliefs over time (version history).
- `id`: UUID primary key
- `persona_id`: Foreign key to personas
- `belief_id`: Foreign key to belief_nodes
- `text`: Stance text at this version
- `confidence`: Confidence at this version (0-1)
- `status`: Version status (current, deprecated, locked)
- `rationale`: Reason for this stance/change
- `created_at`, `updated_at`: Timestamps

Constraints:
- Confidence must be between 0 and 1
- Cascades on persona or belief deletion

#### evidence_links
Links evidence sources to beliefs.
- `id`: UUID primary key
- `persona_id`: Foreign key to personas
- `belief_id`: Foreign key to belief_nodes
- `source_type`: Type of source (reddit_comment, external_link, note)
- `source_ref`: Reference/URL to source
- `strength`: Evidence strength (weak, moderate, strong)
- `created_at`, `updated_at`: Timestamps

Constraints:
- Cascades on persona or belief deletion

#### interactions
Stores history of Reddit interactions (episodic memory).
- `id`: UUID primary key
- `persona_id`: Foreign key to personas
- `content`: Interaction content
- `interaction_type`: Type (post, comment, reply)
- `reddit_id`: Unique Reddit ID
- `subreddit`: Subreddit name
- `parent_id`: Parent post/comment ID (if reply)
- `metadata`: JSON metadata
- `embedding`: Vector embedding (BLOB) for semantic search
- `created_at`, `updated_at`: Timestamps

Constraints:
- reddit_id must be unique
- Cascades on persona deletion

#### belief_updates
Audit log for belief changes.
- `id`: UUID primary key
- `persona_id`: Foreign key to personas
- `belief_id`: Foreign key to belief_nodes
- `old_value`: Previous value (JSON)
- `new_value`: New value (JSON)
- `reason`: Reason for update
- `trigger_type`: What triggered update (auto, manual, evidence)
- `updated_by`: User who made update (for manual)
- `created_at`, `updated_at`: Timestamps

Constraints:
- Cascades on persona or belief deletion

#### pending_posts
Moderation queue for posts requiring review.
- `id`: UUID primary key
- `persona_id`: Foreign key to personas
- `content`: Draft content
- `post_type`: Type of post
- `target_subreddit`: Target subreddit
- `parent_id`: Parent post ID (if reply)
- `draft_metadata`: JSON metadata
- `status`: Review status (pending, approved, rejected)
- `reviewed_by`: Admin who reviewed
- `reviewed_at`: Review timestamp
- `created_at`, `updated_at`: Timestamps

Constraints:
- Cascades on persona deletion

#### agent_config
Per-persona configuration key-value store.
- `id`: UUID primary key
- `persona_id`: Foreign key to personas
- `config_key`: Configuration key
- `config_value`: Configuration value (JSON)
- `created_at`, `updated_at`: Timestamps

Constraints:
- Unique constraint on (persona_id, config_key)
- Cascades on persona deletion

#### admins
Dashboard authentication.
- `id`: UUID primary key
- `username`: Unique username
- `hashed_password`: Bcrypt hashed password
- `created_at`, `updated_at`: Timestamps

## SQLite Configuration

### WAL Mode
Write-Ahead Logging (WAL) is enabled for better concurrency:
```sql
PRAGMA journal_mode=WAL;
```

This is set automatically by the database initialization code in `app/core/database.py`.

### Connection Settings
- `check_same_thread`: False (required for async SQLite)
- Pool: StaticPool (optimal for single-file SQLite)

## Migration Commands

### Apply all pending migrations
```bash
alembic upgrade head
```

### Rollback one migration
```bash
alembic downgrade -1
```

### Rollback to specific migration
```bash
alembic downgrade <revision_id>
```

### Rollback all migrations
```bash
alembic downgrade base
```

### View current revision
```bash
alembic current
```

### View migration history
```bash
alembic history
```

### Create new migration (auto-generate)
```bash
alembic revision --autogenerate -m "Description of changes"
```

## Seeding Data

### Seed admin user
```bash
python scripts/seed_admin.py
```

Creates default admin user:
- Username: `admin`
- Password: `changeme123` (CHANGE IN PRODUCTION!)

### Seed default configuration
```bash
python scripts/seed_default_config.py
```

Creates demo persona with default configuration.

### Seed demo data (beliefs)
```bash
python scripts/seed_demo.py
```

Creates demo persona with 8 core beliefs and relationships for testing the belief graph.

## Testing Migrations

All migrations should be tested for:
1. **Upgrade**: Does the migration apply cleanly?
2. **Downgrade**: Does the rollback work correctly?
3. **Data integrity**: Are foreign keys enforced?
4. **Constraints**: Do check constraints work?

Test procedure:
```bash
# Start from base
alembic downgrade base

# Apply all migrations
alembic upgrade head

# Seed test data
python scripts/seed_demo.py

# Test rollback
alembic downgrade base

# Verify all tables removed (except alembic_version)
python -c "import sqlite3; conn = sqlite3.connect('data/reddit_agent.db'); cursor = conn.cursor(); cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"'); print([row[0] for row in cursor.fetchall()])"

# Re-apply migrations
alembic upgrade head

# Re-seed data
python scripts/seed_demo.py
```

## Migration Discipline

Following `docs/0_dev.md` database operation standards:

1. **Forward-only**: Never edit existing migrations that have been applied to any environment
2. **Transactional DDL**: Each migration runs in a transaction where supported
3. **Version control**: All migrations are committed to git
4. **Documentation**: Each migration includes a descriptive docstring
5. **Testing**: Test both upgrade and downgrade paths
6. **Cascading deletes**: Properly configured to maintain referential integrity
7. **Indices**: Created for all foreign keys and commonly queried columns

## Postgres Migration Path

While we use SQLite for MVP, the schema is designed to be Postgres-compatible:
- JSON columns use TEXT in SQLite, will map to JSONB in Postgres
- BLOB for embeddings will map to BYTEA
- TEXT timestamps will map to TIMESTAMPTZ
- VARCHAR limits are consistent with Postgres

Migration to Postgres will require:
1. Export data from SQLite
2. Update DATABASE_URL to postgres://...
3. Run `alembic upgrade head` (migrations are compatible)
4. Import data with type conversions

## Troubleshooting

### "The asyncio extension requires an async driver"
The DATABASE_URL must include the async driver: `sqlite+aiosqlite:///./data/reddit_agent.db`

### "pysqlite is not async"
Check that `aiosqlite` is installed: `pip install aiosqlite`

### Migrations fail to apply
1. Check alembic version: `alembic current`
2. Check database exists: `ls data/reddit_agent.db`
3. Check for schema drift: `alembic check`

### Cannot import app modules
Ensure you're running from the backend directory: `cd backend`

## Reference

- Alembic Documentation: https://alembic.sqlalchemy.org/
- SQLAlchemy Async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- aiosqlite: https://aiosqlite.omnilib.dev/
