import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// ── Custom metrics ────────────────────────────────────────────────────────────
const bookingConflicts = new Counter('booking_conflicts');
const bookingSuccess   = new Counter('booking_success');
const cacheHitProxy    = new Counter('report_fetches');

// ── Config ────────────────────────────────────────────────────────────────────
const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const ADMIN_KEY = __ENV.ADMIN_KEY || 'changeme-replace-in-prod';
const CONTENTION_SLOT_ID = __ENV.CONTENTION_SLOT_ID || '';

// ── Scenarios ─────────────────────────────────────────────────────────────────
export const options = {
  scenarios: {
    // a) Steady-state booking load: 50 req/s for 3 min
    steady_booking: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 60,
      maxVUs: 100,
      exec: 'steadyBooking',
      startTime: '0s',
    },

    // b) Slot contention: 50 VUs hammer one slot for 30s
    slot_contention: {
      executor: 'constant-vus',
      vus: 50,
      duration: '30s',
      exec: 'contentionBooking',
      startTime: '3m10s',  // run after steady test
    },

    // c) Report retrieval ramp: 0→20→20→0 VUs over 4 min
    report_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 20 },
        { duration: '2m', target: 20 },
        { duration: '1m', target: 0 },
      ],
      exec: 'getReports',
      startTime: '4m',
    },
  },

  thresholds: {
    // steady booking: p95 < 150ms, error rate < 1%
    'http_req_duration{scenario:steady_booking}': ['p(95)<150'],
    'http_req_failed{scenario:steady_booking}':   ['rate<0.01'],

    // slot contention: p99 < 300ms (contended path is slower)
    'http_req_duration{scenario:slot_contention}': ['p(99)<300'],

    // report load: p95 < 100ms
    'http_req_duration{scenario:report_load}': ['p(95)<100'],
    'http_req_failed{scenario:report_load}':   ['rate<0.01'],
  },
};

// ── Shared state (set in setup) ───────────────────────────────────────────────
export function setup() {
  // Register a test patient
  const patientRes = http.post(`${BASE}/api/v1/auth/register`, JSON.stringify({
    email: `k6-patient-${Date.now()}@test.com`,
    password: 'k6password123',
    name: 'K6 Patient',
    role: 'patient',
  }), { headers: { 'Content-Type': 'application/json' } });

  const loginRes = http.post(`${BASE}/api/v1/auth/login`, JSON.stringify({
    email: JSON.parse(patientRes.body).email,
    password: 'k6password123',
  }), { headers: { 'Content-Type': 'application/json' } });

  const tokens = JSON.parse(loginRes.body);

  // Register a test admin + doctor via admin API
  const doctorUserRes = http.post(`${BASE}/api/v1/auth/register`, JSON.stringify({
    email: `k6-doctor-${Date.now()}@test.com`,
    password: 'k6password123',
    name: 'K6 Doctor',
    role: 'doctor',
  }), { headers: { 'Content-Type': 'application/json' } });

  return {
    accessToken: tokens.access_token,
    patientId: JSON.parse(patientRes.body).id,
  };
}

// ── a) Steady booking ─────────────────────────────────────────────────────────
export function steadyBooking(data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.accessToken}`,
    'Idempotency-Key': `steady-${__VU}-${__ITER}-${Date.now()}`,
  };

  // Use a random slot id — most will 409 (no slot), which is fine for latency test
  const fakeSlotId = generateUUID();
  const res = http.post(
    `${BASE}/api/v1/bookings`,
    JSON.stringify({ slot_id: fakeSlotId }),
    { headers, tags: { scenario: 'steady_booking' } },
  );

  // 409 is an expected application response — not a failure
  check(res, {
    'booking responded': (r) => r.status === 201 || r.status === 409 || r.status === 200,
  });

  if (res.status === 201) bookingSuccess.add(1);
  if (res.status === 409) bookingConflicts.add(1);
}

// ── b) Slot contention ────────────────────────────────────────────────────────
export function contentionBooking(data) {
  if (!CONTENTION_SLOT_ID) return;

  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.accessToken}`,
    'Idempotency-Key': `contention-${__VU}-${__ITER}-${Date.now()}`,
  };

  const res = http.post(
    `${BASE}/api/v1/bookings`,
    JSON.stringify({ slot_id: CONTENTION_SLOT_ID }),
    { headers, tags: { scenario: 'slot_contention' } },
  );

  if (res.status === 201) {
    bookingSuccess.add(1);
    console.log(`VU ${__VU} iter ${__ITER}: BOOKED slot — exactly 1 expected`);
  }
  if (res.status === 409) {
    bookingConflicts.add(1);
  }

  check(res, {
    'no 5xx errors': (r) => r.status < 500,
    'booking or conflict': (r) => r.status === 201 || r.status === 409 || r.status === 200,
  });
}

// ── c) Report retrieval ───────────────────────────────────────────────────────
export function getReports(data) {
  const headers = {
    'Authorization': `Bearer ${data.accessToken}`,
  };

  const res = http.get(
    `${BASE}/api/v1/reports?patient_id=${data.patientId}&limit=20`,
    { headers, tags: { scenario: 'report_load' } },
  );

  check(res, {
    'reports 200': (r) => r.status === 200,
  });
  cacheHitProxy.add(1);

  sleep(0.1);  // 100ms think time — realistic read pattern
}

// ── helpers ───────────────────────────────────────────────────────────────────
function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}
