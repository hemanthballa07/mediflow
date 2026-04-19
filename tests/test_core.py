"""
Unit tests for core business logic.
Run: pytest tests/ -v
"""
import pytest
import uuid
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError
from app.core.security import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    create_refresh_jti,
)


# ── Security ──────────────────────────────────────────────────────────────────

def test_password_hash_and_verify():
    plain = "super-secret-password"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "patient")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "patient"
    assert "jti" in payload
    assert "exp" in payload


def test_refresh_jti_is_unique():
    jtis = {create_refresh_jti() for _ in range(1000)}
    assert len(jtis) == 1000  # all unique


# ── Booking service ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_booking_conflict_increments_metric():
    """When slot is locked/unavailable, booking_conflicts counter should increment."""
    from app.core import metrics

    initial = metrics.booking_conflicts_total._value.get()

    # Mock DB that returns no locked slot (simulating contention)
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None  # SKIP LOCKED returned nothing

    # Mock idempotency check returning None (new key)
    mock_idem_result = MagicMock()
    mock_idem_result.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(side_effect=[mock_idem_result, mock_result])
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.add = MagicMock()

    mock_redis = AsyncMock()

    from fastapi import HTTPException
    from app.services.booking import BookingService

    with pytest.raises(HTTPException) as exc_info:
        await BookingService.create_booking(
            user_id=uuid.uuid4(),
            slot_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            db=mock_db,
            redis=mock_redis,
        )

    assert exc_info.value.status_code == 409
    # Metric incremented
    assert metrics.booking_conflicts_total._value.get() == initial + 1


@pytest.mark.asyncio
async def test_idempotency_replay_returns_cached_response():
    """Same idempotency key returns stored response without re-executing logic."""
    from app.core import metrics
    from app.services.booking import BookingService

    booking_id = uuid.uuid4()
    slot_id = uuid.uuid4()
    user_id = uuid.uuid4()
    key = str(uuid.uuid4())

    # Simulate existing SUCCESS idempotency record
    mock_idem = MagicMock()
    mock_idem.status = "SUCCESS"
    mock_idem.response = {
        "id": str(booking_id),
        "user_id": str(user_id),
        "slot_id": str(slot_id),
        "status": "active",
        "created_at": "2026-01-01T00:00:00",
    }

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_idem

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_redis = AsyncMock()

    initial_replays = metrics.idempotency_replays_total._value.get()

    out, status_code = await BookingService.create_booking(
        user_id=user_id,
        slot_id=slot_id,
        idempotency_key=key,
        db=mock_db,
        redis=mock_redis,
    )

    assert status_code == 200  # replay returns 200
    assert str(out.id) == str(booking_id)
    assert metrics.idempotency_replays_total._value.get() == initial_replays + 1


# ── Auth service ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_token_reuse_detection_revokes_family():
    """Presenting an already-used refresh token revokes the entire token family."""
    from app.core import metrics
    from app.services.auth import AuthService
    from fastapi import HTTPException

    family_id = uuid.uuid4()
    used_token = MagicMock()
    used_token.revoked = False
    used_token.used_at = "2026-01-01T00:00:00"  # already used
    used_token.expires_at = MagicMock()
    used_token.expires_at.replace = MagicMock(return_value=MagicMock(
        __lt__=MagicMock(return_value=False)  # not expired
    ))
    used_token.family_id = family_id
    used_token.user_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = used_token

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    initial_revocations = metrics.token_family_revocations_total._value.get()

    with pytest.raises(HTTPException) as exc_info:
        await AuthService.refresh(jti="already-used-jti", db=mock_db)

    assert exc_info.value.status_code == 401
    assert "reuse" in exc_info.value.detail.lower()
    assert metrics.token_family_revocations_total._value.get() == initial_revocations + 1


# ── Block A security fixes ────────────────────────────────────────────────────

def test_register_rejects_admin_role():
    """POST /auth/register must not accept role=admin."""
    from app.schemas.schemas import RegisterRequest
    with pytest.raises(ValidationError):
        RegisterRequest(email="x@x.com", password="secret", name="X", role="admin")


def test_register_accepts_valid_roles():
    """patient and doctor are the only self-assignable roles."""
    from app.schemas.schemas import RegisterRequest
    for role in ("patient", "doctor"):
        r = RegisterRequest(email="x@x.com", password="secret", name="X", role=role)
        assert r.role == role


@pytest.mark.asyncio
async def test_list_reports_patient_cannot_access_other_patient():
    """A patient requesting another patient's reports gets 403."""
    from fastapi import HTTPException
    from app.api.v1.endpoints.reports import list_reports

    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()

    patient_user = MagicMock()
    patient_user.role = "patient"
    patient_user.id = owner_id

    mock_db = AsyncMock()
    mock_redis = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await list_reports(
            patient_id=other_id,
            report_status=None,
            cursor=None,
            limit=20,
            current_user=patient_user,
            db=mock_db,
            redis=mock_redis,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_reports_patient_can_access_own():
    """A patient can list their own reports without 403."""
    from app.api.v1.endpoints.reports import list_reports
    from app.schemas.schemas import ReportPage

    patient_id = uuid.uuid4()

    patient_user = MagicMock()
    patient_user.role = "patient"
    patient_user.id = patient_id

    mock_db = AsyncMock()
    mock_redis = AsyncMock()

    with patch("app.api.v1.endpoints.reports.ReportService.list_reports",
               new=AsyncMock(return_value=ReportPage(items=[], next_cursor=None))):
        result = await list_reports(
            patient_id=patient_id,
            report_status=None,
            cursor=None,
            limit=20,
            current_user=patient_user,
            db=mock_db,
            redis=mock_redis,
        )
    assert result.items == []


# ── Block D new tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_available_slots_passes_string_date():
    """GET /bookings/slots/available converts date param to str before calling service."""
    from datetime import date as date_type
    from app.api.v1.endpoints.bookings import get_available_slots

    doctor_id = uuid.uuid4()
    target_date = date_type(2026, 6, 15)

    mock_db = AsyncMock()
    mock_redis = AsyncMock()

    with patch(
        "app.api.v1.endpoints.bookings.BookingService.get_available_slots",
        new=AsyncMock(return_value=[]),
    ) as mock_svc:
        await get_available_slots(
            doctor_id=doctor_id,
            date=target_date,
            db=mock_db,
            redis=mock_redis,
        )
        mock_svc.assert_awaited_once_with(doctor_id, "2026-06-15", mock_db, mock_redis)


@pytest.mark.asyncio
async def test_register_rate_limit_enforced():
    """POST /auth/register raises RateLimitExceeded when limiter fires."""
    from starlette.requests import Request as StarletteRequest
    from app.api.v1.endpoints.auth import register
    from app.schemas.schemas import RegisterRequest
    from slowapi.errors import RateLimitExceeded

    payload = RegisterRequest(email="x@x.com", password="secret", name="X", role="patient")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/register",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 9999),
    }
    real_request = StarletteRequest(scope)
    mock_db = AsyncMock()

    mock_limit = MagicMock()
    mock_limit.error_message = None

    with patch(
        "slowapi.extension.Limiter._check_request_limit",
        side_effect=RateLimitExceeded(mock_limit),
    ):
        with pytest.raises(RateLimitExceeded):
            await register(request=real_request, payload=payload, db=mock_db)


def test_report_page_next_cursor_defaults_none():
    """ReportPage with no items has next_cursor=None by default."""
    from app.schemas.schemas import ReportPage
    page = ReportPage(items=[])
    assert page.next_cursor is None


# ── Phase D: health endpoint ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_200_when_all_healthy():
    """GET /health returns 200 with ok status when DB and Redis are up."""
    import json
    from fastapi.responses import JSONResponse
    from app.main import health

    with patch("app.main.AsyncSessionLocal") as mock_session_cls, \
         patch("app.main.get_redis") as mock_get_redis:

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_get_redis.return_value = mock_redis

        response = await health()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_503_when_db_fails():
    """GET /health returns 503 with db=error when DB is unreachable."""
    import json
    from fastapi.responses import JSONResponse
    from app.main import health

    with patch("app.main.AsyncSessionLocal") as mock_session_cls, \
         patch("app.main.get_redis") as mock_get_redis:

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB down"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_get_redis.return_value = mock_redis

        response = await health()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["status"] == "error"
    assert body["db"] == "error"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_503_when_redis_fails():
    """GET /health returns 503 with redis=error when Redis is unreachable."""
    import json
    from fastapi.responses import JSONResponse
    from app.main import health

    with patch("app.main.AsyncSessionLocal") as mock_session_cls, \
         patch("app.main.get_redis") as mock_get_redis:

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        mock_get_redis.side_effect = Exception("Redis down")

        response = await health()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["status"] == "error"
    assert body["db"] == "ok"
    assert body["redis"] == "error"


# ── Phase D: slot validation ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slot_create_rejects_end_before_start():
    """POST /admin/slots returns 422 when end_time <= start_time."""
    from datetime import date, time
    from fastapi import HTTPException
    from app.api.v1.endpoints.admin import create_slot
    from app.schemas.schemas import SlotCreate

    payload = SlotCreate(
        doctor_id=uuid.uuid4(),
        date=date.today(),
        start_time=time(10, 0),
        end_time=time(9, 0),
    )
    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_slot(payload=payload, _=None, db=mock_db)

    assert exc_info.value.status_code == 422
    assert "end_time" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_slot_create_rejects_past_date():
    """POST /admin/slots returns 422 when slot date is in the past."""
    from datetime import date, time
    from fastapi import HTTPException
    from app.api.v1.endpoints.admin import create_slot
    from app.schemas.schemas import SlotCreate

    payload = SlotCreate(
        doctor_id=uuid.uuid4(),
        date=date(2020, 1, 1),
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_slot(payload=payload, _=None, db=mock_db)

    assert exc_info.value.status_code == 422
    assert "past" in exc_info.value.detail.lower()


# ── Phase D: report cache TTL ─────────────────────────────────────────────────

def test_report_cache_ttl_comes_from_config():
    """REPORT_CACHE_TTL is defined in settings, not hardcoded."""
    from app.core.config import get_settings
    s = get_settings()
    assert hasattr(s, "REPORT_CACHE_TTL")
    assert s.REPORT_CACHE_TTL == 300


# ── Phase D: auth failures ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_wrong_password_returns_401():
    """Login with wrong password raises 401 and increments auth_failures_total."""
    from fastapi import HTTPException
    from app.services.auth import AuthService
    from app.core import metrics

    user = MagicMock()
    user.hashed_password = "hashed"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    initial = metrics.auth_failures_total.labels(reason="bad_credentials")._value.get()

    with patch("app.services.auth.verify_password", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await AuthService.login(email="x@x.com", password="wrong", db=mock_db)

    assert exc_info.value.status_code == 401
    assert metrics.auth_failures_total.labels(reason="bad_credentials")._value.get() == initial + 1


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401():
    """Login with unknown email raises 401."""
    from fastapi import HTTPException
    from app.services.auth import AuthService

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await AuthService.login(email="nobody@x.com", password="any", db=mock_db)

    assert exc_info.value.status_code == 401


# ── Phase D: booking cancellation ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_booking_own_succeeds():
    """A user can cancel their own booking."""
    from app.services.booking import BookingService

    user_id = uuid.uuid4()
    booking_id = uuid.uuid4()
    slot_id = uuid.uuid4()

    booking = MagicMock()
    booking.id = booking_id
    booking.user_id = user_id
    booking.slot_id = slot_id
    booking.status = "active"

    slot = MagicMock()
    slot.doctor_id = uuid.uuid4()
    slot.date = date(2026, 6, 15)
    slot.start_time = time(9, 0)

    mock_result_booking = MagicMock()
    mock_result_booking.scalar_one_or_none.return_value = booking
    mock_result_slot = MagicMock()
    mock_result_slot.scalar_one_or_none.return_value = slot

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_result_booking, mock_result_slot, AsyncMock()])
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_redis = AsyncMock()

    await BookingService.cancel_booking(
        booking_id=booking_id, user_id=user_id, db=mock_db, redis=mock_redis
    )
    assert booking.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_booking_other_user_returns_403():
    """A user cannot cancel another user's booking."""
    from fastapi import HTTPException
    from app.services.booking import BookingService

    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    booking_id = uuid.uuid4()

    booking = MagicMock()
    booking.id = booking_id
    booking.user_id = owner_id
    booking.status = "active"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = booking

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await BookingService.cancel_booking(
            booking_id=booking_id, user_id=other_id, db=mock_db, redis=AsyncMock()
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cancel_already_cancelled_returns_409():
    """Cancelling an already-cancelled booking raises 409."""
    from fastapi import HTTPException
    from app.services.booking import BookingService

    user_id = uuid.uuid4()
    booking_id = uuid.uuid4()

    booking = MagicMock()
    booking.id = booking_id
    booking.user_id = user_id
    booking.status = "cancelled"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = booking

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await BookingService.cancel_booking(
            booking_id=booking_id, user_id=user_id, db=mock_db, redis=AsyncMock()
        )

    assert exc_info.value.status_code == 409


# ── Phase G tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_booking_within_24h_window_raises_409():
    """Cancel within 24h of appointment start raises 409."""
    from datetime import datetime, timezone, timedelta
    from fastapi import HTTPException
    from app.services.booking import BookingService

    user_id = uuid.uuid4()
    booking_id = uuid.uuid4()
    slot_id = uuid.uuid4()

    booking = MagicMock()
    booking.id = booking_id
    booking.user_id = user_id
    booking.slot_id = slot_id
    booking.status = "active"

    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    slot = MagicMock()
    slot.date = soon.date()
    slot.start_time = soon.time()

    mock_result_booking = MagicMock()
    mock_result_booking.scalar_one_or_none.return_value = booking
    mock_result_slot = MagicMock()
    mock_result_slot.scalar_one_or_none.return_value = slot

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_result_booking, mock_result_slot])

    with pytest.raises(HTTPException) as exc_info:
        await BookingService.cancel_booking(
            booking_id=booking_id, user_id=user_id, db=mock_db, redis=AsyncMock()
        )

    assert exc_info.value.status_code == 409
    assert "24h" in exc_info.value.detail


def test_get_user_id_from_request_extracts_jwt_sub():
    """get_user_id_from_request returns user UUID from valid Bearer token."""
    from app.core.limiter import get_user_id_from_request
    from app.core.security import create_access_token

    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, role="patient")

    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {token}"}

    result = get_user_id_from_request(request)
    assert result == str(user_id)


def test_db_query_duration_histogram_is_registered():
    """db_query_duration_seconds is a Histogram with observe callable."""
    from prometheus_client import Histogram
    from app.core.metrics import db_query_duration_seconds

    assert isinstance(db_query_duration_seconds, Histogram)
    assert callable(db_query_duration_seconds.observe)
