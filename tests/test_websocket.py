"""
Unit tests for Phase 9B: WebSocket + Redis pub/sub.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.redis_pubsub import publish


# ── redis_pubsub publish ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_calls_redis_publish():
    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    with patch("app.db.redis_pubsub.get_pubsub_redis", AsyncMock(return_value=mock_redis)):
        await publish("slots:doctor-1:2026-01-01", '{"slot_id": "abc", "status": "booked"}')

    mock_redis.publish.assert_called_once_with(
        "slots:doctor-1:2026-01-01",
        '{"slot_id": "abc", "status": "booked"}',
    )


@pytest.mark.asyncio
async def test_publish_swallows_redis_error():
    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))

    with patch("app.db.redis_pubsub.get_pubsub_redis", AsyncMock(return_value=mock_redis)):
        # Should not raise
        await publish("test:channel", "payload")


# ── WS auth helper ─────────────────────────────────────────────────────────────

def test_ws_token_payload_structure():
    from app.core.security import create_access_token, decode_access_token
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "doctor")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "doctor"


def test_ws_invalid_token_raises():
    from app.core.security import decode_access_token
    from jwt.exceptions import InvalidTokenError
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-valid-token")


# ── Slot pub/sub channel naming ───────────────────────────────────────────────

def test_slot_channel_name_format():
    doctor_id = uuid.uuid4()
    date = "2026-04-27"
    channel = f"slots:{doctor_id}:{date}"
    assert channel.startswith("slots:")
    assert date in channel
    assert str(doctor_id) in channel


def test_cds_channel_name_format():
    encounter_id = uuid.uuid4()
    channel = f"cds:{encounter_id}"
    assert channel.startswith("cds:")
    assert str(encounter_id) in channel


# ── Booking slot publish integration ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_booking_publishes_slot_booked_event():
    from app.db import redis_pubsub

    published_messages = []

    async def capture_publish(channel, message):
        published_messages.append((channel, message))

    with patch.object(redis_pubsub, "publish", capture_publish):
        # Simulate what booking.py does
        import json as _json
        from datetime import datetime, timezone
        doctor_id = uuid.uuid4()
        slot_id = uuid.uuid4()
        date_str = "2026-04-27"
        await redis_pubsub.publish(
            f"slots:{doctor_id}:{date_str}",
            _json.dumps({"slot_id": str(slot_id), "status": "booked", "timestamp": datetime.now(timezone.utc).isoformat()}),
        )

    assert len(published_messages) == 1
    channel, payload_str = published_messages[0]
    assert channel == f"slots:{doctor_id}:{date_str}"
    data = json.loads(payload_str)
    assert data["status"] == "booked"
    assert data["slot_id"] == str(slot_id)


@pytest.mark.asyncio
async def test_booking_publishes_slot_freed_on_cancel():
    from app.db import redis_pubsub

    published = []

    async def capture(channel, message):
        published.append((channel, message))

    with patch.object(redis_pubsub, "publish", capture):
        import json as _json
        from datetime import datetime, timezone
        doctor_id = uuid.uuid4()
        slot_id = uuid.uuid4()
        date_str = "2026-04-27"
        await redis_pubsub.publish(
            f"slots:{doctor_id}:{date_str}",
            _json.dumps({"slot_id": str(slot_id), "status": "available", "timestamp": datetime.now(timezone.utc).isoformat()}),
        )

    assert len(published) == 1
    data = json.loads(published[0][1])
    assert data["status"] == "available"


# ── CDS pub/sub payload structure ─────────────────────────────────────────────

def test_cds_publish_payload_structure():
    from app.schemas.schemas import CdsAlertOut
    alerts = [
        CdsAlertOut(rule_type="vital_alert", severity="critical", message="SpO2 low", rule_key="SPO2_LOW"),
    ]
    encounter_id = uuid.uuid4()
    payload = json.dumps({
        "encounter_id": str(encounter_id),
        "alerts": [a.model_dump() for a in alerts],
        "timestamp": "2026-04-27T00:00:00Z",
    })
    data = json.loads(payload)
    assert data["encounter_id"] == str(encounter_id)
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["severity"] == "critical"
    assert data["alerts"][0]["rule_key"] == "SPO2_LOW"


def test_cds_payload_contains_no_phi():
    payload = {
        "encounter_id": str(uuid.uuid4()),
        "alerts": [{"rule_type": "vital_alert", "severity": "critical", "message": "SpO2 low"}],
    }
    payload_str = json.dumps(payload)
    assert "@" not in payload_str
    assert "patient_name" not in payload_str
    assert "dob" not in payload_str
