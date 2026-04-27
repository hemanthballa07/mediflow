import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_read_db
from app.api.v1.deps import get_current_user
from app.models.models import User, Doctor, Booking, Slot, Encounter, Vital, Diagnosis, Prescription, LabReport
from app.services import fhir as fhir_svc

router = APIRouter(prefix="/fhir/r4", tags=["fhir"])

_CAPABILITY = {
    "resourceType": "CapabilityStatement",
    "fhirVersion": "4.0.1",
    "kind": "instance",
    "format": ["json"],
    "status": "active",
    "rest": [
        {
            "mode": "server",
            "resource": [
                {
                    "type": t,
                    "interaction": [{"code": "read"}, {"code": "search-type"}],
                    "searchParam": [{"name": "patient", "type": "reference"}],
                }
                for t in [
                    "Patient", "Practitioner", "Appointment", "Encounter",
                    "Observation", "Condition", "MedicationRequest", "DiagnosticReport",
                ]
            ],
        }
    ],
}


@router.get("/metadata")
async def capability_statement():
    return _CAPABILITY


# ── Patient ───────────────────────────────────────────────────────────────────

@router.get("/Patient/{patient_id}")
async def get_patient(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    user = await _get_patient_or_404(patient_id, current_user, db)
    return fhir_svc.user_to_patient(user)


@router.get("/Patient")
async def search_patients(
    patient: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    user = await _get_patient_or_404(patient, current_user, db)
    return fhir_svc.make_bundle("Patient", [fhir_svc.user_to_patient(user)])


async def _get_patient_or_404(patient_id: uuid.UUID, requester: User, db: AsyncSession) -> User:
    if requester.role == "patient" and requester.id != patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")
    result = await db.execute(select(User).where(User.id == patient_id, User.role == "patient"))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")
    if requester.role == "doctor":
        doctor_res = await db.execute(select(Doctor).where(Doctor.user_id == requester.id))
        doctor = doctor_res.scalar_one_or_none()
        if doctor:
            link = await db.execute(
                select(Booking).join(Slot, Booking.slot_id == Slot.id)
                .where(Slot.doctor_id == doctor.id, Booking.user_id == patient_id).limit(1)
            )
            if link.scalar_one_or_none() is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return user


# ── Practitioner ──────────────────────────────────────────────────────────────

@router.get("/Practitioner/{practitioner_id}")
async def get_practitioner(
    practitioner_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    doctor, user = await _get_practitioner_or_404(practitioner_id, db)
    return fhir_svc.doctor_to_practitioner(doctor, user)


@router.get("/Practitioner")
async def search_practitioners(
    patient: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    q = (
        select(Doctor)
        .join(Slot, Doctor.id == Slot.doctor_id)
        .join(Booking, Booking.slot_id == Slot.id)
        .where(Booking.user_id == patient)
        .distinct()
    )
    result = await db.execute(q)
    doctors = result.scalars().all()
    entries = []
    for doc in doctors:
        u_res = await db.execute(select(User).where(User.id == doc.user_id))
        u = u_res.scalar_one_or_none()
        if u:
            entries.append(fhir_svc.doctor_to_practitioner(doc, u))
    return fhir_svc.make_bundle("Practitioner", entries)


async def _get_practitioner_or_404(doctor_id: uuid.UUID, db: AsyncSession):
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Practitioner not found")
    u_res = await db.execute(select(User).where(User.id == doctor.user_id))
    user = u_res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Practitioner not found")
    return doctor, user


# ── Appointment ───────────────────────────────────────────────────────────────

@router.get("/Appointment/{appointment_id}")
async def get_appointment(
    appointment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    booking = await _get_booking_or_404(appointment_id, current_user, db)
    return fhir_svc.booking_to_appointment(booking)


@router.get("/Appointment")
async def search_appointments(
    patient: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    if current_user.role == "patient" and current_user.id != patient:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
    result = await db.execute(
        select(Booking)
        .options(selectinload(Booking.slot))
        .where(Booking.user_id == patient)
        .order_by(Booking.created_at.desc())
    )
    bookings = result.scalars().all()
    return fhir_svc.make_bundle("Appointment", [fhir_svc.booking_to_appointment(b) for b in bookings])


async def _get_booking_or_404(booking_id: uuid.UUID, requester: User, db: AsyncSession) -> Booking:
    result = await db.execute(
        select(Booking).options(selectinload(Booking.slot)).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    if requester.role == "patient" and booking.user_id != requester.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return booking


# ── Encounter ─────────────────────────────────────────────────────────────────

@router.get("/Encounter/{encounter_id}")
async def get_encounter(
    encounter_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    enc = await _get_encounter_or_404(encounter_id, current_user, db)
    return fhir_svc.encounter_to_fhir(enc)


@router.get("/Encounter")
async def search_encounters(
    patient: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    _assert_patient_access(patient, current_user)
    result = await db.execute(
        select(Encounter).where(Encounter.patient_id == patient).order_by(Encounter.encounter_date.desc())
    )
    encounters = result.scalars().all()
    return fhir_svc.make_bundle("Encounter", [fhir_svc.encounter_to_fhir(e) for e in encounters])


async def _get_encounter_or_404(encounter_id: uuid.UUID, requester: User, db: AsyncSession) -> Encounter:
    result = await db.execute(select(Encounter).where(Encounter.id == encounter_id))
    enc = result.scalar_one_or_none()
    if enc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Encounter not found")
    if requester.role == "patient" and enc.patient_id != requester.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Encounter not found")
    return enc


# ── Observation (Vitals) ──────────────────────────────────────────────────────

@router.get("/Observation/{vital_id}")
async def get_observation(
    vital_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    raw_id = vital_id.split("-")[0]
    try:
        uid = uuid.UUID(raw_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Observation not found")
    result = await db.execute(select(Vital).where(Vital.id == uid))
    vital = result.scalar_one_or_none()
    if vital is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Observation not found")
    if current_user.role == "patient" and vital.patient_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Observation not found")
    obs = fhir_svc.vital_to_observations(vital)
    if not obs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Observation not found")
    return obs[0]


@router.get("/Observation")
async def search_observations(
    patient: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    _assert_patient_access(patient, current_user)
    result = await db.execute(select(Vital).where(Vital.patient_id == patient))
    vitals = result.scalars().all()
    entries = []
    for v in vitals:
        entries.extend(fhir_svc.vital_to_observations(v))
    return fhir_svc.make_bundle("Observation", entries)


# ── Condition (Diagnoses) ─────────────────────────────────────────────────────

@router.get("/Condition/{condition_id}")
async def get_condition(
    condition_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    result = await db.execute(select(Diagnosis).where(Diagnosis.id == condition_id))
    dx = result.scalar_one_or_none()
    if dx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Condition not found")
    if current_user.role == "patient" and dx.patient_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Condition not found")
    return fhir_svc.diagnosis_to_condition(dx)


@router.get("/Condition")
async def search_conditions(
    patient: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    _assert_patient_access(patient, current_user)
    result = await db.execute(select(Diagnosis).where(Diagnosis.patient_id == patient))
    dxs = result.scalars().all()
    return fhir_svc.make_bundle("Condition", [fhir_svc.diagnosis_to_condition(d) for d in dxs])


# ── MedicationRequest (Prescriptions) ────────────────────────────────────────

@router.get("/MedicationRequest/{rx_id}")
async def get_medication_request(
    rx_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    result = await db.execute(select(Prescription).where(Prescription.id == rx_id))
    rx = result.scalar_one_or_none()
    if rx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="MedicationRequest not found")
    if current_user.role == "patient" and rx.patient_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="MedicationRequest not found")
    return fhir_svc.prescription_to_medication_request(rx)


@router.get("/MedicationRequest")
async def search_medication_requests(
    patient: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    _assert_patient_access(patient, current_user)
    result = await db.execute(select(Prescription).where(Prescription.patient_id == patient))
    rxs = result.scalars().all()
    return fhir_svc.make_bundle("MedicationRequest", [fhir_svc.prescription_to_medication_request(r) for r in rxs])


# ── DiagnosticReport (Lab Reports) ───────────────────────────────────────────

@router.get("/DiagnosticReport/{report_id}")
async def get_diagnostic_report(
    report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    result = await db.execute(select(LabReport).where(LabReport.id == report_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="DiagnosticReport not found")
    if current_user.role == "patient" and report.patient_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="DiagnosticReport not found")
    return fhir_svc.lab_report_to_diagnostic_report(report)


@router.get("/DiagnosticReport")
async def search_diagnostic_reports(
    patient: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    _assert_patient_access(patient, current_user)
    result = await db.execute(select(LabReport).where(LabReport.patient_id == patient))
    reports = result.scalars().all()
    return fhir_svc.make_bundle("DiagnosticReport", [fhir_svc.lab_report_to_diagnostic_report(r) for r in reports])


# ── helpers ───────────────────────────────────────────────────────────────────

def _assert_patient_access(patient_id: uuid.UUID, requester: User) -> None:
    if requester.role == "patient" and requester.id != patient_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
