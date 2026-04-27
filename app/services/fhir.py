from datetime import datetime, timezone
from app.models.models import (
    User, Doctor, Booking, Encounter, Vital, Diagnosis, Prescription, LabReport,
)


def _ts(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def user_to_patient(user: User) -> dict:
    return {
        "resourceType": "Patient",
        "id": str(user.id),
        "meta": {"lastUpdated": _ts(user.created_at)},
        "name": [{"text": user.name}],
        "telecom": [{"system": "email", "value": user.email}],
        "active": True,
    }


def doctor_to_practitioner(doctor: Doctor, user: User) -> dict:
    return {
        "resourceType": "Practitioner",
        "id": str(doctor.id),
        "meta": {"lastUpdated": _ts(doctor.created_at)},
        "name": [{"text": user.name}],
        "qualification": [{"code": {"text": doctor.specialty}}],
        "active": True,
    }


def booking_to_appointment(booking: Booking) -> dict:
    _status_map = {
        "scheduled": "booked",
        "checked_in": "arrived",
        "in_progress": "fulfilled",
        "completed": "fulfilled",
        "cancelled": "cancelled",
        "no_show": "noshow",
    }
    fhir_status = _status_map.get(booking.status, "pending")
    start_dt = None
    if booking.slot and booking.slot.date and booking.slot.start_time:
        from datetime import datetime, timezone
        start_dt = datetime(
            booking.slot.date.year,
            booking.slot.date.month,
            booking.slot.date.day,
            booking.slot.start_time.hour,
            booking.slot.start_time.minute,
            tzinfo=timezone.utc,
        ).isoformat()
    return {
        "resourceType": "Appointment",
        "id": str(booking.id),
        "meta": {"lastUpdated": _ts(booking.created_at)},
        "status": fhir_status,
        "participant": [
            {"actor": {"reference": f"Patient/{booking.user_id}"}, "status": "accepted"},
        ],
        "start": start_dt,
        "description": booking.reason_for_visit,
    }


def encounter_to_fhir(encounter: Encounter) -> dict:
    _type_map = {
        "office_visit": "AMB",
        "telehealth": "VR",
        "emergency": "EMER",
        "procedure": "IMP",
        "walk_in": "AMB",
    }
    _status_map = {
        "open": "in-progress",
        "completed": "finished",
        "cancelled": "cancelled",
    }
    return {
        "resourceType": "Encounter",
        "id": str(encounter.id),
        "meta": {"lastUpdated": _ts(encounter.updated_at)},
        "status": _status_map.get(encounter.status, "unknown"),
        "class": {"code": _type_map.get(encounter.encounter_type, "AMB")},
        "subject": {"reference": f"Patient/{encounter.patient_id}"},
        "participant": [{"individual": {"reference": f"Practitioner/{encounter.doctor_id}"}}],
        "period": {"start": str(encounter.encounter_date)},
        "reasonCode": [{"text": encounter.chief_complaint}] if encounter.chief_complaint else [],
    }


def vital_to_observations(vital: Vital) -> list[dict]:
    obs = []
    base = {
        "resourceType": "Observation",
        "meta": {"lastUpdated": _ts(vital.created_at)},
        "status": "final",
        "subject": {"reference": f"Patient/{vital.patient_id}"},
        "encounter": {"reference": f"Encounter/{vital.encounter_id}"},
        "effectiveDateTime": _ts(vital.recorded_at),
    }

    if vital.bp_systolic is not None and vital.bp_diastolic is not None:
        obs.append({
            **base,
            "id": f"{vital.id}-bp",
            "code": {"coding": [{"system": "http://loinc.org", "code": "55284-4", "display": "Blood pressure"}]},
            "component": [
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic BP"}]},
                    "valueQuantity": {"value": vital.bp_systolic, "unit": "mmHg"},
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic BP"}]},
                    "valueQuantity": {"value": vital.bp_diastolic, "unit": "mmHg"},
                },
            ],
        })

    if vital.heart_rate is not None:
        obs.append({
            **base,
            "id": f"{vital.id}-hr",
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}]},
            "valueQuantity": {"value": vital.heart_rate, "unit": "/min"},
        })

    if vital.temperature_f is not None:
        obs.append({
            **base,
            "id": f"{vital.id}-temp",
            "code": {"coding": [{"system": "http://loinc.org", "code": "8310-5", "display": "Body temperature"}]},
            "valueQuantity": {"value": float(vital.temperature_f), "unit": "[degF]"},
        })

    if vital.spo2 is not None:
        obs.append({
            **base,
            "id": f"{vital.id}-spo2",
            "code": {"coding": [{"system": "http://loinc.org", "code": "2708-6", "display": "Oxygen saturation"}]},
            "valueQuantity": {"value": float(vital.spo2), "unit": "%"},
        })

    if vital.respiratory_rate is not None:
        obs.append({
            **base,
            "id": f"{vital.id}-rr",
            "code": {"coding": [{"system": "http://loinc.org", "code": "9279-1", "display": "Respiratory rate"}]},
            "valueQuantity": {"value": vital.respiratory_rate, "unit": "/min"},
        })

    if vital.weight_kg is not None:
        obs.append({
            **base,
            "id": f"{vital.id}-wt",
            "code": {"coding": [{"system": "http://loinc.org", "code": "29463-7", "display": "Body weight"}]},
            "valueQuantity": {"value": float(vital.weight_kg), "unit": "kg"},
        })

    if vital.height_cm is not None:
        obs.append({
            **base,
            "id": f"{vital.id}-ht",
            "code": {"coding": [{"system": "http://loinc.org", "code": "8302-2", "display": "Body height"}]},
            "valueQuantity": {"value": float(vital.height_cm), "unit": "cm"},
        })

    return obs


def diagnosis_to_condition(dx: Diagnosis) -> dict:
    return {
        "resourceType": "Condition",
        "id": str(dx.id),
        "meta": {"lastUpdated": _ts(dx.created_at)},
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "resolved" if dx.resolved else "active"}]
        },
        "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": dx.icd10_code}],
                 "text": dx.description},
        "subject": {"reference": f"Patient/{dx.patient_id}"},
        "encounter": {"reference": f"Encounter/{dx.encounter_id}"},
        "onsetDateTime": str(dx.onset_date) if dx.onset_date else None,
        "category": [{"coding": [{"code": dx.diagnosis_type}]}],
    }


def prescription_to_medication_request(rx: Prescription) -> dict:
    _status_map = {
        "active": "active",
        "completed": "completed",
        "cancelled": "cancelled",
        "on_hold": "on-hold",
    }
    return {
        "resourceType": "MedicationRequest",
        "id": str(rx.id),
        "meta": {"lastUpdated": _ts(rx.created_at)},
        "status": _status_map.get(rx.status, "unknown"),
        "intent": "order",
        "medicationCodeableConcept": {"text": rx.drug_name},
        "subject": {"reference": f"Patient/{rx.patient_id}"},
        "encounter": {"reference": f"Encounter/{rx.encounter_id}"},
        "authoredOn": str(rx.start_date),
        "dosageInstruction": [{"text": f"{rx.dose} {rx.frequency}", "route": {"text": rx.route}}],
        "dispenseRequest": {
            "numberOfRepeatsAllowed": rx.refills,
            "validityPeriod": {"start": str(rx.start_date), "end": str(rx.end_date) if rx.end_date else None},
        },
    }


def lab_report_to_diagnostic_report(report: LabReport) -> dict:
    _status_map = {
        "PENDING": "registered",
        "READY": "final",
        "ARCHIVED": "entered-in-error",
    }
    return {
        "resourceType": "DiagnosticReport",
        "id": str(report.id),
        "meta": {"lastUpdated": _ts(report.created_at)},
        "status": _status_map.get(report.status, "unknown"),
        "code": {"text": report.report_type},
        "subject": {"reference": f"Patient/{report.patient_id}"},
        "effectiveDateTime": _ts(report.created_at),
        "conclusion": report.data,
    }


def make_bundle(resource_type: str, entries: list[dict]) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(entries),
        "entry": [{"resource": e} for e in entries],
    }
