"""
Unit tests for core business logic.
Run: pytest tests/ -v
"""
import pytest
import uuid
from datetime import date, time, datetime, timezone
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
        "appointment_type_id": None,
        "room_id": None,
        "status": "scheduled",
        "reason_for_visit": None,
        "notes": None,
        "checked_in_at": None,
        "started_at": None,
        "completed_at": None,
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
    booking.status = "scheduled"
    booking.appointment_type_id = None
    booking.room_id = None
    booking.reason_for_visit = None
    booking.notes = None
    booking.checked_in_at = None
    booking.started_at = None
    booking.completed_at = None
    booking.created_at = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)

    slot = MagicMock()
    slot.doctor_id = uuid.uuid4()
    slot.date = date(2026, 6, 15)
    slot.start_time = time(9, 0)

    mock_user = MagicMock()
    mock_user.email = "patient@test.dev"
    mock_user.name = "Test Patient"

    mock_result_booking = MagicMock()
    mock_result_booking.scalar_one_or_none.return_value = booking
    mock_result_slot = MagicMock()
    mock_result_slot.scalar_one_or_none.return_value = slot
    mock_result_user = MagicMock()
    mock_result_user.scalar_one_or_none.return_value = mock_user
    # promote_next: no waiting entries
    mock_result_waitlist = MagicMock()
    mock_result_waitlist.scalars.return_value.first.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        mock_result_booking,   # select(Booking)
        mock_result_slot,      # select(Slot) for cancellation window
        AsyncMock(),           # UPDATE slots SET status = 'available'
        mock_result_user,      # select(User) for notification
        mock_result_waitlist,  # select(WaitlistEntry) in promote_next
    ])
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


# ── Phase 3: Clinical — access control ───────────────────────────────────────

@pytest.mark.asyncio
async def test_chart_patient_role_gets_403():
    """Patients cannot access any chart — always 403."""
    from fastapi import HTTPException
    from app.services.clinical import ClinicalService

    patient_user = MagicMock()
    patient_user.role = "patient"
    patient_user.id = uuid.uuid4()

    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await ClinicalService._assert_chart_access(
            requester=patient_user,
            patient_id=uuid.uuid4(),
            db=mock_db,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_chart_doctor_no_booking_relationship_gets_404():
    """Doctor with no booking to patient sees 404 (security masking)."""
    from fastapi import HTTPException
    from app.services.clinical import ClinicalService

    doctor_user = MagicMock()
    doctor_user.role = "doctor"
    doctor_user.id = uuid.uuid4()

    mock_doctor = MagicMock()
    mock_doctor.id = uuid.uuid4()

    mock_doctor_result = MagicMock()
    mock_doctor_result.scalar_one_or_none.return_value = mock_doctor

    mock_booking_result = MagicMock()
    mock_booking_result.scalar_one_or_none.return_value = None  # no link

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_doctor_result, mock_booking_result])

    with pytest.raises(HTTPException) as exc_info:
        await ClinicalService._assert_chart_access(
            requester=doctor_user,
            patient_id=uuid.uuid4(),
            db=mock_db,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_chart_admin_role_passes_access_check():
    """Admin role always passes access check with no DB queries."""
    from app.services.clinical import ClinicalService

    admin_user = MagicMock()
    admin_user.role = "admin"
    admin_user.id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    await ClinicalService._assert_chart_access(
        requester=admin_user,
        patient_id=uuid.uuid4(),
        db=mock_db,
    )

    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_chart_doctor_with_booking_passes_access_check():
    """Doctor who has booked with patient passes access check."""
    from app.services.clinical import ClinicalService

    doctor_user = MagicMock()
    doctor_user.role = "doctor"
    doctor_user.id = uuid.uuid4()

    mock_doctor = MagicMock()
    mock_doctor.id = uuid.uuid4()

    mock_doctor_result = MagicMock()
    mock_doctor_result.scalar_one_or_none.return_value = mock_doctor

    mock_booking = MagicMock()
    mock_booking_result = MagicMock()
    mock_booking_result.scalar_one_or_none.return_value = mock_booking

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_doctor_result, mock_booking_result])

    await ClinicalService._assert_chart_access(
        requester=doctor_user,
        patient_id=uuid.uuid4(),
        db=mock_db,
    )


# ── Phase 3: Clinical — encounter CRUD ───────────────────────────────────────

@pytest.mark.asyncio
async def test_create_encounter_returns_encounter():
    """create_encounter inserts and returns the encounter ORM object."""
    from datetime import date as date_type
    from app.services.clinical import ClinicalService
    from app.schemas.schemas import EncounterCreate

    payload = EncounterCreate(
        patient_id=uuid.uuid4(),
        doctor_id=uuid.uuid4(),
        encounter_type="office_visit",
        encounter_date=date_type.today(),
    )

    mock_enc = MagicMock()
    mock_enc.id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    with patch("app.services.clinical.Encounter", return_value=mock_enc):
        result = await ClinicalService.create_encounter(payload, mock_db)

    mock_db.add.assert_called_once_with(mock_enc)
    await mock_db.flush()
    assert result is mock_enc


@pytest.mark.asyncio
async def test_add_vitals_attaches_to_encounter():
    """add_vitals resolves the encounter and creates a Vital row."""
    from app.services.clinical import ClinicalService
    from app.schemas.schemas import VitalCreate

    encounter_id = uuid.uuid4()
    patient_id = uuid.uuid4()

    mock_enc = MagicMock()
    mock_enc.id = encounter_id
    mock_enc.patient_id = patient_id

    mock_enc_result = MagicMock()
    mock_enc_result.scalar_one_or_none.return_value = mock_enc

    mock_vital = MagicMock()

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_enc_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    recorder = MagicMock()
    recorder.id = uuid.uuid4()

    payload = VitalCreate(heart_rate=72, bp_systolic=120, bp_diastolic=80, spo2=98.5)

    with patch("app.services.clinical.Vital", return_value=mock_vital):
        result = await ClinicalService.add_vitals(encounter_id, payload, recorder, mock_db)

    mock_db.add.assert_called_once_with(mock_vital)
    assert result is mock_vital


@pytest.mark.asyncio
async def test_add_vitals_unknown_encounter_raises_404():
    """add_vitals raises 404 when encounter does not exist."""
    from fastapi import HTTPException
    from app.services.clinical import ClinicalService
    from app.schemas.schemas import VitalCreate

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await ClinicalService.add_vitals(
            uuid.uuid4(),
            VitalCreate(),
            MagicMock(),
            mock_db,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_add_diagnosis_uses_icd10_code():
    """add_diagnosis stores the ICD-10 code on the Diagnosis row."""
    from app.services.clinical import ClinicalService
    from app.schemas.schemas import DiagnosisCreate
    from datetime import date as date_type

    encounter_id = uuid.uuid4()
    mock_enc = MagicMock()
    mock_enc.id = encounter_id
    mock_enc.patient_id = uuid.uuid4()

    mock_enc_result = MagicMock()
    mock_enc_result.scalar_one_or_none.return_value = mock_enc

    created_dx = None

    def capture_dx(obj):
        nonlocal created_dx
        created_dx = obj

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_enc_result)
    mock_db.add = MagicMock(side_effect=capture_dx)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    creator = MagicMock()
    creator.id = uuid.uuid4()

    payload = DiagnosisCreate(
        icd10_code="E11.9",
        description="Type 2 diabetes mellitus without complications",
        diagnosis_type="primary",
        onset_date=date_type(2024, 1, 15),
    )

    from app.models.models import Diagnosis
    with patch("app.services.clinical.Diagnosis", wraps=Diagnosis) as mock_dx_cls:
        await ClinicalService.add_diagnosis(encounter_id, payload, creator, mock_db)
        call_kwargs = mock_dx_cls.call_args.kwargs
        assert call_kwargs["icd10_code"] == "E11.9"
        assert call_kwargs["diagnosis_type"] == "primary"


@pytest.mark.asyncio
async def test_add_prescription_sets_prescriber():
    """add_prescription sets prescriber_id from the caller's user."""
    from app.services.clinical import ClinicalService
    from app.schemas.schemas import PrescriptionCreate
    from datetime import date as date_type
    from app.models.models import Prescription

    encounter_id = uuid.uuid4()
    mock_enc = MagicMock()
    mock_enc.id = encounter_id
    mock_enc.patient_id = uuid.uuid4()

    mock_enc_result = MagicMock()
    mock_enc_result.scalar_one_or_none.return_value = mock_enc

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_enc_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    prescriber = MagicMock()
    prescriber.id = uuid.uuid4()

    payload = PrescriptionCreate(
        drug_name="Metformin",
        dose="500mg",
        frequency="twice daily",
        start_date=date_type.today(),
    )

    with patch("app.services.clinical.Prescription", wraps=Prescription) as mock_rx_cls:
        await ClinicalService.add_prescription(encounter_id, payload, prescriber, mock_db)
        call_kwargs = mock_rx_cls.call_args.kwargs
        assert call_kwargs["prescriber_id"] == prescriber.id
        assert call_kwargs["drug_name"] == "Metformin"


@pytest.mark.asyncio
async def test_add_allergy_records_severity():
    """add_allergy stores allergen and severity correctly."""
    from app.services.clinical import ClinicalService
    from app.schemas.schemas import AllergyCreate
    from app.models.models import Allergy

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    recorder = MagicMock()
    recorder.id = uuid.uuid4()

    payload = AllergyCreate(allergen="Penicillin", reaction="Anaphylaxis", severity="severe")

    with patch("app.services.clinical.Allergy", wraps=Allergy) as mock_allergy_cls:
        await ClinicalService.add_allergy(uuid.uuid4(), payload, recorder, mock_db)
        call_kwargs = mock_allergy_cls.call_args.kwargs
        assert call_kwargs["allergen"] == "Penicillin"
        assert call_kwargs["severity"] == "severe"


@pytest.mark.asyncio
async def test_add_problem_defaults_to_active_status():
    """add_problem defaults status to active when not specified."""
    from app.services.clinical import ClinicalService
    from app.schemas.schemas import ProblemCreate
    from app.models.models import ProblemList

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    noter = MagicMock()
    noter.id = uuid.uuid4()

    payload = ProblemCreate(
        icd10_code="I10",
        description="Essential hypertension",
    )

    with patch("app.services.clinical.ProblemList", wraps=ProblemList) as mock_pl_cls:
        await ClinicalService.add_problem(uuid.uuid4(), payload, noter, mock_db)
        call_kwargs = mock_pl_cls.call_args.kwargs
        assert call_kwargs["status"] == "active"
        assert call_kwargs["icd10_code"] == "I10"


# ── Phase 4: Referrals ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_referral_as_doctor_resolves_doctor_id():
    """create() for a doctor auto-resolves referring_doctor_id from their Doctor profile."""
    from app.services.referrals import ReferralsService
    from app.schemas.schemas import ReferralCreate
    from app.models.models import Referral

    doctor_user = MagicMock()
    doctor_user.role = "doctor"
    doctor_user.id = uuid.uuid4()

    mock_doctor = MagicMock()
    mock_doctor.id = uuid.uuid4()

    mock_doctor_result = MagicMock()
    mock_doctor_result.scalar_one_or_none.return_value = mock_doctor

    created_ref = None

    def capture(obj):
        nonlocal created_ref
        created_ref = obj

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_doctor_result)
    mock_db.add = MagicMock(side_effect=capture)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    payload = ReferralCreate(
        patient_id=uuid.uuid4(),
        receiving_department_id=uuid.uuid4(),
        reason="Cardiology follow-up",
    )

    with patch("app.services.referrals.Referral", wraps=Referral) as mock_ref_cls:
        await ReferralsService.create(payload, doctor_user, mock_db)
        call_kwargs = mock_ref_cls.call_args.kwargs
        assert call_kwargs["referring_doctor_id"] == mock_doctor.id


@pytest.mark.asyncio
async def test_create_referral_admin_missing_doctor_id_raises_400():
    """Admin creating a referral without referring_doctor_id gets 400."""
    from fastapi import HTTPException
    from app.services.referrals import ReferralsService
    from app.schemas.schemas import ReferralCreate

    admin_user = MagicMock()
    admin_user.role = "admin"
    admin_user.id = uuid.uuid4()

    mock_db = AsyncMock()

    payload = ReferralCreate(
        patient_id=uuid.uuid4(),
        receiving_department_id=uuid.uuid4(),
        reason="Needs specialist",
    )

    with pytest.raises(HTTPException) as exc_info:
        await ReferralsService.create(payload, admin_user, mock_db)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_referral_status_update_sets_responded_at():
    """update_status sets responded_at when status changes from pending."""
    from app.services.referrals import ReferralsService
    from app.schemas.schemas import ReferralStatusUpdate

    doctor_user = MagicMock()
    doctor_user.role = "admin"
    doctor_user.id = uuid.uuid4()

    dept_id = uuid.uuid4()
    mock_ref = MagicMock()
    mock_ref.id = uuid.uuid4()
    mock_ref.status = "pending"
    mock_ref.receiving_department_id = dept_id
    mock_ref.responded_at = None

    mock_ref_result = MagicMock()
    mock_ref_result.scalar_one_or_none.return_value = mock_ref

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_ref_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    payload = ReferralStatusUpdate(status="accepted")
    await ReferralsService.update_status(mock_ref.id, payload, doctor_user, mock_db)

    assert mock_ref.status == "accepted"
    assert mock_ref.responded_at is not None


@pytest.mark.asyncio
async def test_referral_invalid_status_transition_raises_422():
    """Transitioning from 'rejected' raises 422."""
    from fastapi import HTTPException
    from app.services.referrals import ReferralsService
    from app.schemas.schemas import ReferralStatusUpdate

    admin_user = MagicMock()
    admin_user.role = "admin"

    mock_ref = MagicMock()
    mock_ref.status = "rejected"

    mock_ref_result = MagicMock()
    mock_ref_result.scalar_one_or_none.return_value = mock_ref

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_ref_result)

    payload = ReferralStatusUpdate(status="accepted")

    with pytest.raises(HTTPException) as exc_info:
        await ReferralsService.update_status(uuid.uuid4(), payload, admin_user, mock_db)

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_referral_received_doctor_no_department_returns_empty():
    """Doctor with no department_id gets empty list from list_received."""
    from app.services.referrals import ReferralsService

    doctor_user = MagicMock()
    doctor_user.role = "doctor"
    doctor_user.id = uuid.uuid4()

    mock_doctor = MagicMock()
    mock_doctor.department_id = None

    mock_doctor_result = MagicMock()
    mock_doctor_result.scalar_one_or_none.return_value = mock_doctor

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_doctor_result)

    result = await ReferralsService.list_received(doctor_user, mock_db)
    assert result == []


# ── Phase 4: Orders ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_order_patient_derived_from_encounter():
    """create() derives patient_id from the encounter, not the payload."""
    from app.services.orders import OrdersService
    from app.schemas.schemas import OrderCreate
    from app.models.models import Order

    doctor_user = MagicMock()
    doctor_user.role = "doctor"
    doctor_user.id = uuid.uuid4()

    patient_id = uuid.uuid4()
    encounter_id = uuid.uuid4()

    mock_enc = MagicMock()
    mock_enc.id = encounter_id
    mock_enc.patient_id = patient_id

    mock_doctor = MagicMock()
    mock_doctor.id = uuid.uuid4()

    mock_enc_result = MagicMock()
    mock_enc_result.scalar_one_or_none.return_value = mock_enc

    mock_doctor_result = MagicMock()
    mock_doctor_result.scalar_one_or_none.return_value = mock_doctor

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_enc_result, mock_doctor_result])
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    payload = OrderCreate(
        encounter_id=encounter_id,
        order_type="lab",
        cpt_code="80053",
        description="Comprehensive metabolic panel",
    )

    with patch("app.services.orders.Order", wraps=Order) as mock_order_cls:
        await OrdersService.create(payload, doctor_user, mock_db)
        call_kwargs = mock_order_cls.call_args.kwargs
        assert call_kwargs["patient_id"] == patient_id


@pytest.mark.asyncio
async def test_get_order_patient_role_raises_403():
    """Patient calling OrdersService.get() always gets 403."""
    from fastapi import HTTPException
    from app.services.orders import OrdersService

    patient_user = MagicMock()
    patient_user.role = "patient"

    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await OrdersService.get(uuid.uuid4(), patient_user, mock_db)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_order_wrong_doctor_returns_404():
    """Doctor who did not place the order gets 404 (existence masking)."""
    from fastapi import HTTPException
    from app.services.orders import OrdersService

    doctor_user = MagicMock()
    doctor_user.role = "doctor"
    doctor_user.id = uuid.uuid4()

    other_doctor_id = uuid.uuid4()
    my_doctor_id = uuid.uuid4()

    mock_order = MagicMock()
    mock_order.ordering_doctor_id = other_doctor_id

    mock_doctor = MagicMock()
    mock_doctor.id = my_doctor_id

    mock_order_result = MagicMock()
    mock_order_result.scalar_one_or_none.return_value = mock_order

    mock_doctor_result = MagicMock()
    mock_doctor_result.scalar_one_or_none.return_value = mock_doctor

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_order_result, mock_doctor_result])
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await OrdersService.get(uuid.uuid4(), doctor_user, mock_db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_order_writes_audit_log():
    """Successful order GET writes an audit log entry."""
    from app.services.orders import OrdersService

    admin_user = MagicMock()
    admin_user.role = "admin"
    admin_user.id = uuid.uuid4()

    order_id = uuid.uuid4()
    mock_order = MagicMock()
    mock_order.id = order_id

    mock_order_result = MagicMock()
    mock_order_result.scalar_one_or_none.return_value = mock_order

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_order_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    with patch("app.services.orders.AuditService.log", new=AsyncMock()) as mock_audit:
        await OrdersService.get(order_id, admin_user, mock_db)
        mock_audit.assert_awaited_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["action"] == "ORDER_ACCESSED"
        assert call_kwargs["target"] == str(order_id)


@pytest.mark.asyncio
async def test_list_encounter_orders_patient_raises_403():
    """Patient calling list_for_encounter always gets 403."""
    from fastapi import HTTPException
    from app.services.orders import OrdersService

    patient_user = MagicMock()
    patient_user.role = "patient"

    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await OrdersService.list_for_encounter(uuid.uuid4(), patient_user, mock_db)

    assert exc_info.value.status_code == 403


# ── Phase 5: Billing ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insurance_plan_schema_rejects_invalid_plan_type():
    """InsurancePlanCreate rejects unknown plan types."""
    from pydantic import ValidationError
    from app.schemas.schemas import InsurancePlanCreate

    with pytest.raises(ValidationError):
        InsurancePlanCreate(name="Test Plan", payer_id="12345", plan_type="HMX")


def test_insurance_plan_schema_accepts_valid_types():
    """InsurancePlanCreate accepts all valid US plan types."""
    from app.schemas.schemas import InsurancePlanCreate

    for plan_type in ("HMO", "PPO", "EPO", "POS", "HDHP"):
        plan = InsurancePlanCreate(name="Test", payer_id="12345", plan_type=plan_type)
        assert plan.plan_type == plan_type


@pytest.mark.asyncio
async def test_attach_insurance_patient_cross_access_raises_403():
    """A patient cannot attach insurance to another patient."""
    from fastapi import HTTPException
    from app.services.insurance import InsuranceService
    from app.schemas.schemas import PatientInsuranceCreate

    patient_user = MagicMock()
    patient_user.role = "patient"
    patient_user.id = uuid.uuid4()

    mock_db = AsyncMock()

    payload = PatientInsuranceCreate(
        insurance_plan_id=uuid.uuid4(),
        member_id="M123",
        effective_date=date(2026, 1, 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        await InsuranceService.attach_to_patient(
            patient_id=uuid.uuid4(),  # different from patient_user.id
            payload=payload,
            current_user=patient_user,
            db=mock_db,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_attach_insurance_rejects_bad_date_range():
    """termination_date < effective_date raises 400."""
    from fastapi import HTTPException
    from app.services.insurance import InsuranceService
    from app.schemas.schemas import PatientInsuranceCreate

    admin_user = MagicMock()
    admin_user.role = "admin"
    admin_user.id = uuid.uuid4()

    patient_id = uuid.uuid4()

    mock_patient = MagicMock()
    mock_patient.role = "patient"
    mock_patient_result = MagicMock()
    mock_patient_result.scalar_one_or_none.return_value = mock_patient

    mock_plan_result = MagicMock()
    mock_plan_result.scalar_one_or_none.return_value = MagicMock()

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_patient_result, mock_plan_result])

    payload = PatientInsuranceCreate(
        insurance_plan_id=uuid.uuid4(),
        member_id="M123",
        effective_date=date(2026, 6, 1),
        termination_date=date(2026, 1, 1),  # before effective
    )

    with pytest.raises(HTTPException) as exc_info:
        await InsuranceService.attach_to_patient(
            patient_id=patient_id,
            payload=payload,
            current_user=admin_user,
            db=mock_db,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_claim_missing_line_items_raises_400():
    """ClaimsService.create() with empty line_items raises 400."""
    from fastapi import HTTPException
    from app.services.claims import ClaimsService
    from app.schemas.schemas import ClaimCreate

    doctor_user = MagicMock()
    doctor_user.role = "doctor"
    doctor_user.id = uuid.uuid4()

    encounter_id = uuid.uuid4()
    mock_enc = MagicMock()
    mock_enc.id = encounter_id
    mock_enc.patient_id = uuid.uuid4()

    mock_enc_result = MagicMock()
    mock_enc_result.scalar_one_or_none.return_value = mock_enc

    mock_ins_result = MagicMock()
    mock_ins = MagicMock()
    mock_ins.patient_id = mock_enc.patient_id
    mock_ins_result.scalar_one_or_none.return_value = mock_ins

    mock_doctor = MagicMock()
    mock_doctor.id = uuid.uuid4()
    mock_doctor_result = MagicMock()
    mock_doctor_result.scalar_one_or_none.return_value = mock_doctor

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_enc_result, mock_ins_result, mock_doctor_result])

    payload = ClaimCreate(
        encounter_id=encounter_id,
        patient_insurance_id=uuid.uuid4(),
        line_items=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await ClaimsService.create(payload, doctor_user, mock_db)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_submit_claim_non_draft_raises_409():
    """submit() on a non-draft claim raises 409."""
    from fastapi import HTTPException
    from app.services.claims import ClaimsService

    doctor_user = MagicMock()
    doctor_user.role = "admin"
    doctor_user.id = uuid.uuid4()

    mock_claim = MagicMock()
    mock_claim.status = "submitted"
    mock_claim.ordering_doctor_id = uuid.uuid4()

    mock_claim_result = MagicMock()
    mock_claim_result.scalar_one_or_none.return_value = mock_claim

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_claim_result)
    mock_db.flush = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await ClaimsService.submit(uuid.uuid4(), doctor_user, mock_db)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_get_claim_patient_sees_only_own():
    """Patient requesting another patient's claim gets 404."""
    from fastapi import HTTPException
    from app.services.claims import ClaimsService

    patient_user = MagicMock()
    patient_user.role = "patient"
    patient_user.id = uuid.uuid4()

    mock_claim = MagicMock()
    mock_claim.patient_id = uuid.uuid4()  # different owner
    mock_claim.ordering_doctor_id = uuid.uuid4()

    mock_claim_result = MagicMock()
    mock_claim_result.scalar_one_or_none.return_value = mock_claim

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_claim_result)

    with pytest.raises(HTTPException) as exc_info:
        await ClaimsService.get(uuid.uuid4(), patient_user, mock_db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_claim_wrong_doctor_returns_404():
    """Doctor who did not create the claim gets 404 (masking)."""
    from fastapi import HTTPException
    from app.services.claims import ClaimsService

    doctor_user = MagicMock()
    doctor_user.role = "doctor"
    doctor_user.id = uuid.uuid4()

    my_doctor_id = uuid.uuid4()
    other_doctor_id = uuid.uuid4()

    mock_claim = MagicMock()
    mock_claim.patient_id = uuid.uuid4()
    mock_claim.ordering_doctor_id = other_doctor_id

    mock_claim_result = MagicMock()
    mock_claim_result.scalar_one_or_none.return_value = mock_claim

    mock_doctor = MagicMock()
    mock_doctor.id = my_doctor_id

    mock_doctor_result = MagicMock()
    mock_doctor_result.scalar_one_or_none.return_value = mock_doctor

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_claim_result, mock_doctor_result])

    with pytest.raises(HTTPException) as exc_info:
        await ClaimsService.get(uuid.uuid4(), doctor_user, mock_db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_payment_idempotency_replay_returns_cached():
    """Same Idempotency-Key replays cached PaymentOut without creating new payment."""
    from app.services.payments import PaymentsService
    from app.schemas.schemas import PaymentCreate

    admin_user = MagicMock()
    admin_user.id = uuid.uuid4()
    admin_user.role = "admin"

    payment_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    cached_response = {
        "id": str(payment_id),
        "claim_id": str(claim_id),
        "payer": "insurance",
        "amount": 150.0,
        "payment_method": "eft",
        "reference_number": "REF001",
        "paid_at": "2026-04-26T12:00:00+00:00",
        "created_at": "2026-04-26T12:00:00+00:00",
    }

    mock_idem = MagicMock()
    mock_idem.status = "SUCCESS"
    mock_idem.response = cached_response

    mock_idem_result = MagicMock()
    mock_idem_result.scalar_one_or_none.return_value = mock_idem

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_idem_result)

    payload = PaymentCreate(
        payer="insurance",
        amount=150.0,
        payment_method="eft",
        paid_at=datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc),
    )

    out, http_status = await PaymentsService.record_payment(
        claim_id=claim_id,
        payload=payload,
        idempotency_key="test-idem-key",
        current_user=admin_user,
        db=mock_db,
    )

    assert http_status == 200
    assert str(out.id) == str(payment_id)


@pytest.mark.asyncio
async def test_payment_schema_rejects_invalid_payer():
    """PaymentCreate rejects invalid payer values."""
    from pydantic import ValidationError
    from app.schemas.schemas import PaymentCreate

    with pytest.raises(ValidationError):
        PaymentCreate(
            payer="hospital",  # invalid
            amount=100.0,
            payment_method="check",
            paid_at=datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_charge_master_service_create():
    """ChargeMasterService.create inserts an entry with correct fields."""
    from app.services.charge_master import ChargeMasterService
    from app.schemas.schemas import ChargeMasterCreate
    from app.models.models import ChargeMaster

    mock_entry = MagicMock()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

    payload = ChargeMasterCreate(
        cpt_code="99213",
        description="Office visit, established patient",
        base_price=150.00,
    )

    with patch("app.services.charge_master.ChargeMaster", return_value=mock_entry) as mock_cls:
        result = await ChargeMasterService.create(payload, mock_db)
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["cpt_code"] == "99213"
        assert call_kwargs["base_price"] == 150.00
    assert result is mock_entry
