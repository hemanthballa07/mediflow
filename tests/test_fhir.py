"""
Unit tests for FHIR R4 mappers and router logic.
"""
import uuid
from datetime import datetime, timezone, date, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import fhir as fhir_svc
from app.models.models import User, Doctor, Booking, Slot, Encounter, Vital, Diagnosis, Prescription, LabReport


def _make_user(**kw):
    u = MagicMock(spec=User)
    u.id = kw.get("id", uuid.uuid4())
    u.name = kw.get("name", "Jane Doe")
    u.email = kw.get("email", "jane@example.com")
    u.created_at = kw.get("created_at", datetime(2024, 1, 15, tzinfo=timezone.utc))
    u.role = kw.get("role", "patient")
    return u


def _make_doctor(**kw):
    d = MagicMock(spec=Doctor)
    d.id = kw.get("id", uuid.uuid4())
    d.user_id = kw.get("user_id", uuid.uuid4())
    d.specialty = kw.get("specialty", "Cardiology")
    d.created_at = kw.get("created_at", datetime(2024, 1, 15, tzinfo=timezone.utc))
    return d


def _make_slot(**kw):
    s = MagicMock(spec=Slot)
    s.date = kw.get("date", date(2024, 3, 10))
    s.start_time = kw.get("start_time", time(9, 0))
    s.end_time = kw.get("end_time", time(9, 30))
    return s


def _make_booking(**kw):
    b = MagicMock(spec=Booking)
    b.id = kw.get("id", uuid.uuid4())
    b.user_id = kw.get("user_id", uuid.uuid4())
    b.status = kw.get("status", "scheduled")
    b.reason_for_visit = kw.get("reason_for_visit", None)
    b.created_at = kw.get("created_at", datetime(2024, 1, 15, tzinfo=timezone.utc))
    b.slot = kw.get("slot", _make_slot())
    return b


def _make_encounter(**kw):
    e = MagicMock(spec=Encounter)
    e.id = kw.get("id", uuid.uuid4())
    e.patient_id = kw.get("patient_id", uuid.uuid4())
    e.doctor_id = kw.get("doctor_id", uuid.uuid4())
    e.encounter_type = kw.get("encounter_type", "office_visit")
    e.status = kw.get("status", "open")
    e.chief_complaint = kw.get("chief_complaint", "Chest pain")
    e.encounter_date = kw.get("encounter_date", date(2024, 3, 10))
    e.updated_at = kw.get("updated_at", datetime(2024, 1, 15, tzinfo=timezone.utc))
    return e


def _make_vital(**kw):
    v = MagicMock(spec=Vital)
    v.id = kw.get("id", uuid.uuid4())
    v.encounter_id = kw.get("encounter_id", uuid.uuid4())
    v.patient_id = kw.get("patient_id", uuid.uuid4())
    v.bp_systolic = kw.get("bp_systolic", 120)
    v.bp_diastolic = kw.get("bp_diastolic", 80)
    v.heart_rate = kw.get("heart_rate", 72)
    v.temperature_f = kw.get("temperature_f", None)
    v.spo2 = kw.get("spo2", None)
    v.respiratory_rate = kw.get("respiratory_rate", None)
    v.weight_kg = kw.get("weight_kg", None)
    v.height_cm = kw.get("height_cm", None)
    v.recorded_at = kw.get("recorded_at", datetime(2024, 1, 15, tzinfo=timezone.utc))
    v.created_at = kw.get("created_at", datetime(2024, 1, 15, tzinfo=timezone.utc))
    return v


# ── Patient mapper ────────────────────────────────────────────────────────────

def test_user_to_patient_resource_type():
    user = _make_user()
    result = fhir_svc.user_to_patient(user)
    assert result["resourceType"] == "Patient"


def test_user_to_patient_id():
    uid = uuid.uuid4()
    user = _make_user(id=uid)
    result = fhir_svc.user_to_patient(user)
    assert result["id"] == str(uid)


def test_user_to_patient_meta_last_updated():
    dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    user = _make_user(created_at=dt)
    result = fhir_svc.user_to_patient(user)
    assert result["meta"]["lastUpdated"] is not None
    assert "2024-06-01" in result["meta"]["lastUpdated"]


# ── Practitioner mapper ───────────────────────────────────────────────────────

def test_doctor_to_practitioner_resource_type():
    doctor = _make_doctor()
    user = _make_user()
    result = fhir_svc.doctor_to_practitioner(doctor, user)
    assert result["resourceType"] == "Practitioner"
    assert result["id"] == str(doctor.id)


def test_doctor_to_practitioner_specialty():
    doctor = _make_doctor(specialty="Neurology")
    user = _make_user()
    result = fhir_svc.doctor_to_practitioner(doctor, user)
    assert result["qualification"][0]["code"]["text"] == "Neurology"


# ── Appointment mapper ────────────────────────────────────────────────────────

def test_booking_to_appointment_status_mapping():
    b = _make_booking(status="scheduled")
    result = fhir_svc.booking_to_appointment(b)
    assert result["resourceType"] == "Appointment"
    assert result["status"] == "booked"


def test_booking_to_appointment_cancelled():
    b = _make_booking(status="cancelled")
    result = fhir_svc.booking_to_appointment(b)
    assert result["status"] == "cancelled"


def test_booking_to_appointment_start_date():
    slot = _make_slot(date=date(2025, 5, 10), start_time=time(14, 30))
    b = _make_booking(slot=slot)
    result = fhir_svc.booking_to_appointment(b)
    assert result["start"] is not None
    assert "2025-05-10" in result["start"]


# ── Encounter mapper ──────────────────────────────────────────────────────────

def test_encounter_to_fhir_resource_type():
    enc = _make_encounter()
    result = fhir_svc.encounter_to_fhir(enc)
    assert result["resourceType"] == "Encounter"
    assert result["status"] == "in-progress"


def test_encounter_to_fhir_completed_status():
    enc = _make_encounter(status="completed")
    result = fhir_svc.encounter_to_fhir(enc)
    assert result["status"] == "finished"


# ── Vital → Observation BP component ─────────────────────────────────────────

def test_vital_to_observations_bp_component():
    vital = _make_vital(bp_systolic=130, bp_diastolic=85, heart_rate=None)
    obs = fhir_svc.vital_to_observations(vital)
    bp_obs = next((o for o in obs if "component" in o), None)
    assert bp_obs is not None
    assert bp_obs["resourceType"] == "Observation"
    assert len(bp_obs["component"]) == 2
    codes = {c["code"]["coding"][0]["code"] for c in bp_obs["component"]}
    assert "8480-6" in codes
    assert "8462-4" in codes


def test_vital_to_observations_heart_rate():
    vital = _make_vital(bp_systolic=None, bp_diastolic=None, heart_rate=88)
    obs = fhir_svc.vital_to_observations(vital)
    assert any(o.get("code", {}).get("coding", [{}])[0].get("code") == "8867-4" for o in obs)


def test_vital_to_observations_empty_returns_no_obs():
    vital = _make_vital(bp_systolic=None, bp_diastolic=None, heart_rate=None)
    obs = fhir_svc.vital_to_observations(vital)
    assert obs == []


# ── Diagnosis → Condition ─────────────────────────────────────────────────────

def test_diagnosis_to_condition_resource_type():
    dx = MagicMock(spec=Diagnosis)
    dx.id = uuid.uuid4()
    dx.icd10_code = "I10"
    dx.description = "Hypertension"
    dx.diagnosis_type = "primary"
    dx.onset_date = None
    dx.resolved = False
    dx.patient_id = uuid.uuid4()
    dx.encounter_id = uuid.uuid4()
    dx.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    result = fhir_svc.diagnosis_to_condition(dx)
    assert result["resourceType"] == "Condition"
    assert result["code"]["coding"][0]["code"] == "I10"


def test_diagnosis_to_condition_resolved():
    dx = MagicMock(spec=Diagnosis)
    dx.id = uuid.uuid4()
    dx.icd10_code = "J06.9"
    dx.description = "URI"
    dx.diagnosis_type = "primary"
    dx.onset_date = None
    dx.resolved = True
    dx.patient_id = uuid.uuid4()
    dx.encounter_id = uuid.uuid4()
    dx.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    result = fhir_svc.diagnosis_to_condition(dx)
    assert result["clinicalStatus"]["coding"][0]["code"] == "resolved"


# ── MedicationRequest ─────────────────────────────────────────────────────────

def test_prescription_to_medication_request():
    rx = MagicMock(spec=Prescription)
    rx.id = uuid.uuid4()
    rx.drug_name = "Lisinopril"
    rx.dose = "10mg"
    rx.frequency = "daily"
    rx.route = "oral"
    rx.start_date = date(2024, 1, 1)
    rx.end_date = None
    rx.refills = 2
    rx.status = "active"
    rx.patient_id = uuid.uuid4()
    rx.encounter_id = uuid.uuid4()
    rx.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    result = fhir_svc.prescription_to_medication_request(rx)
    assert result["resourceType"] == "MedicationRequest"
    assert result["status"] == "active"
    assert result["medicationCodeableConcept"]["text"] == "Lisinopril"


# ── DiagnosticReport ──────────────────────────────────────────────────────────

def test_lab_report_to_diagnostic_report():
    report = MagicMock(spec=LabReport)
    report.id = uuid.uuid4()
    report.report_type = "blood"
    report.status = "READY"
    report.data = "All values normal"
    report.patient_id = uuid.uuid4()
    report.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    result = fhir_svc.lab_report_to_diagnostic_report(report)
    assert result["resourceType"] == "DiagnosticReport"
    assert result["status"] == "final"
    assert result["conclusion"] == "All values normal"


# ── Bundle ────────────────────────────────────────────────────────────────────

def test_make_bundle_structure():
    entries = [{"resourceType": "Patient", "id": str(uuid.uuid4())}]
    bundle = fhir_svc.make_bundle("Patient", entries)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "searchset"
    assert bundle["total"] == 1
    assert bundle["entry"][0]["resource"] == entries[0]


def test_make_bundle_empty():
    bundle = fhir_svc.make_bundle("Patient", [])
    assert bundle["total"] == 0
    assert bundle["entry"] == []
