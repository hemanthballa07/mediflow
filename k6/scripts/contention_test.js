/**
 * contention_test.js
 *
 * The resume-proof test.
 * Run AFTER you have a real slot ID from the API:
 *
 *   SLOT_ID=$(curl -s -X POST http://localhost:8000/api/v1/admin/slots \
 *     -H "X-Admin-Api-Key: changeme-replace-in-prod" \
 *     -H "Content-Type: application/json" \
 *     -d '{"doctor_id":"<UUID>","date":"2026-06-01","start_time":"09:00","end_time":"09:30"}' \
 *     | jq -r '.id')
 *
 *   TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
 *     -H "Content-Type: application/json" \
 *     -d '{"email":"patient@test.com","password":"password123"}' \
 *     | jq -r '.access_token')
 *
 *   k6 run -e SLOT_ID=$SLOT_ID -e TOKEN=$TOKEN k6/scripts/contention_test.js
 *
 * Expected results:
 *   ✓ booking_success_total == 1
 *   ✓ booking_conflict_total == 49 (or n_vus - 1)
 *   ✓ http_req_failed rate == 0%
 *   ✓ No duplicate rows in bookings table: SELECT count(*) FROM bookings WHERE slot_id = '<SLOT_ID>'
 */

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const success  = new Counter('booking_success_total');
const conflict = new Counter('booking_conflict_total');
const errors   = new Counter('booking_5xx_total');

const BASE     = __ENV.BASE_URL || 'http://localhost:8000';
const SLOT_ID  = __ENV.SLOT_ID;
const TOKEN    = __ENV.TOKEN;

export const options = {
  vus: 50,
  duration: '30s',
  thresholds: {
    'booking_5xx_total':    ['count==0'],           // zero server errors
    'http_req_failed':      ['rate==0'],             // no connection failures
    'http_req_duration':    ['p(99)<300'],           // p99 under 300ms even under contention
  },
};

export default function () {
  if (!SLOT_ID || !TOKEN) {
    console.error('Set SLOT_ID and TOKEN env vars. See file header for instructions.');
    return;
  }

  const res = http.post(
    `${BASE}/api/v1/bookings`,
    JSON.stringify({ slot_id: SLOT_ID }),
    {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${TOKEN}`,
        // Unique idempotency key per VU per iteration — each attempt is a distinct request
        'Idempotency-Key': `contention-vu${__VU}-iter${__ITER}`,
      },
    },
  );

  if (res.status === 201 || res.status === 200) {
    success.add(1);
    console.log(`✓ VU ${__VU} ITER ${__ITER}: slot BOOKED (${res.status})`);
  } else if (res.status === 409) {
    conflict.add(1);
  } else {
    errors.add(1);
    console.error(`✗ VU ${__VU}: unexpected ${res.status} — ${res.body}`);
  }

  check(res, {
    'no 5xx': (r) => r.status < 500,
    'booking or conflict': (r) => [200, 201, 409].includes(r.status),
  });
}
