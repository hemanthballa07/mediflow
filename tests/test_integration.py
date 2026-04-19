"""
Integration tests — require live Docker stack (make up && make seed).
Run: .venv/bin/pytest tests/test_integration.py -v
"""
import uuid
import subprocess
from datetime import date, timedelta
import pytest
import httpx

BASE = "http://localhost:8000/api/v1"
ADMIN_KEY = "changeme-replace-in-prod-xxxxxxxxxx"


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def flush_rate_limits():
    """Clear Redis rate limit counters before the test session."""
    subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "FLUSHDB"],
        capture_output=True,
    )

@pytest.fixture(scope="module")
def patient_token():
    r = httpx.post(f"{BASE}/auth/login", json={"email": "patient@mediflow.dev", "password": "patient123"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def available_slot():
    r = httpx.get(
        f"{BASE}/admin/slots",
        headers={"X-Admin-Api-Key": ADMIN_KEY},
        params={"slot_status": "available"},
    )
    assert r.status_code == 200, r.text
    slots = r.json()
    cutoff = (date.today() + timedelta(days=2)).isoformat()
    far_slots = [s for s in slots if s["date"] >= cutoff]
    assert far_slots, "No slots ≥2 days from now — run make seed first"
    return far_slots[0]


# ── health ─────────────────────────────────────────────────────────────────────

def test_health():
    r = httpx.get("http://localhost:8000/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


# ── auth ───────────────────────────────────────────────────────────────────────

def test_login_wrong_password_returns_401():
    r = httpx.post(f"{BASE}/auth/login", json={"email": "patient@mediflow.dev", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_email_returns_401():
    r = httpx.post(f"{BASE}/auth/login", json={"email": "nobody@example.com", "password": "any"})
    assert r.status_code == 401


def test_me_returns_patient_profile(patient_token):
    r = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {patient_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "patient@mediflow.dev"
    assert body["role"] == "patient"


# ── bookings ───────────────────────────────────────────────────────────────────

def test_booking_missing_idempotency_key_returns_422(patient_token, available_slot):
    r = httpx.post(
        f"{BASE}/bookings",
        json={"slot_id": available_slot["id"]},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert r.status_code == 422


def test_full_booking_flow(patient_token, available_slot):
    headers = {"Authorization": f"Bearer {patient_token}"}
    slot_id = available_slot["id"]
    idem_key = str(uuid.uuid4())

    # Create booking → 201
    r = httpx.post(
        f"{BASE}/bookings",
        json={"slot_id": slot_id},
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    booking_id = body["id"]
    assert body["status"] == "active"
    assert body["slot_id"] == slot_id

    # Idempotency replay → 200, same booking_id
    r2 = httpx.post(
        f"{BASE}/bookings",
        json={"slot_id": slot_id},
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == booking_id

    # Cancel → 200
    r3 = httpx.delete(f"{BASE}/bookings/{booking_id}", headers=headers)
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "cancelled"

    # Cancel again → 409 already cancelled
    r4 = httpx.delete(f"{BASE}/bookings/{booking_id}", headers=headers)
    assert r4.status_code == 409


# ── reports ────────────────────────────────────────────────────────────────────

def test_report_list_own(patient_token):
    me = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {patient_token}"})
    patient_id = me.json()["id"]

    r = httpx.get(
        f"{BASE}/reports",
        params={"patient_id": patient_id},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert len(body["items"]) > 0


# ── admin ──────────────────────────────────────────────────────────────────────

def test_admin_slots_missing_key_returns_422():
    r = httpx.get(f"{BASE}/admin/slots")
    assert r.status_code == 422


def test_admin_slots_wrong_key_returns_401():
    r = httpx.get(f"{BASE}/admin/slots", headers={"X-Admin-Api-Key": "wrongkey"})
    assert r.status_code == 401


# ── logout ─────────────────────────────────────────────────────────────────────

def test_logout_revokes_refresh_token():
    # Login to get a fresh token pair
    r = httpx.post(f"{BASE}/auth/login", json={"email": "doctor@mediflow.dev", "password": "doctor123"})
    assert r.status_code == 200
    refresh_token = r.json()["refresh_token"]

    # Logout — revokes the family
    r2 = httpx.post(f"{BASE}/auth/logout", json={"refresh_token": refresh_token})
    assert r2.status_code == 200
    assert r2.json()["message"] == "Logged out successfully"

    # Attempt to use the revoked refresh token → 401
    r3 = httpx.post(f"{BASE}/auth/refresh", json={"refresh_token": refresh_token})
    assert r3.status_code == 401

    # Logout again (idempotent) → still 200
    r4 = httpx.post(f"{BASE}/auth/logout", json={"refresh_token": refresh_token})
    assert r4.status_code == 200
