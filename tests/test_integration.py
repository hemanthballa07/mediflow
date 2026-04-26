"""
Integration tests — require live Docker stack (make up && make seed).
Run: docker compose exec api pytest tests/test_integration.py -v
"""
import uuid
import os
from datetime import date, timedelta
import pytest
import httpx
import redis as sync_redis

BASE = "http://localhost:8000/api/v1"
ADMIN_KEY = "changeme-replace-in-prod-xxxxxxxxxx"
_REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def flush_rate_limits():
    """Clear Redis rate limit counters before the test session."""
    r = sync_redis.from_url(_REDIS_URL, decode_responses=True)
    r.flushdb()
    r.close()

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
    assert body["status"] == "scheduled"
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


# ── Phase 3: Clinical ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def doctor_token():
    r = httpx.post(f"{BASE}/auth/login", json={"email": "doctor@mediflow.dev", "password": "doctor123"})
    assert r.status_code == 200, f"Doctor login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def doctor_id(doctor_token):
    """Returns the Doctor profile id (doctors.id, not users.id)."""
    r = httpx.get(f"{BASE}/catalog/doctors", headers={"Authorization": f"Bearer {doctor_token}"})
    assert r.status_code == 200, r.text
    doctors = r.json()
    assert doctors, "No doctors in catalog — run make seed"
    return doctors[0]["id"]


@pytest.fixture(scope="module")
def patient_id(patient_token):
    r = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {patient_token}"})
    assert r.status_code == 200
    return r.json()["id"]


def test_patient_cannot_access_own_chart(patient_token, patient_id):
    """Patients are blocked from GET /patients/{id}/chart with 403."""
    r = httpx.get(
        f"{BASE}/patients/{patient_id}/chart",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert r.status_code == 403


def test_doctor_cannot_see_unrelated_patient_chart(doctor_token):
    """Doctor gets 404 for a patient they have no booking with."""
    unknown_patient_id = str(uuid.uuid4())
    r = httpx.get(
        f"{BASE}/patients/{unknown_patient_id}/chart",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert r.status_code == 404


def test_clinical_full_workflow(doctor_token, patient_token, doctor_id, patient_id):
    """
    Full Phase 3 workflow:
    - Book an appointment to establish doctor-patient link
    - Doctor creates encounter
    - Doctor adds vitals, diagnosis, prescription
    - Doctor adds allergy + problem to patient record
    - Doctor reads chart — all data present
    - Patient reading chart still blocked
    """
    doc_headers = {"Authorization": f"Bearer {doctor_token}"}
    pat_headers = {"Authorization": f"Bearer {patient_token}"}

    # Fetch a fresh available slot (independent of other test's slot)
    r = httpx.get(
        f"{BASE}/admin/slots",
        headers={"X-Admin-Api-Key": ADMIN_KEY},
        params={"slot_status": "available"},
    )
    assert r.status_code == 200, r.text
    cutoff = (date.today() + timedelta(days=2)).isoformat()
    far_slots = [s for s in r.json() if s["date"] >= cutoff]
    assert far_slots, "No available slots — run make seed"
    slot_id = far_slots[0]["id"]

    # Book slot to create doctor-patient relationship
    r = httpx.post(
        f"{BASE}/bookings",
        json={"slot_id": slot_id},
        headers={**pat_headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 201, f"Booking failed: {r.text}"

    # Create encounter
    r = httpx.post(
        f"{BASE}/encounters",
        json={
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "encounter_type": "office_visit",
            "chief_complaint": "Annual checkup",
            "encounter_date": date.today().isoformat(),
        },
        headers=doc_headers,
    )
    assert r.status_code == 201, f"Create encounter failed: {r.text}"
    encounter = r.json()
    encounter_id = encounter["id"]
    assert encounter["encounter_type"] == "office_visit"
    assert encounter["status"] == "open"

    # Add vitals
    r = httpx.post(
        f"{BASE}/encounters/{encounter_id}/vitals",
        json={
            "bp_systolic": 122,
            "bp_diastolic": 78,
            "heart_rate": 68,
            "temperature_f": 98.6,
            "weight_kg": 75.5,
            "height_cm": 178.0,
            "spo2": 99.0,
            "respiratory_rate": 16,
        },
        headers=doc_headers,
    )
    assert r.status_code == 201, f"Add vitals failed: {r.text}"
    vitals = r.json()
    assert vitals["bp_systolic"] == 122
    assert vitals["encounter_id"] == encounter_id

    # Add ICD-10 diagnosis
    r = httpx.post(
        f"{BASE}/encounters/{encounter_id}/diagnoses",
        json={
            "icd10_code": "Z00.00",
            "description": "Encounter for general adult medical examination without abnormal findings",
            "diagnosis_type": "primary",
        },
        headers=doc_headers,
    )
    assert r.status_code == 201, f"Add diagnosis failed: {r.text}"
    dx = r.json()
    assert dx["icd10_code"] == "Z00.00"
    assert dx["encounter_id"] == encounter_id

    # Add prescription
    r = httpx.post(
        f"{BASE}/encounters/{encounter_id}/prescriptions",
        json={
            "drug_name": "Lisinopril",
            "dose": "10mg",
            "frequency": "once daily",
            "route": "oral",
            "start_date": date.today().isoformat(),
            "refills": 2,
        },
        headers=doc_headers,
    )
    assert r.status_code == 201, f"Add prescription failed: {r.text}"
    rx = r.json()
    assert rx["drug_name"] == "Lisinopril"
    assert rx["status"] == "active"

    # Add allergy
    r = httpx.post(
        f"{BASE}/patients/{patient_id}/allergies",
        json={
            "allergen": "Sulfonamides",
            "reaction": "Rash",
            "severity": "moderate",
        },
        headers=doc_headers,
    )
    assert r.status_code == 201, f"Add allergy failed: {r.text}"
    allergy = r.json()
    assert allergy["allergen"] == "Sulfonamides"
    assert allergy["severity"] == "moderate"

    # Add problem list entry
    r = httpx.post(
        f"{BASE}/patients/{patient_id}/problems",
        json={
            "icd10_code": "I10",
            "description": "Essential hypertension",
            "status": "active",
        },
        headers=doc_headers,
    )
    assert r.status_code == 201, f"Add problem failed: {r.text}"
    problem = r.json()
    assert problem["icd10_code"] == "I10"
    assert problem["status"] == "active"

    # Doctor reads full chart
    r = httpx.get(
        f"{BASE}/patients/{patient_id}/chart",
        headers=doc_headers,
    )
    assert r.status_code == 200, f"Chart read failed: {r.text}"
    chart = r.json()
    assert chart["patient_id"] == patient_id

    enc_ids = [e["id"] for e in chart["encounters"]]
    assert encounter_id in enc_ids

    target_enc = next(e for e in chart["encounters"] if e["id"] == encounter_id)
    assert any(v["bp_systolic"] == 122 for v in target_enc["vitals"])
    assert any(d["icd10_code"] == "Z00.00" for d in target_enc["diagnoses"])
    assert any(p["drug_name"] == "Lisinopril" for p in target_enc["prescriptions"])

    assert any(a["allergen"] == "Sulfonamides" for a in chart["allergies"])
    assert any(pr["icd10_code"] == "I10" for pr in chart["problem_list"])

    # Patient still blocked
    r = httpx.get(
        f"{BASE}/patients/{patient_id}/chart",
        headers=pat_headers,
    )
    assert r.status_code == 403
