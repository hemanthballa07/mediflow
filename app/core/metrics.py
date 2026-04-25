from prometheus_client import Counter, Histogram, Gauge, start_http_server
import threading

# ── HTTP ──────────────────────────────────────────────────────────────────────
http_requests_total = Counter(
    "mediflow_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "mediflow_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

# ── Booking ───────────────────────────────────────────────────────────────────
bookings_created_total = Counter(
    "mediflow_bookings_created_total",
    "Successful bookings created",
)

booking_conflicts_total = Counter(
    "mediflow_booking_conflicts_total",
    "Booking attempts that hit a conflict (slot already taken)",
)

booking_cancelled_total = Counter(
    "mediflow_booking_cancelled_total",
    "Bookings cancelled",
)

# ── Cache ─────────────────────────────────────────────────────────────────────
cache_hits_total = Counter(
    "mediflow_cache_hits_total",
    "Redis cache hits",
    ["cache_key_prefix"],
)

cache_misses_total = Counter(
    "mediflow_cache_misses_total",
    "Redis cache misses",
    ["cache_key_prefix"],
)

# ── Auth ──────────────────────────────────────────────────────────────────────
auth_failures_total = Counter(
    "mediflow_auth_failures_total",
    "Authentication failures",
    ["reason"],  # bad_credentials | token_expired | token_reuse
)

token_rotations_total = Counter(
    "mediflow_token_rotations_total",
    "Refresh token rotations",
)

token_family_revocations_total = Counter(
    "mediflow_token_family_revocations_total",
    "Token family revocations triggered by reuse detection",
)

# ── Reports ───────────────────────────────────────────────────────────────────
reports_accessed_total = Counter(
    "mediflow_reports_accessed_total",
    "Lab report fetch requests",
    ["status"],  # hit | miss
)

# ── Database ──────────────────────────────────────────────────────────────────
db_query_duration_seconds = Histogram(
    "mediflow_db_query_duration_seconds",
    "SQLAlchemy query execution latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# ── Idempotency ───────────────────────────────────────────────────────────────
idempotency_replays_total = Counter(
    "mediflow_idempotency_replays_total",
    "Requests served from idempotency cache",
)

# ── Clinical scheduling ───────────────────────────────────────────────────────
bookings_by_status = Gauge(
    "mediflow_bookings_by_status",
    "Current booking count by status",
    ["status"],
)

no_show_total = Counter(
    "mediflow_no_show_total",
    "Appointments marked no-show",
    ["department_id"],
)

checkin_to_start_seconds = Histogram(
    "mediflow_checkin_to_start_seconds",
    "Time between patient check-in and appointment start (waiting time)",
    buckets=[60, 300, 600, 900, 1800, 3600],
)

slots_generated_total = Counter(
    "mediflow_slots_generated_total",
    "Slots generated from doctor schedules",
)


_metrics_started = False
_metrics_lock = threading.Lock()


def start_metrics_server(port: int = 9100) -> None:
    global _metrics_started
    with _metrics_lock:
        if not _metrics_started:
            try:
                start_http_server(port)
                _metrics_started = True
            except OSError:
                # Another worker already bound the port — metrics still collected
                _metrics_started = True
