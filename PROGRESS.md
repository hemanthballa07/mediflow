# MediFlow — Progress Log

Living source of truth. Reflects current project state at all times.

---

## Status Legend
- ✅ Done + pushed to main
- 🔄 In Progress
- ⏳ Todo
- ❌ Blocked

---

## What's Built (pushed to main)

### Auth
- ✅ JWT access tokens (15min) + refresh token rotation with family invalidation
- ✅ Logout endpoint (revokes token family, idempotent)
- ✅ Rate limiting on auth endpoints (slowapi + Redis, per-IP)
- ✅ bcrypt password hashing

### Multi-Tenant Data Model
- ✅ `facilities` table — hospitals/clinics with timezone support
- ✅ `specialties` table — Cardiology, Radiology, General Practice, etc.
- ✅ `departments` table — scoped to facility + specialty
- ✅ `rooms` table — exam/procedure/imaging/ward, scoped to facility + department
- ✅ `doctors`, `slots`, `bookings`, `lab_reports` all FK'd to facility + department
- ✅ `users.home_facility_id` FK
- ✅ Catalog endpoints: `GET /catalog/specialties`, `/catalog/facilities`, `/catalog/facilities/{id}/departments`, `/catalog/doctors?facility_id=&department_id=&specialty_id=`
- ✅ Admin catalog endpoints: `POST /admin/specialties`, `/admin/facilities`, `/admin/departments`, `/admin/rooms`

### Booking System
- ✅ `SELECT FOR UPDATE SKIP LOCKED` — concurrency-safe, no double-booking
- ✅ Idempotency key table — replay-safe POST /bookings
- ✅ Partial unique index on `bookings(slot_id) WHERE status = 'scheduled'`
- ✅ Cancellation window enforcement (24h, configurable)
- ✅ Per-user booking rate limit (JWT sub key, configurable via env)
- ✅ Room double-booking prevention (range overlap query)

### Clinical Scheduling (Phase 1)
- ✅ `appointment_types` — duration, buffer, requires_referral, requires_fasting, color
- ✅ `doctor_schedules` — recurring weekly availability with effective date range
- ✅ `doctor_time_off` — blocks out time ranges for a doctor
- ✅ Slot generator from schedules (`POST /admin/slots/generate`) — idempotent, respects time-off
- ✅ Booking status machine: `scheduled → checked_in → in_progress → completed | no_show | cancelled`
- ✅ Endpoints: `POST /bookings/{id}/check-in`, `/start`, `/complete`, `/no-show`
- ✅ Admin: `POST /admin/doctors/{id}/schedule`, `/admin/doctors/{id}/time-off`, `/admin/appointment-types`

### Reports
- ✅ Lab reports scoped to facility + department
- ✅ Keyset pagination, Redis cache-aside (5m TTL, first page only)
- ✅ Ownership enforcement (patients see only their own reports)

### Observability
- ✅ Prometheus metrics: HTTP latency, booking counters, cache hits, auth failures, DB query histogram, no-show rate, check-in wait time, bookings by status
- ✅ Grafana dashboard (auto-provisioned): HTTP + DB latency panels
- ✅ Structured JSON logging
- ✅ `/health` endpoint (DB + Redis liveness check)

### Infrastructure
- ✅ Docker Compose: postgres, redis, api, prometheus, grafana, migrator (one-shot)
- ✅ Alembic migrations: 001_initial, 002_multi_tenant, 003_clinical_scheduling
- ✅ Separate migrator service — API only starts after migrations succeed
- ✅ Seed script: 2 facilities, 3 specialties, 4 departments, 5 rooms, 2 doctors, 1 patient

### Security
- ✅ PyJWT (replaced python-jose CVEs)
- ✅ pydantic-settings v2
- ✅ HMAC-safe admin key comparison
- ✅ No hardcoded secrets — all required env vars
- ✅ Role-scoped endpoints (patient/doctor/admin)

### Tests
- ✅ 38 unit tests (pytest) — includes 11 Phase 3 clinical tests
- ✅ 13 integration tests (live Docker stack) — includes Phase 3 full workflow
- ✅ k6 load tests: benchmark.js, contention_test.js
- ✅ Contention test proven: 50 VUs, 1 booking through, 13,437 conflicts, 0 server errors

---

## Seeded Credentials
| Role       | Email                        | Password    |
|------------|------------------------------|-------------|
| Admin      | admin@mediflow.dev           | admin123    |
| Doctor GP  | doctor@mediflow.dev          | doctor123   |
| Cardiolog. | cardiologist@mediflow.dev    | cardio123   |
| Patient    | patient@mediflow.dev         | patient123  |

---

## Planned — Not Started

### Phase 2 — Waitlist + Notifications
- ✅ `waitlist_entries` table — patient queues for department/appointment type; statuses: waiting | notified | expired | cancelled
- ✅ `notifications` outbox table — email/SMS/push with per-row retry tracking (attempts, next_attempt_at, error, context)
- ✅ `patient_preferences` — preferred channel, language, reminder_hours_before[], per-channel toggles
- ✅ Waitlist service — FIFO by priority then created_at; auto-promotes next waiting patient on booking cancellation
- ✅ Notification worker (`worker/main.py`) — polls outbox every 10s, dispatches email via SMTP, SMS stub, exponential backoff (1/5/15 min), SELECT FOR UPDATE SKIP LOCKED
- ✅ Docker `worker` service + `mailhog` service (SMTP :1025, Web UI :8025)
- ✅ Migration 004 — `patient_preferences`, `waitlist_entries`, `notifications`
- ✅ `POST /api/v1/bookings` now enqueues BOOKING_CONFIRMED email
- ✅ `DELETE /api/v1/bookings/{id}` now enqueues BOOKING_CANCELLED email + triggers waitlist promotion
- ✅ Endpoints: `POST/GET/DELETE /api/v1/waitlist`, `GET /api/v1/waitlist/{id}/position`
- ✅ Endpoints: `GET/PUT /api/v1/preferences/me`

### Phase 3 — Clinical Data (Encounters)
- ✅ `encounters` table — ties booking to clinical visit; types: office_visit | telehealth | emergency | procedure | walk_in
- ✅ `vitals` table — BP, HR, temperature (°F), weight, height, SpO2, RR per encounter
- ✅ `diagnoses` table — ICD-10 code, primary/secondary/differential flag, onset date, resolved flag
- ✅ `prescriptions` table — drug, dose, frequency, route, start/end dates, refills, prescriber, status
- ✅ `allergies` table — allergen, reaction, severity (mild/moderate/severe/life_threatening/unknown), patient-scoped
- ✅ `problem_list` table — active/inactive/resolved chronic conditions per patient (ICD-10 optional)
- ✅ Migration 005_clinical_encounters.py — all 6 tables + indexes
- ✅ `app/services/clinical.py` — CRUD + chart + access control
- ✅ `GET /api/v1/patients/{id}/chart` — doctor/admin only; patients get 403; doctor sees own patients only (masked as 404); all PHI reads write to audit_log
- ✅ Write endpoints: `POST /encounters`, `/encounters/{id}/vitals`, `/encounters/{id}/diagnoses`, `/encounters/{id}/prescriptions`, `/patients/{id}/allergies`, `/patients/{id}/problems` — doctor/admin only

### Phase 4 — Referrals + Orders
- ⏳ `referrals` (cross-department patient routing)
- ⏳ `orders` (lab/imaging/procedure)
- ⏳ Link reports to orders

### Phase 5 — Billing & Insurance (US)
- ⏳ `insurance_plans`, `patient_insurance`, `charge_masters`, `claims`, `payments`
- ⏳ CPT/ICD-10 codes
- ⏳ Idempotent payment endpoint

### Phase 6 — Compliance + Audit Hardening
- ⏳ PHI access logging middleware
- ⏳ Break-glass endpoint
- ⏳ GDPR data export + delete request
- ⏳ PII encryption at rest
- ⏳ Password history + rotation

### Phase 7 — Reliability + Tracing
- ⏳ `/health/live` + `/health/ready` split
- ⏳ OpenTelemetry → Tempo in Docker Compose
- ⏳ Read replica routing
- ⏳ Circuit breaker on Redis
- ⏳ SLO burn-rate Grafana panels

### Phase 8 — FHIR R4 + HL7
- ⏳ `/fhir/r4/` read-only router (Patient, Practitioner, Appointment, Encounter, Observation, Condition, MedicationRequest, DiagnosticReport)
- ⏳ CapabilityStatement
- ⏳ Webhook system with HMAC signing + retry
- ⏳ HL7 v2 ADT ingestion

---

## Key Commands
```bash
make up              # start all services (from worktree dir)
make migrate         # run Alembic migrations
make seed            # seed test data
make test            # pytest
make contention-test SLOT_ID=<id> TOKEN=<token>
make logs            # follow API logs
make clean           # stop + remove volumes
```

## Next Migration
Next file: `migrations/versions/006_referrals_orders.py`
