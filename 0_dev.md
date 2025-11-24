# Engineering Quality Guidelines

This document sets the expectations for engineering quality across the stack. It replaces the earlier training-style roadmap with pragmatic standards, quality bars, and delivery guardrails that experienced developers can apply immediately. Each section clarifies the intent behind the practice, the behaviours that produce high quality outcomes, and the failure signals that indicate corrective action is needed. Nothing here is meant to be aspirational theory-treat it as the minimum viable professionalism for shipping resilient products.

---

## Quality Baselines (3-6 Months)

### Frontend Quality

#### Component Frameworks (React/Vue)
- **Quality objective**: Maintain predictable, testable UI surfaces by keeping state local to components and wiring data flows explicitly.
- **Standards**:
  - Structure features as composable components with clear props/state contracts; avoid monolith components that reach across the tree.
  - Encapsulate state changes through framework primitives (hooks, composables, stores) instead of direct DOM manipulation.
  - Always define default rendering states and loading/error placeholders to prevent layout jumps.
- **Verification**:
  - Lint for missing keys in lists and unstable dependencies in effects/computeds.
  - Snapshot or visual regression coverage for critical UX paths.
- **Failure signals**: cross-component state coupling, UI flicker caused by uncontrolled async updates, or logic patched into lifecycle callbacks instead of proper abstractions.

#### Responsive UX
- **Quality objective**: Ship a single codebase that behaves flawlessly on any viewport, input modality, or pixel density.
- **Standards**:
  - Design mobile-first breakpoints with fluid spacing (rem, %) and avoid hard-coded pixel widths.
  - Validate touch target sizing (minimum 44px square) and ensure keyboard navigation parity.
  - Performance budget of <100KB critical CSS and consistent typography scale across breakpoints.
- **Verification**:
  - Automated visual checks across representative device profiles.
  - Manual audits with device emulators and screen readers.
- **Failure signals**: layout collapse on uncommon aspect ratios, overflow scrollbars caused by fixed elements, or degraded input affordances on touch.

### Backend Quality

#### RESTful API Contracts
- **Quality objective**: Expose durable, evolvable API surfaces with precise semantics and discoverability.
- **Standards**:
  - Enforce resource-oriented URIs, explicit versioning, and idempotent HTTP verb usage.
  - Return structured errors (problem+json or equivalent) with actionable messages and correlation IDs.
  - Document contracts via OpenAPI and publish change logs before breaking updates.
- **Verification**:
  - Contract tests between services and consumer schema validation.
  - Monitoring for verb misuse (e.g., non-idempotent GET) in access logs.
- **Failure signals**: undocumented behaviour changes, consumer workarounds, or coupling to underlying database schema.

#### Resilient Error Handling
- **Quality objective**: Degrade gracefully while preserving debuggability and user trust.
- **Standards**:
  - Separate technical exceptions from domain errors and translate them to domain-aware responses.
  - Surface user-facing errors that describe impact and next steps; keep stack traces for logs only.
  - Correlate log entries with request IDs and propagate them through async flows.
- **Verification**:
  - Chaos drills for dependent services (timeouts, partial failures).
  - Alerting on error-rate thresholds with root-cause annotations.
- **Failure signals**: 500 spikes with no diagnostics, inconsistent error formats, or silent data corruption.

#### Data Validation Discipline
- **Quality objective**: Reject bad input before it pollutes state or propagates downstream.
- **Standards**:
  - Validate at both API boundary and domain layer; never trust client-side checks alone.
  - Centralize validation schemas and reuse them for docs, tests, and runtime guards.
  - Sanitize third-party payloads and enforce rate-limited retries to avoid poisoning queues.
- **Verification**:
  - Contract tests that assert validation failure behaviour.
  - Metrics per validation rule to detect drift or unexpected user behaviour.
- **Failure signals**: runtime crashes from unvalidated fields, security incidents from unchecked input, or divergent validation logic across layers.

### Data Foundation Quality

#### PostgreSQL Operations
- **Quality objective**: Run PostgreSQL with production-grade reliability and performance by default.
- **Standards**:
  - Configure connection pooling and connection limit guards; monitor wait events.
  - Enforce WAL archiving and automated point-in-time recovery testing.
  - Use environment-specific parameter templates (shared_buffers, work_mem) with infra-as-code parity.
- **Verification**:
  - Periodic failover rehearsals and backup restore drills.
  - Query plans captured for top N endpoints.
- **Failure signals**: reliance on SQLite in production, missing backups, or connection storms during deploys.

#### Relational Modeling
- **Quality objective**: Preserve domain integrity through explicit relationships and constraints.
- **Standards**:
  - Model relationships with foreign keys and cascading rules aligned to business logic.
  - Document cardinality and ownership semantics within the data dictionary.
  - Validate referential quality during migrations and data imports.
- **Verification**:
  - Schema linting for orphan tables or missing constraints.
  - Data quality dashboards highlighting orphaned records.
- **Failure signals**: manual cleanup scripts, inconsistent joins across services, or unbounded denormalization.

#### Schema Migration Discipline
- **Quality objective**: Ship schema changes without downtime or data loss.
- **Standards**:
  - Version migrations, forward-only; apply in CI before merging.
  - Use transactional DDL when available and gate long-running migrations behind feature flags.
  - Coordinate backfills with throttled jobs and observability for lock contention.
- **Verification**:
  - Dry-run migrations against production snapshots.
  - Automated rollback plans documented for each release.
- **Failure signals**: hotfixes on live databases, manual SQL patching, or migrations that cannot be replayed.

### Delivery & Operations Quality

#### Clean Git Workflow
- **Quality objective**: Keep history comprehensible and auditable.
- **Standards**:
  - Branch naming tied to work item IDs; commit messages describe intent and impact.
  - Rebase locally before merge to maintain linear history; avoid merge commits in feature branches.
  - Enforce reviewers with domain expertise and documented decision outcomes.
- **Verification**:
  - Pre-merge checks for lint/tests and diff size budgets.
  - Retrospectives on revert frequency or hotfix volume.
- **Failure signals**: unreviewed merges, tangled commits, or branch divergence causing redeploys.

#### Unit Testing Baseline
- **Quality objective**: Secure behaviour with fast, deterministic feedback.
- **Standards**:
  - Cover pure logic with unit tests and isolate side effects behind mocks/fakes.
  - Enforce coverage thresholds per critical module (minimum 80% where measurable) and mutation testing for core algorithms.
  - Structure tests following AAA (Arrange, Act, Assert) and keep fixtures explicit.
- **Verification**:
  - CI gating on test flakiness and runtime budgets.
  - Periodic review of flaky test quarantine lists.
- **Failure signals**: regressions caught in production, brittle mocks, or tests that double as documentation but fail to assert behaviour.

#### Container Hygiene (Docker Fundamentals)
- **Quality objective**: Deliver portable builds with secure, reproducible environments.
- **Standards**:
  - Use minimal base images, pin versions, and multi-stage builds to strip tooling from runtime images.
- **Verification**:
  - CVE scanning integrated into CI.
  - Runtime probes validating container health/readiness.
- **Failure signals**: snowflake environments, 1GB+ images, or secrets baked into layers.

### Architecture Fundamentals

#### MVC Discipline
- **Quality objective**: Maintain separation between presentation, domain, and persistence layers.
- **Standards**:
  - Keep controllers thin; move domain logic into services/use cases.
  - Design views/templates as pure renderers with no business decisions.
- **Failure signals**: fat controllers, models accessing HTTP context directly, or cross-layer cyclic dependencies.

#### Separation of Responsibilities
- **Quality objective**: Reduce coupling and maximise reuse.
- **Standards**:
  - Define boundaries with explicit interfaces; enforce dependency injection.
  - Make modules single-purpose and observable (metrics, logs) at their boundary.
- **Failure signals**: hidden side effects, modules that need to know internal state of peers, or features requiring edits across unrelated packages.

---

## Quality Depth (6-12 Months)

### Frontend Quality Depth

#### State Management (Redux, Pinia, Zustand, etc.)
- **Quality objective**: Keep global state predictable, observable, and minimal.
- **Standards**:
  - Model state domains explicitly with typed selectors and memoized derivations.
  - Co-locate async data fetching logic with domain modules; avoid component-level duplication.
  - Instrument state transitions with devtools and production logging (feature-flaggable).
- **Failure signals**: cascading re-renders, state duplication, or debug logs injected directly into UI code.

#### Performance Optimization
- **Quality objective**: Maintain sub-100ms interactions through proactive performance design.
- **Standards**:
  - Establish budgets for bundle size, render time, and input latency.
  - Apply code splitting, memoization, virtualization, and prefetching where metrics show impact.
- **Verification**:
  - Lighthouse/ Web Vitals tracked per release.
- **Failure signals**: user-reported sluggishness, unbounded event listeners, or blocking synchronous work on the main thread.

### Backend Quality Depth

#### Microservice Architecture Governance
- **Quality objective**: Ensure independent deployability without sacrificing observability or reliability.
- **Standards**:
  - Define service contracts with backward-compatible evolution paths.
  - Implement circuit breakers, retries with jitter, and bulkhead isolation.
  - Document service dependency graphs and recovery plans.
- **Failure signals**: cascading failures, ambiguous ownership, or manual deployment coordination.

#### Application Security (JWT, HTTPS, Secrets)
- **Quality objective**: Enforce least privilege and data protection across all surfaces.
- **Standards**:
  - Rotate signing keys, store secrets in vaults, and pin TLS versions/ciphers.
  - Implement secure default headers (CSP, HSTS) and audit logging for auth flows.
- **Verification**:
  - Pen tests, automated dependency scanning, and threat models per feature.
- **Failure signals**: tokens without expiry, mixed-content warnings, or secrets in repos.

### Data Quality Depth

#### Query Optimization
- **Quality objective**: Deliver consistent latency under load without over-provisioning.
- **Standards**:
  - Profile query plans, eliminate N+1 patterns, and push computation to the database when cheaper.
  - Materialize aggregates with refresh policies when it reduces load.
- **Failure signals**: 95th percentile latency regressions, runaway temp files, or ad hoc SQL patched into services.

#### Indexing Strategy
- **Quality objective**: Balance read/write performance and storage.
- **Standards**:
  - Design composite indexes for dominant access patterns; drop unused indexes proactively.
  - Monitor bloat, vacuum schedules, and dead tuples.
- **Failure signals**: slow scans, blocked writers, or index explosion with no ownership.

### Delivery Quality Depth

#### CI/CD Pipelines
- **Quality objective**: Ship multiple times per day without regressions.
- **Standards**:
  - Pipeline stages: lint -> unit -> integration -> security scan -> deploy -> smoke test.
  - Blue/green or canary deployments with automated rollback triggers.
  - Immutable artifacts promoted through environments.
- **Failure signals**: manual hotfixes, long-lived release branches, or broken builds ignored for >1h.

#### Observability (Logs, Metrics, Traces)
- **Quality objective**: Detect, diagnose, and resolve incidents before users notice.
- **Standards**:
  - Structured logs with correlation IDs; 90-day retention for audit-critical data.
  - Service-level indicators (SLI) and error budgets tracked per product surface.
  - Distributed tracing for every async boundary.
- **Failure signals**: blind spots during incidents, inconsistent alert thresholds, or dashboards without owners.

### Architecture Quality Depth

#### Design Patterns in Practice
- **Quality objective**: Apply patterns to simplify complexity, not increase it.
- **Standards**:
  - Document intent when adopting a pattern (Factory, Strategy, CQRS, etc.).
  - Avoid pattern proliferation; enforce reviews to retire misused patterns.
- **Failure signals**: patterns referenced as buzzwords, duplicated implementations, or over-engineered solutions for simple problems.

#### Clean Code Systemically
- **Quality objective**: Optimize for readability, alignment with domain language, and change resilience.
- **Standards**:
  - Keep functions short, side-effect free where possible, and named after business behaviour.
  - Enforce static analysis and formatting; treat warnings as failures.
- **Failure signals**: code commentating itself, dead code accumulation, or inconsistent naming across modules.

#### Documentation with Purpose
- **Quality objective**: Ensure documentation accelerates onboarding and decision-making.
- **Standards**:
  - Maintain architecture decision records (ADR) and runbooks.
  - Keep diagrams version-controlled; update when interfaces change.
  - Document invariants, not implementation trivia.
- **Failure signals**: stale docs, undocumented emergent behaviour, or dependencies on institutional memory.

---

## Quality Excellence (12+ Months)

### Frontend Quality Excellence

#### Micro-frontends and SSR/SSG
- **Quality objective**: Deliver large-scale interfaces with independent deployability and fast time-to-first-byte.
- **Standards**:
  - Define contracts (events, shared dependencies) between micro-frontends; isolate styles.
  - Use server-side rendering or static generation to meet SEO/performance budgets.
- **Failure signals**: bundle duplication across teams, hydration mismatches, or deployment coupling.

#### Accessibility Leadership
- **Quality objective**: Exceed WCAG AA by default and treat accessibility as a core feature.
- **Standards**:
  - Automated a11y tests (axe, pa11y) in CI; manual screen reader QA per release.
  - Semantic HTML, ARIA only when necessary, and consistent focus management.
- **Failure signals**: reported blockers from assistive tech users, inaccessible custom components, or no alt text policy.

### Backend Quality Excellence

#### Scalability Engineering
- **Quality objective**: Meet SLOs under peak and failover scenarios.
- **Standards**:
  - Performance budgets per endpoint; load testing with production-like environments.
  - Capacity planning and chaos engineering integrated into quarterly rituals.
- **Failure signals**: scaling via manual server additions, missing horizontal scaling strategy, or no autoscaling guardrails.

#### Distributed Cache Stewardship
- **Quality objective**: Accelerate read paths without compromising correctness.
- **Standards**:
  - Define cache ownership, TTL strategy, and invalidation events.
  - Monitor hit/miss ratios, replication lag, and eviction patterns.
- **Failure signals**: stale data incidents, thundering herds, or cache treated as database of record.

#### Message Queue Design
- **Quality objective**: Build resilient asynchronous workflows.
- **Standards**:
  - Contract-first event design with schema evolution workflows.
  - Handle poison messages via dead-letter queues and alerting.
- **Failure signals**: lost messages, unbounded retries, or queues without replay capability.

### Data Quality Excellence

#### Sharding Strategy
- **Quality objective**: Scale horizontally while protecting consistency.
- **Standards**:
  - Choose shard keys aligned with access patterns; avoid hotspots.
  - Implement resharding playbooks and unique ID generators.
- **Failure signals**: manual shard balancing, cross-shard transactions without safeguards, or data skew.

#### Replication Topologies
- **Quality objective**: Ensure read scalability and failover readiness.
- **Standards**:
  - Monitor replication lag; enforce read-only replicas.
  - Test failover routinely and document promotion procedures.
- **Failure signals**: replicas drifting silently, applications writing to replicas, or untested failovers.

#### Backup and Recovery Strategy
- **Quality objective**: Guarantee recoverability within RPO/RTO targets.
- **Standards**:
  - Automate full, incremental, and off-site backups.
  - Practice restore drills quarterly and document time to recover.
- **Failure signals**: backups unverified, encryption ignored, or no isolation between backup and primary accounts.

### Delivery Quality Excellence

#### Kubernetes Operations
- **Quality objective**: Treat clusters as cattle with observable, self-healing workloads.
- **Standards**:
  - Declarative manifests, health probes, resource quotas, and PodSecurity standards.
  - Automated cluster upgrades with canaries.
- **Failure signals**: pets clusters, manual kubectl patching, or no RBAC governance.

#### Infrastructure as Code
- **Quality objective**: Version, review, and reproduce every infrastructure change.
- **Standards**:
  - Keep Terraform/ Pulumi stacks free of drift; run plan checks in CI.
  - Separate state per environment with secure backends and policy-as-code.
- **Failure signals**: click-ops changes, missing rollbacks, or secrets embedded in templates.

### Architecture & Leadership Excellence

#### Systems Architecture Stewardship
- **Quality objective**: Align architecture with evolving business strategy while controlling complexity.
- **Standards**:
  - Maintain living architecture maps with domain boundaries, data flows, and quality attributes.
  - Evaluate trade-offs explicitly (availability vs consistency, build vs buy).
- **Failure signals**: architectural drift, duplicated systems, or undocumented critical paths.

#### Mentoring and Team Enablement
- **Quality objective**: Multiply team effectiveness through coaching and structured knowledge sharing.
- **Standards**:
  - Mentor plans with measurable outcomes; pair on complex reviews.
  - Build onboarding curricula, brown-bag sessions, and guilds around core capabilities.
- **Failure signals**: single points of failure, uneven code quality across squads, or lack of successors.

---

## Quality Activation Roadmap

### Weeks 1-2: Flask Advanced Platform Hardening
- Establish production-grade Flask baseline: application factory, blueprints, dependency injection.
- Harden security upfront: CSRF, rate limiting, structured logging, and secret management.
- Define API contracts with OpenAPI, generate clients, and add smoke tests in CI.

### Weeks 3-5: Data Platform Excellence
- Design schemas with peer review, implement migrations, and rehearse rollback scenarios.
- Set up connection pooling, monitoring (pg_stat_statements, logs), and data retention policies.
- Build analytics-ready exports or materialized views aligned with business KPIs.

### Weeks 6-7: Testing & Reliability Reinforcement
- Expand coverage to integration, contract, and end-to-end tests; automate environment provisioning.
- Implement quality gates: mutation testing, fuzzing for critical inputs, and chaos drills.
- Establish incident response runbooks and PagerDuty/alert routing with agreed SLOs.

---

## Quality Metrics and Feedback Loops

- **Code health**: cyclomatic complexity trends, review turnaround time, mutation score, and refactoring cadence.
- **Process reliability**: deployment frequency, change failure rate, mean time to detection (MTTD), and rollback frequency.
- **Product performance**: core Web Vitals, API p95 latency, error budget burn rate, and customer satisfaction (NPS, CES).
- **Learning velocity**: experiment cycle time, hypothesis validation rate, and discovery-to-delivery ratio.
- **Operational readiness**: incident response time, on-call load distribution, and recovery drill success.

Instrument these metrics in a single quality dashboard. Act on trends-not just absolute thresholds-and align them with quarterly objectives.

---

## Reflections and Decisions

- Maintain a running log of architectural decisions (ADR) with context, options discarded, and review cadence.
- Capture qualitative learnings from incidents, experiments, and user feedback; translate them into backlog items or playbooks.
- Review quality posture monthly: what degraded, what improved, and what trade-offs were accepted intentionally.

---

## Methodological Playbooks

### Interface-First Design
- Define contracts before implementation. Collaborate with stakeholders to describe interfaces, expected behaviours, and failure modes.
- Use interface definitions to unblock parallel work, create mocks, and validate assumptions early.

#### Step 1: Cement the Contract
- Draft API/interface specs using OpenAPI/TypeScript interfaces/Protobuf.
- Include success, failure, idempotency, and versioning details.
- Validate contracts through consumer-driven tests before coding internals.

#### Step 2: Adapt Existing Systems
- Evaluate current architecture for compatibility; identify seams and integration points.
- Introduce adapters that translate new interfaces to legacy behaviour without side effects.

#### Step 3: Implement to the Contract
- Start with the smallest functional slice; implement business logic against contract mocks.
- Instrument implementation from day one (metrics, logs) to confirm contract adherence.

#### Step 4: Assemble via Dependency Injection
- Wire components through dependency injection or service locators.
- Keep composition roots explicit and unit-test wiring logic.

### Temporal Universe Pattern
- Treat time-evolving systems as universes transitioning between states.
- Model explicit state transitions, invariants, and audit trails.
- Provide simulation or dry-run modes to verify transitions before they reach production.

---

## Project Inception Foundations

### Phase 0: Indestructible Foundations (Week 1)
- **Day 1 - Architecture Decision Record**: Create `docs/decisions/ADR-001-tech-stack.md` capturing stack rationale, constraints, and exit criteria.
- **Day 2 - Project Structure**: Scaffold backend/frontend/docs directories with opinionated defaults, enforce linting, formatting, and tooling parity.
- **Day 3 - Configuration & Secrets**: Centralize configuration (`backend/app/core/config.py`), define `.env.example`, and set up secret management workflows.
- **Day 4 - Database & Migrations**: Establish base models (`backend/app/models/base.py`), connection utils, and migration tooling with sample migration.
- **Day 5 - Docker & Environment Setup**: Produce `docker-compose.yml`, base Dockerfiles, health checks, and onboarding docs for new engineers.

### Phase 1: MVP Core Services (Weeks 2-4)
- Implement services in a deliberate order to maximise learning and reduce rework:
  1. **Auth Service** - foundational security, token lifecycle, role model.
  2. **Health Checks** - system observability and deployment readiness.
  3. **Data Service** - domain models, repositories, and first migrations.
  4. **Universe Service** - domain orchestration built on data service.
  5. **Strategy Service** - encapsulate business logic with quality gates.
  6. **Execution Service** - final layer invoking downstream integrations.
- After each service, run contract/integration tests and update runbooks.

### Feature Prioritisation Framework
- Apply RICE (Reach, Impact, Confidence, Effort) scoring with engineering review.
- Maintain a prioritisation board with thresholds for moving features up/down.

### Feature Delivery Template
```
Feature: <Name>
1. Analysis (Monday): requirements, dependencies, risks, quality metrics.
2. Design (Tuesday): sequence diagrams, contract updates, architecture review.
3. Implementation (Wed-Thu): development, unit/integration tests, documentation.
4. Integration (Friday): environment rollout, observability checks, user validation.
5. Deployment (Following Monday): staged release, monitoring, post-deploy review.
```

### Priority Change Signals
- **Stop immediately** when quality regression threatens users, critical dependency fails, or security exposure discovered.
- **Reevaluate** when scope doubles, customer sentiment shifts, or new market opportunity emerges.
- **Continue** when quality signal is green, timelines hold, and no higher-leverage work arose.

### First Concrete Action
```
mkdir bubble-platform
cd bubble-platform
mkdir -p backend/app/{core,api/v1,services,models,tests}
mkdir frontend docs
touch backend/app/core/config.py backend/requirements.txt docker-compose.yml .env.example
git init && git add . && git commit -m "Initial project structure"
```
This starter workflow guarantees reproducible setup, audit trail, and clarity about next quality steps.

---

## Operational Case Study: Remote MCP Deployment (2025-10-11)

### Outcome
- Remote MCP server reachable from external Claude Desktop clients with full toolset availability (16 tools).
- Deployment hardened on production node `209.38.99.115` with documented access workflows.

### Deployment Quality
- Installed dependencies (`fastmcp==0.2.0`, `anthropic==0.40.0`, `sse-starlette`) and validated services via curl both locally and remotely.
- Service managed by systemd (`uncle-stock-api.service`) with clear branch (`agent`) and environment layout.

### Configuration Assets
- `backend/CLAUDE_DESKTOP_REMOTE_CONFIG.md`: remote setup instructions.
- `backend/claude_desktop_config_REMOTE.json`: reference configuration.
- Documentation updated in `CLAUDE.md` covering tool taxonomy, modes (STDIO, HTTP), production details, and known issues.

### Validation & Observability
- Tool list latency ~80 ms; execution latency 150-300 ms; local STDIO latency <10 ms.
- Remote HTTP endpoints validated; SSE endpoint noted as known limitation (uvicorn recursion) with mitigation strategy (use POST endpoints).

### Security & Risk Posture
- Current gaps: HTTP-only transport, basic rate limiting, no authentication.
- Phase 8 action items: add OAuth/API keys, HTTPS via Let's Encrypt, rate limiting, metrics/monitoring, and directory submission.

### Rollback Plan
```
ssh root@209.38.99.115
cd /home/uncle-stock/uncle-stock-system
git checkout main
sudo systemctl restart uncle-stock-api
```

### Lessons for Quality Practice
- Deployments must ship with rollback scripts, observability hooks, and clear ownership.
- Known issues are acceptable when documented, monitored, and scheduled for resolution with explicit accountability.
*** End Patch***/
