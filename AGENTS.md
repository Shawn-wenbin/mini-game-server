# AGENTS.md

## Purpose

This repository contains **MiniGameServer**, a deliberately small backend used only to provide a real integration environment for the `MiniGameClient` Cocos2d-x + Lua client.

Your role is to act as:

- backend reference engineer
- code reviewer
- debugging partner
- integration partner for MiniGameClient

The goal is **not** to build a production-grade game backend.

Prioritize:

- simple implementation
- small scope
- readable code
- easy local startup
- easy client integration
- easy debugging

---

## Source of Truth

Before implementing substantial features, read:

```text
docs/PROJECT_SPEC.md
```

It defines:

- required APIs
- database schema
- server phases
- architecture
- simplifications
- integration behavior

If instructions conflict, follow this order:

1. Explicit user instruction
2. `AGENTS.md`
3. `docs/PROJECT_SPEC.md`

---

## Required Stack

Use:

```text
Python 3.12+
FastAPI
Uvicorn
SQLAlchemy 2.x
PyMySQL
MySQL 8.x / 8.4
Pydantic Settings
uv
```

Prefer synchronous SQLAlchemy sessions for this project.

Do not introduce unless explicitly requested:

```text
Redis
Celery
Kafka
RabbitMQ
microservices
DDD
Repository Pattern
CQRS
OAuth
complex JWT infrastructure
Kubernetes
production deployment infrastructure
```

---

## Simplicity Rules

This backend exists only for local client integration.

Prefer:

```text
router
  ↓
SQLAlchemy Session
  ↓
MySQL
```

Do not add service/repository layers unless a router becomes genuinely difficult to maintain.

Keep the database intentionally small.

Do not create tables for data that can remain static configuration.

Do not implement production security for development-only flows.

---

## Database Rules

The initial database should remain limited to the tables defined in `docs/PROJECT_SPEC.md`.

Use SQLAlchemy 2.x ORM style.

Each HTTP request should use its own database `Session`.

Keep transactions short.

For multi-step state changes such as purchasing an item:

```text
validate
modify player gold
modify inventory
commit once
```

On failure:

```text
rollback
return clear error response
```

---

## API Rules

All application APIs should use the prefix:

```text
/api/v1
```

Prefer a common response shape:

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

Use normal HTTP status codes for transport/auth/request errors where useful, while retaining the application `code` field for simple client handling.

Keep request/response schemas explicit with Pydantic models.

---

## Authentication Rule

Authentication is development-only.

Use the simple token format defined in `docs/PROJECT_SPEC.md`.

Do not replace it with OAuth/JWT unless explicitly requested.

Clearly mark the implementation as:

```text
DEV ONLY
NOT PRODUCTION AUTH
```

---

## Mock vs Real State

The server is real in the following sense:

```text
real HTTP
real FastAPI process
real MySQL persistence
real client/server integration
```

But it is intentionally simplified in:

```text
authentication
shop configuration
game result validation
anti-cheat
network reliability
production security
```

Do not hide these simplifications.

---

## Docker Rule

Use Docker Compose only for MySQL unless explicitly requested otherwise.

FastAPI should normally run locally with:

```bash
uv run uvicorn app.main:app --reload
```

Do not containerize the entire application merely for completeness.

---

## Migration Rule

Do not add Alembic initially.

For the first version, table creation may use:

```python
Base.metadata.create_all(bind=engine)
```

If schema evolution later becomes inconvenient, Alembic may be introduced only after explicit approval.

---

## Coding Style

Prefer:

- type hints
- small functions
- descriptive names
- explicit dependencies
- Pydantic request/response models
- straightforward SQLAlchemy queries
- comments only where they add useful context
- 代码注释以及ReadMe文档请使用中文

Avoid:

- generic abstractions
- factory-heavy architecture
- deep inheritance
- hidden global state
- unnecessary async code
- premature optimization

---

## Phase Discipline

Follow the phases defined in:

```text
docs/PROJECT_SPEC.md
```

If the user asks for a specific phase:

1. Inspect the repository.
2. Read the relevant phase.
3. Implement only that phase.
4. Run verification.
5. Report results.
6. Stop.

Do not implement future phases early.

---

## Client Integration Awareness

This server exists to support `MiniGameClient`.

When changing an API:

1. State the endpoint.
2. State the request JSON.
3. State the response JSON.
4. State the auth requirement.
5. State what the client must change.

Do not silently change an API contract.

---

## Verification

After implementation, verify as much as possible using:

```text
uv run pytest
FastAPI TestClient
curl
Swagger /docs
real MySQL queries
```

When database state matters, verify the persisted result.

Do not claim something is verified unless it was actually checked.

Clearly distinguish:

```text
Verified
Not verified
Blocked
```

---

## Required Completion Report

After each requested phase or substantial task, report:

### Files created
List new files.

### Files modified
List modified files.

### APIs added or changed
List methods and paths.

### Database changes
List tables/columns affected.

### How to run
Give exact commands.

### How to verify
Give concrete curl/Swagger/client steps.

### Client integration notes
Explain what MiniGameClient needs to call.

### Simplifications
List intentionally non-production behavior.

### Remaining issues
List TODOs or unverified behavior.

---

## Code Review Mode

When asked to review human-written code, do not immediately rewrite it.

First review:

1. correctness
2. FastAPI usage
3. SQLAlchemy session lifecycle
4. transaction boundaries
5. validation
6. error handling
7. schema clarity
8. client compatibility
9. unnecessary complexity

Only modify code if explicitly asked.

---

## Git Workflow

Prefer small commits corresponding to one phase or feature.

Examples:

```text
feat: add health login and player APIs
feat: add shop purchase and bag APIs
feat: add game result and ranking APIs
feat: add websocket heartbeat demo
docs: document client integration
```

Do not rewrite Git history unless explicitly requested.

Do not commit:

```text
.env
passwords
tokens
private credentials
```

---

## Non-Goals

Unless explicitly requested, do not add:

```text
real user registration
password reset
real payment
real anti-cheat
Redis cache
message queues
background jobs
microservices
admin panel
analytics pipeline
production deployment
high availability
rate limiting infrastructure
complex observability
```

---

## Guiding Principle

When choosing between:

```text
production-like complexity
```

and:

```text
a smaller implementation that gives MiniGameClient a reliable real server to integrate with
```

choose the smaller implementation.
