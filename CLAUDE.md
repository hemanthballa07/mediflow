# MediFlow — Claude Context

## What This Project Is
Hospital scheduling and lab report access platform. Production-grade FastAPI backend demonstrating: concurrency-safe booking (pessimistic locking), idempotent APIs, JWT refresh token rotation with family invalidation, keyset pagination, Redis cache-aside, full observability.

## Stack
- **Runtime:** Python 3.12, FastAPI, async SQLAlchemy
- **DB:** PostgreSQL (Alembic migrations)
- **Cache:** Redis (slot availability 30s TTL, report list 5m TTL)
- **Auth:** JWT access tokens (15min) + refresh token rotation with family invalidation
- **Observability:** Prometheus + Grafana (auto-provisioned)
- **Tests:** pytest
- **Load tests:** k6
- **Infra:** Docker Compose (everything runs locally, no cloud needed)

## Project Structure
```
app/
  api/v1/endpoints/   → auth, bookings, reports, admin
  core/               → config, security, metrics, logging
  db/                 → session (async SQLAlchemy), redis
  middleware/         → metrics (HTTP latency + request count)
  models/models.py    → all 7 SQLAlchemy models
  schemas/schemas.py  → all Pydantic schemas
  services/           → auth, booking, reports, audit (business logic lives here)
  main.py             → FastAPI app, lifespan, middleware
migrations/versions/  → Alembic migrations (001_initial.py has all tables + triggers)
k6/scripts/           → benchmark.js, contention_test.js
deploy/               → Prometheus + Grafana config
tests/test_core.py    → unit tests
scripts/seed.py       → dev seed data
```

## Key Conventions
- Business logic in `services/`, endpoints only parse/validate/delegate
- Never use raw SQL — always SQLAlchemy ORM (except Alembic migrations)
- All logs are structured JSON
- Admin API protected by `X-Admin-Api-Key` header
- Idempotency-Key required for POST /bookings

## Commands
```bash
make up             # start all services
make migrate        # run Alembic migrations
make seed           # seed test data
make test           # pytest
make benchmark      # k6 full suite
make contention-test SLOT_ID=<id> TOKEN=<token>
make logs           # follow API logs
make clean          # stop + remove volumes
```

## Seeded Credentials
| Role    | Email                  | Password   |
|---------|------------------------|------------|
| Admin   | admin@mediflow.dev     | admin123   |
| Doctor  | doctor@mediflow.dev    | doctor123  |
| Patient | patient@mediflow.dev   | patient123 |

## Source of Truth Files
- `CLAUDE.md` — project context for Claude (this file)
- `PROGRESS.md` — living log of what's done, in progress, and todo

## Rules for Claude
- After EVERY change (code, config, docs), update `PROGRESS.md`
- Log what changed, why, and what's next
- Never leave `PROGRESS.md` stale after a task
