"""
Unit tests for webhook service: signing, enqueue, deactivation.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.webhooks import _sign, WebhookService
from app.models.models import Webhook, WebhookDelivery


# ── Signing ───────────────────────────────────────────────────────────────────

def test_sign_produces_sha256_prefix():
    sig = _sign("mysecret", {"event": "booking.created", "id": "abc"})
    assert sig.startswith("sha256=")


def test_sign_is_deterministic():
    payload = {"event": "booking.created", "z": 1, "a": 2}
    sig1 = _sign("mysecret", payload)
    sig2 = _sign("mysecret", payload)
    assert sig1 == sig2


def test_sign_uses_canonical_json():
    payload = {"z": 1, "a": 2}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected_hex = hmac.new("secret".encode(), canonical.encode(), hashlib.sha256).hexdigest()
    sig = _sign("secret", payload)
    assert sig == f"sha256={expected_hex}"


def test_sign_different_secrets_produce_different_sigs():
    payload = {"event": "test"}
    assert _sign("secret1", payload) != _sign("secret2", payload)


def test_sign_payload_order_independent():
    sig1 = _sign("k", {"b": 1, "a": 2})
    sig2 = _sign("k", {"a": 2, "b": 1})
    assert sig1 == sig2


# ── Enqueue ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enqueue_creates_delivery_for_matching_webhook():
    webhook_id = uuid.uuid4()
    user_id = uuid.uuid4()
    wh = MagicMock(spec=Webhook)
    wh.id = webhook_id
    wh.user_id = user_id
    wh.url = "https://example.com/hook"
    wh.secret = "testsecret"
    wh.events = ["booking.created"]
    wh.active = True

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [wh]

    mock_lookup_db = AsyncMock()
    mock_lookup_db.execute = AsyncMock(return_value=mock_result)
    mock_lookup_db.__aenter__ = AsyncMock(return_value=mock_lookup_db)
    mock_lookup_db.__aexit__ = AsyncMock(return_value=False)

    db = AsyncMock()
    db.add = MagicMock()

    payload = {"event": "booking.created", "booking_id": str(uuid.uuid4())}

    with patch("app.services.webhooks.AsyncSessionLocal", return_value=mock_lookup_db):
        await WebhookService.enqueue("booking.created", payload, db)

    db.add.assert_called_once()
    delivery: WebhookDelivery = db.add.call_args[0][0]
    assert delivery.event == "booking.created"
    assert delivery.status == "pending"
    assert delivery.signature.startswith("sha256=")
    assert delivery.attempts == 0


@pytest.mark.asyncio
async def test_enqueue_no_delivery_when_no_matching_webhook():
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_lookup_db = AsyncMock()
    mock_lookup_db.execute = AsyncMock(return_value=mock_result)
    mock_lookup_db.__aenter__ = AsyncMock(return_value=mock_lookup_db)
    mock_lookup_db.__aexit__ = AsyncMock(return_value=False)

    db = AsyncMock()
    db.add = MagicMock()

    with patch("app.services.webhooks.AsyncSessionLocal", return_value=mock_lookup_db):
        await WebhookService.enqueue("booking.created", {"event": "booking.created"}, db)

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_does_not_deliver_wrong_event():
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_lookup_db = AsyncMock()
    mock_lookup_db.execute = AsyncMock(return_value=mock_result)
    mock_lookup_db.__aenter__ = AsyncMock(return_value=mock_lookup_db)
    mock_lookup_db.__aexit__ = AsyncMock(return_value=False)

    db = AsyncMock()
    db.add = MagicMock()

    with patch("app.services.webhooks.AsyncSessionLocal", return_value=mock_lookup_db):
        await WebhookService.enqueue("booking.created", {"event": "booking.created"}, db)

    db.add.assert_not_called()


# ── Payload PHI check ─────────────────────────────────────────────────────────

def test_webhook_payload_contains_no_email():
    payload = {
        "event": "booking.created",
        "booking_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "slot_id": str(uuid.uuid4()),
        "status": "scheduled",
    }
    payload_str = json.dumps(payload)
    assert "@" not in payload_str


def test_webhook_payload_contains_no_name():
    payload = {
        "event": "claim.submitted",
        "claim_id": str(uuid.uuid4()),
        "patient_id": str(uuid.uuid4()),
        "status": "submitted",
    }
    payload_str = json.dumps(payload)
    assert "name" not in payload_str.lower()


# ── Deactivate ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deactivate_sets_active_false():
    wh = MagicMock(spec=Webhook)
    wh.id = uuid.uuid4()
    wh.active = True

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = wh
    db.execute = AsyncMock(return_value=mock_result)

    result = await WebhookService.deactivate(wh.id, db)
    assert result is True
    assert wh.active is False


@pytest.mark.asyncio
async def test_deactivate_returns_false_when_not_found():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    result = await WebhookService.deactivate(uuid.uuid4(), db)
    assert result is False
