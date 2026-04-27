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
- ✅ 69 unit tests (pytest) — includes 11 Phase 3 clinical tests + 10 Phase 4 referrals/orders tests + 11 Phase 5 billing tests + 10 Phase 6 compliance tests
- ✅ 19 integration tests (live Docker stack) — includes Phase 3 + Phase 4 + Phase 5 flows
- ✅ **161/161 total passing**
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
- ✅ `referrals` table — cross-department patient routing; urgency (routine|urgent|stat); status machine (pending→accepted|rejected, accepted→completed); access-scoped by role
- ✅ `orders` table — lab/imaging/procedure orders with CPT codes; patient_id derived from encounter; existence-masked for wrong-doctor access
- ✅ `lab_reports.order_id` — nullable FK links reports to orders (migration 006)
- ✅ Migration `006_referrals_orders.py` — creates referrals, orders; ALTER TABLE lab_reports ADD COLUMN order_id
- ✅ `app/services/referrals.py` — ReferralsService: create, list_sent, list_received, list_for_patient, update_status; all PHI reads audited
- ✅ `app/services/orders.py` — OrdersService: create, get (404-masked), list_for_encounter; all PHI reads audited; patient→403
- ✅ Endpoints: `POST /referrals`, `GET /referrals/sent`, `GET /referrals/received`, `GET /referrals/my`, `PATCH /referrals/{id}/status`
- ✅ Endpoints: `POST /orders`, `GET /orders/{id}`, `GET /encounters/{id}/orders`
- ✅ 10 new unit tests (Phase 4 referrals + orders service access rules)
- ✅ 3 new integration tests (orders lifecycle, referral lifecycle, invalid transition)

### Phase 5 — Billing & Insurance (US)
- ✅ `insurance_plans` — name, payer_id (US payer ID), plan_type (HMO|PPO|EPO|POS|HDHP)
- ✅ `patient_insurance` — member_id, group_number, effective/termination dates, is_primary; partial unique index enforces single primary per patient
- ✅ `charge_masters` — CPT code pricing table; department-scoped; active flag
- ✅ `claims` — status machine (draft→submitted→accepted|rejected|paid); total_charged/total_paid (Numeric 10,2); submitted_at, adjudicated_at
- ✅ `claim_line_items` — per-CPT line with ICD-10 codes (text array), units, unit_price, total_price; optional order_id FK
- ✅ `payments` — payer (patient|insurance), payment_method (check|eft|card|cash), idempotent via IdempotencyKey; auto-transitions claim→paid when total_paid >= total_charged; SELECT FOR UPDATE prevents double-credit
- ✅ Migration `007_billing_insurance.py` — all 6 tables + indexes + partial unique (down_revision = 006)
- ✅ `app/services/insurance.py` — InsuranceService: create_plan, attach_to_patient (enforce single primary), list_for_patient; all PHI reads audited
- ✅ `app/services/charge_master.py` — ChargeMasterService: create, list (filter by cpt_code), get_by_cpt
- ✅ `app/services/claims.py` — ClaimsService: create (pricing from charge master), submit (state machine), get (404-masked for doctor scope), list_for_patient; all PHI reads audited
- ✅ `app/services/payments.py` — PaymentsService: idempotent record_payment; replicates BookingService idempotency pattern
- ✅ Endpoints: `POST /admin/insurance-plans`, `POST|GET /patients/{id}/insurance`
- ✅ Endpoints: `POST /admin/charge-masters`, `GET /charge-masters?cpt_code=`
- ✅ Endpoints: `POST /claims`, `POST /claims/{id}/submit`, `GET /claims/{id}`, `GET /patients/{id}/claims`, `POST /claims/{id}/payments`
- ✅ 11 new unit tests + 3 new integration tests

### Phase 6 — Compliance + Audit Hardening
- ✅ PHI access middleware — `phi_audit` FastAPI dependency wired to clinical, reports, claims, insurance, orders, referrals routers; auto-logs `PHI_ACCESSED` without per-endpoint calls
- ✅ Break-glass endpoint — `POST /admin/break-glass/{patient_id}` (admin + X-Admin-Api-Key); mandatory `reason`; logs `BREAK_GLASS_ACCESS` with admin_id + reason + timestamp; returns patient full chart
- ✅ GDPR export — `GET /patients/{id}/export` — returns all patient data (bookings, encounters, claims, insurance, reports, referrals, orders, vitals, diagnoses, prescriptions, allergies, problems); patient(own)/admin; audit logged
- ✅ GDPR deletion requests — `deletion_requests` table with status machine (pending→approved|rejected|completed); `POST/GET /patients/{id}/deletion-requests` + `PATCH /deletion-requests/{id}/status`
- ✅ Password history — `password_history` table; enforce no reuse of last 5 passwords; `POST /auth/change-password`; family token invalidation on change
- ✅ PII encryption — AES-256 (Fernet) encrypts `users.email` + `users.name` at rest; `email_hash` HMAC-SHA256 column for login lookup; transparent in service layer
- ✅ Migration `008_compliance.py` — password_history, deletion_requests tables; email_hash column on users; PII data migration via ENCRYPTION_KEY
- ✅ `app/core/encryption.py` — Fernet encrypt/decrypt + HMAC email_hash
- ✅ 10 new unit tests (Phase 6 compliance + PII encryption)


### Phase 7 — Reliability + Tracing
- ✅ `/health/live` — always 200 (process probe); `/health/ready` — DB + Redis probe, 503 on failure; old `/health` removed
- ✅ Redis circuit breaker — `execute_redis(coro)` in `app/db/redis.py`; 5 failures → OPEN; half-open after 30s; structured JSON log on transitions; `ReportService` cache calls wrapped; health probe bypasses CB
- ✅ Read replica routing — `READ_REPLICA_URL` optional env; `get_read_db` dep in `session.py` (falls back to primary); wired to GET /reports, GET /reports/{id}, GET /patients/{id}/chart, GET /patients/{id}/claims, GET /claims/{id}, all GET /catalog/* endpoints
- ✅ OpenTelemetry → Tempo — `app/core/telemetry.py` setup (FastAPI + SQLAlchemy + Redis instrumentation); graceful no-op on Tempo unreachable; `OTEL_EXPORTER_OTLP_ENDPOINT` env var; Tempo service in docker-compose (port 3200 + 4317); `deploy/tempo/tempo.yaml` local storage config; Grafana Tempo datasource provisioned; `opentelemetry-instrumentation-redis` added to requirements.txt; exemplar queries on latency panels
- ✅ SLO burn-rate Grafana panels — P99 latency SLO (500ms budget, 2× burn alert/1h) + error rate SLO (1% budget, 5× burn alert/5m); 4 new panels + 1 row appended to `mediflow_overview.json`

### Phase 8 — FHIR R4 + HL7
- ✅ `/fhir/r4/` read-only router (Patient, Practitioner, Appointment, Encounter, Observation, Condition, MedicationRequest, DiagnosticReport) — JWT auth, patient/doctor/admin scoped, replica routing, FHIR R4 JSON
- ✅ CapabilityStatement at `GET /fhir/r4/metadata`
- ✅ Webhook system: `webhooks` + `webhook_deliveries` tables (migration 009), HMAC-SHA256 signing (X-MediFlow-Signature), exponential backoff (1m/5m/30m/2h/8h, max 5 attempts), delivery worker, events: booking.created/cancelled, claim.submitted/paid, encounter.created
- ✅ Admin webhook endpoints: POST/GET/DELETE /api/v1/admin/webhooks, GET /api/v1/admin/webhooks/{id}/deliveries
- ✅ HL7 v2 ADT ingestion: `POST /hl7/adt` — ADT^A01 (admit/create patient) + ADT^A08 (update demographics), ACK AA/AE responses, admin-key secured
- ✅ **137/137 tests passing** (48 new Phase 8 tests added)

### Phase 9 — Clinical Decision Support + Real-time
- ✅ `cds_rules` table — facility_id (nullable=global), rule_type (drug_allergy|drug_drug|vital_alert|sepsis_score), rule_key, severity (info|warning|critical), message, active
- ✅ Migration `010_cds_rules.py` — creates cds_rules table + seeds 6 rules (penicillin allergy, sulfa allergy, aspirin-warfarin DDI, metformin-contrast DDI, qSOFA, elevated RR)
- ✅ `app/services/cds.py` — CdsService: evaluate_prescription (drug-allergy check, drug-drug interaction), evaluate_vitals (HR>120, SBP>180, DBP>120, SpO2<92, RR≥22, Temp>103°F), qSOFA score (RR≥22 + SBP≤100 = score≥2 → critical), publish_critical_alerts → Redis pub/sub
- ✅ Critical drug-allergy → HTTP 409 with cds_alerts in body (blocks prescription write)
- ✅ Drug-drug + vital alerts → non-blocking, returned in response alongside entity
- ✅ All CDS alert fires audited to audit_log (CDS_ALERT_FIRED action)
- ✅ POST /encounters/{id}/vitals now returns `VitalCreatedOut` {vital, cds_alerts[]}
- ✅ POST /encounters/{id}/prescriptions now returns `PrescriptionCreatedOut` {prescription, cds_alerts[]}
- ✅ Endpoints: `GET /encounters/{id}/cds-alerts` (doctor/admin; reads from audit_log)
- ✅ Endpoints: `GET /admin/cds-rules`, `POST /admin/cds-rules`, `PATCH /admin/cds-rules/{id}`
- ✅ `app/db/redis_pubsub.py` — separate Redis connection for pub/sub (subscriber connections isolated); publish helper with error swallowing
- ✅ WebSocket: `GET /ws/slots/{doctor_id}/{date}?token=JWT` — sends slot snapshot on connect, forwards Redis pub/sub events `{slot_id, status, timestamp}`
- ✅ WebSocket: `GET /ws/encounters/{encounter_id}/cds?token=JWT` — sends existing alerts on connect, forwards new critical/warning CDS alerts in real-time
- ✅ Slot pub/sub wired into booking.py: publishes `{slot_id, status: "booked"}` on create, `{slot_id, status: "available"}` on cancel
- ✅ CDS critical alerts published to `cds:{encounter_id}` Redis channel
- ✅ lifespan init/close for pubsub Redis connection
- ✅ **161/161 tests passing** (24 new Phase 9 tests: 14 CDS unit + 10 WebSocket/pub/sub)

---

## Roadmap — Not Started

### Phase 10 — CI/CD + Production Infra ⏳
**Priority: HIGH — do this before anything else ships**
- GitHub Actions pipeline: lint (ruff) → pytest → docker build → push image on PR + merge to main
- Kubernetes manifests (Deployment, Service, HPA, PodDisruptionBudget) or Helm chart
- PgBouncer sidecar for DB connection pooling (critical at scale)
- Secrets management: replace hardcoded JWT_SECRET/ADMIN_API_KEY with env injection (Vault or K8s secrets)
- `docker-compose.prod.yml` override: no exposed ports except 8000, read-only filesystem, no-new-privileges
- Data retention cron: archive bookings/audit_log rows older than 7 years (HIPAA minimum)

### Phase 11 — Prior Authorization ⏳
**Priority: HIGH — closes the billing loop**
- `prior_auth_requests` table — linked to orders + claims; status machine: pending → approved | denied | pending_info | expired
- `prior_auth_rules` table — payer_id + cpt_code combinations that require auth
- Hook into `POST /claims` submit: if any line item CPT requires auth and no approved PA → 409 with detail
- EDI 278 stub: `POST /admin/prior-auth/{id}/submit-edi` — serialize to X12 278 format (outbound only)
- Endpoints: `POST /prior-auth`, `GET /prior-auth/{id}`, `PATCH /prior-auth/{id}/status`, `GET /patients/{id}/prior-auths`
- Migration: `011_prior_auth.py`

### Phase 12 — Analytics + Operational Reporting ⏳
**Priority: MEDIUM**
- Materialized views (refreshed hourly via pg_cron or worker): `mv_daily_occupancy`, `mv_revenue_by_department`, `mv_no_show_cohort`
- Endpoints: `GET /admin/reports/revenue?from=&to=&department_id=`, `/admin/reports/utilization`, `/admin/reports/no-shows`
- No-show risk score per patient (rolling 90-day rate) — stored on `users` or computed view
- Grafana panels: revenue trend, occupancy heatmap, no-show rate by specialty
- CSV export for all report endpoints (`Accept: text/csv` header)

### Phase 13 — Patient Self-Service ⏳
**Priority: MEDIUM**
- Patient-initiated booking: currently doctor/admin creates encounters; patients can only book slots
- Secure messaging: `messages` table (thread_id, sender_id, recipient_id, body, read_at); patient↔doctor threaded inbox
- Care plan: `care_plans` + `care_plan_items` — discharge instructions, follow-up tasks, patient-visible
- Patient health summary: `GET /patients/me/summary` — active problems, current meds, upcoming bookings, recent labs
- Push notifications: FCM/APNS device token table, notification fan-out for appointment reminders

### Phase 14 — Production Hardening ⏳
**Priority: MEDIUM — needed before public launch**
- OWASP API Top 10 audit pass: mass assignment check, object-level auth on every endpoint, rate limits on all write endpoints
- Load test with realistic data: 10k patients, 100k bookings, 500k audit_log rows — verify query plans, add missing indexes
- Penetration test checklist: JWT alg confusion, SSRF via webhook URLs, IDOR on patient IDs
- Database backup + restore runbook (pg_dump, WAL archiving, point-in-time recovery test)
- Disaster recovery runbook: failover steps, RTO/RPO targets documented
- API versioning: `/api/v2/` prefix strategy, deprecation headers on v1 endpoints

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
Next file: `migrations/versions/011_*.py`
