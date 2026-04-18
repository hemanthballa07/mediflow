"""
Unit tests for core business logic.
Run: pytest tests/ -v
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
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

    initial_revocations = metrics.token_family_revocations_total._value.get()

    with pytest.raises(HTTPException) as exc_info:
        await AuthService.refresh(jti="already-used-jti", db=mock_db)

    assert exc_info.value.status_code == 401
    assert "reuse" in exc_info.value.detail.lower()
    assert metrics.token_family_revocations_total._value.get() == initial_revocations + 1
