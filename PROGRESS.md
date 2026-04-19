# MediFlow — Progress Log

Living source of truth. Updated after every change — big or small.

---

## Status Legend
- ✅ Done
- 🔄 In Progress
- ⏳ Todo
- ❌ Blocked

---

## Completed

### 2026-04-18
- ✅ **Initial project built** — Full FastAPI backend with PostgreSQL, Redis, Alembic, Docker Compose
- ✅ **Auth service** — JWT access tokens (15min TTL), refresh token rotation, family invalidation on reuse detection
- ✅ **Booking service** — `SELECT FOR UPDATE SKIP LOCKED`, idempotency key table, Redis cache invalidation on booking
- ✅ **Reports service** — Keyset pagination, Redis cache-aside (5m TTL, first page only)
- ✅ **Admin endpoints** — Audit log (append-only trigger), slot management
- ✅ **Observability** — Prometheus metrics, Grafana dashboard (auto-provisioned), structured JSON logging
- ✅ **k6 load tests** — benchmark.js (full suite), contention_test.js (50-VU slot contention)
- ✅ **Git initialized** — Repo pushed to https://github.com/hemanthballa07/mediflow.git
- ✅ **`.gitignore` created** — Python, venv, .env, pycache, macOS, IDE patterns
- ✅ **`CLAUDE.md` created** — Project context, conventions, commands for Claude sessions
- ✅ **`PROGRESS.md` created** — This file; living log of all changes
- ✅ **Security review** — 6 critical, 7 high, 8 medium, 4 low issues identified
- ✅ **Python review** — 1 critical, 7 high, 8 medium, 4 low issues identified
- ✅ **Phase F: admin slot pagination** (2026-04-18):
  - `app/api/v1/endpoints/admin.py`: added `after_date: date | None` keyset cursor to `list_slots` — `WHERE date > after_date ORDER BY date, start_time LIMIT n`; caller uses last item's date as next cursor; `get_audit_log` already had `after_id` keyset pagination, no change needed
  - 24/24 tests pass
- ✅ **Phase E: Docker migration automation** (2026-04-18):
  - `docker-compose.yml`: added `migrator` one-shot service (`alembic upgrade head`, `restart: no`); `api` now `depends_on: migrator: condition: service_completed_successfully` — API never starts if migrations fail
  - `docker compose config` validates clean (pre-existing `version` obsolete warning only)
  - **Follow-up:** Phase F (admin pagination), G (features) remain
- ✅ **Phases A–D: health endpoint, config cleanup, slot validation, test expansion** (2026-04-18):
  - `app/schemas/schemas.py`: added `HealthResponse` model
  - `app/main.py`: upgraded `/health` stub to real DB (`SELECT 1`) + Redis (`PING`) checks; 200 healthy / 503 unhealthy; `response_model`
  - `app/core/config.py`: added `REPORT_CACHE_TTL: int = 300`
  - `app/services/reports.py`: replaced hardcoded `300` with `settings.REPORT_CACHE_TTL`
  - `app/api/v1/endpoints/admin.py`: slot creation rejects `end_time <= start_time` and past dates with 422; fixed deprecated `HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT`
  - `tests/test_core.py`: 11 new tests — health 200/503, slot validation, report TTL config, auth failures, booking cancellation (own/other/already-cancelled)
  - Tests: 13 → 24 passing
  - **Follow-up:** Phase E (migration automation), F (admin pagination), G (features) remain
- ✅ **Block F: python-jose → PyJWT migration** (2026-04-18):
  - `requirements.txt`: replaced `python-jose[cryptography]==3.3.0` with `PyJWT==2.10.0` — eliminates known CVEs (GHSA-cjwg-qfpm-7377, alg confusion)
  - `app/core/security.py`: `from jose import JWTError, jwt` → `import jwt; from jwt.exceptions import InvalidTokenError`; updated docstring
  - `app/api/v1/deps.py`: `from jose import JWTError` → `from jwt.exceptions import InvalidTokenError`; `except JWTError` → `except InvalidTokenError`
  - PyJWT 2.x `encode`/`decode` API identical to python-jose for HS256; no behavior change
  - All 13 tests pass
  - **Follow-up risks**: `python-jose` still in venv until Docker rebuild; Docker image needs `pip install` with updated `requirements.txt`; slowapi deprecation warning remains (unrelated)
- ✅ **Block E: pydantic-settings v2 migration + mock fix** (2026-04-18):
  - `app/core/config.py`: replaced deprecated `class Config: env_file = ".env"` with `model_config = SettingsConfigDict(env_file=".env")` — eliminates pydantic-settings deprecation warning
  - `tests/test_core.py`: added `mock_db.add = MagicMock()` in `test_token_reuse_detection_revokes_family` — `db.add()` is sync; `AsyncMock` auto-creating it caused "coroutine never awaited" warning
  - `app/core/security.py`: verified `decode_access_token` uses `algorithms=[settings.JWT_ALGORITHM]` (list) — `python-jose` alg:none attack blocked; no change needed
  - All 13 tests pass, 3 warnings remain (slowapi `asyncio.iscoroutinefunction` — unrelated to Block E)
  - **Follow-up risks**: `python-jose` has known CVEs (alg confusion, GHSA-cjwg-qfpm-7377) — consider migrating to `PyJWT`; slowapi `asyncio.iscoroutinefunction` deprecated in Python 3.16 — upgrade slowapi before then
- ✅ **Block D: test suite green + 3 new tests** (2026-04-18):
  - Fixed local env blockers: `bcrypt==3.2.2` (passlib 1.7.4 incompatible with bcrypt 4.x), `sqlalchemy>=2.0.40` (2.0.36 broke on Python 3.14 `Union.__getitem__`), `requirements.txt` otel pins corrected (`1.28.4`→`1.28.0`, `0.49b4`→`0.49b0`)
  - All 13 tests pass (`pytest tests/ -v`): 10 pre-existing + 3 new
  - `tests/test_core.py`: added `test_get_available_slots_passes_string_date`, `test_register_rate_limit_enforced`, `test_report_page_next_cursor_defaults_none`
  - **Follow-up risks**: venv uses bcrypt 3.2.2 + SQLAlchemy 2.0.49 while `requirements.txt` pins 4.0.1 + 2.0.36 — Docker (Python 3.12) unaffected; update production pins only after Docker build validated. Two warnings: `audit.py:24` `db.add` unawaited in mock tests (cosmetic); slowapi uses deprecated `asyncio.iscoroutinefunction` (removed Python 3.16 — upgrade slowapi then)
- ✅ **Block C: rate limiting + date cast fix** (2026-04-18):
  - `requirements.txt`: added `slowapi==0.1.9`
  - `app/core/limiter.py`: created — `Limiter` instance backed by Redis (`REDIS_URL`)
  - `app/main.py`: wired `app.state.limiter`, registered `RateLimitExceeded` → JSON 429 handler
  - `app/api/v1/endpoints/auth.py`: `@limiter.limit` on register (10/min), login (5/min), refresh (20/min); added `request: Request` param
  - `app/api/v1/endpoints/bookings.py`: `str(date)` cast before passing to `get_available_slots`
  - **Follow-up risks**: run `pip install slowapi==0.1.9` or rebuild Docker image before testing; rate limit counts are per-IP so behind a proxy/load balancer you need `X-Forwarded-For` trust config; `limiter.py` calls `get_settings()` at import time — `conftest.py` env vars cover tests
- ✅ **Block B remaining fixes** (2026-04-18):
  - `.env.example` created — documents all required env vars with placeholder values
  - `main.py`: CORS `allow_origins` restricted from `["*"]` to `["http://localhost:3000"]`
  - `models/models.py`: all 8 `datetime.utcnow` → `lambda: datetime.now(timezone.utc)`; added `timezone` import
  - `endpoints/bookings.py`: `date: str` → `date: date` with `from datetime import date`
  - `schemas/schemas.py`: `ReportPage.next_cursor` now has `= None` default
  - `tests/conftest.py` created — sets required env vars before pytest imports app modules
  - **Follow-up risks**: `BookingService.get_available_slots` may still expect `str` for date — verify it handles `datetime.date`; CORS origin list hardcoded, update when frontend URL known
- ✅ **Block B security fixes** (2026-04-18):
  - `config.py`: `DATABASE_URL`, `JWT_SECRET`, `ADMIN_API_KEY` — removed all hardcoded defaults; now required env vars (startup fails if missing)
  - `config.py`: added `@model_validator` — asserts `len(JWT_SECRET) >= 32` and `len(ADMIN_API_KEY) >= 32` at startup
  - `admin.py`: `verify_admin_key` — replaced `!=` with `hmac.compare_digest` (eliminates timing side-channel)
  - **Follow-up risks**: `.env` must be set before running; tests that instantiate `Settings()` without env vars will break — check test fixtures
- ✅ **Block A security fixes** (2026-04-18):
  - `schemas.py`: `RegisterRequest.role` → `Literal["patient", "doctor"]`; admin self-registration impossible
  - `endpoints/reports.py`: `list_reports` enforces ownership — patients get 403 on other patient's `patient_id`
  - `deps.py`: deleted broken `get_admin_user()` (returned `Depends()` object, never ran role check; zero callers)
  - `tests/test_core.py`: 4 new tests covering all 3 fixes

---

- ✅ **Phase G.2: Per-user booking rate limit** (2026-04-18):
  - `app/core/limiter.py`: added `get_user_id_from_request` key function — decodes JWT Bearer token, extracts `sub` (user UUID); falls back to IP on failure
  - `app/api/v1/endpoints/bookings.py`: `@limiter.limit("10/hour", key_func=get_user_id_from_request)` on `create_booking`; added `request: Request` first param (required by slowapi)
  - 24/24 tests pass
- ✅ **Phase G.1: Booking cancellation window** (2026-04-18):
  - `app/core/config.py`: added `CANCELLATION_WINDOW_HOURS: int = 24`
  - `app/services/booking.py`: `cancel_booking` loads slot before cancellation; combines `slot.date + slot.start_time` → UTC datetime; rejects 409 if `now >= appointment_dt - 24h`; slot reused for cache invalidation (no extra query)
  - `tests/test_core.py`: fixed `test_cancel_booking_own_succeeds` — added `date`/`time` imports, proper typed slot fields, corrected `execute` side_effect order
  - 24/24 tests pass

## In Progress

---

## Todo

- ⏳ **Commit all Block A–F changes** — 12 files modified, uncommitted
- ⏳ **slowapi deprecation** — `asyncio.iscoroutinefunction` removed in Python 3.16; upgrade slowapi when compatible version available
- ⏳ **Expand test coverage** — auth rate limiting, slot date validation, report pagination edge cases

---

## How to Use This File

After every task, add an entry under **Completed** with the date and what changed.
Move items: **Todo** → **In Progress** → **Completed** as work progresses.
If blocked, mark ❌ and note why.
