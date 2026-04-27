import uuid
from datetime import datetime, timezone, date as date_type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.models import (
    Encounter, Vital, Diagnosis, Prescription, Allergy, ProblemList,
    Doctor, Booking, Slot, User,
)
from app.services.webhooks import WebhookService
from app.schemas.schemas import (
    EncounterCreate, VitalCreate, DiagnosisCreate, PrescriptionCreate,
    AllergyCreate, ProblemCreate, PatientChartOut,
    EncounterWithDetails, VitalOut, DiagnosisOut, PrescriptionOut,
    AllergyOut, ProblemOut, EncounterOut,
)
from app.services.audit import AuditService


class ClinicalService:

    # ── access guard ──────────────────────────────────────────────────────────

    @staticmethod
    async def _assert_chart_access(
        requester: User,
        patient_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        """Raise 403/404 if requester may not access this patient's chart."""
        if requester.role == "patient":
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail="Patients cannot access clinical records directly")

        if requester.role == "doctor":
            doctor_result = await db.execute(
                select(Doctor).where(Doctor.user_id == requester.id)
            )
            doctor = doctor_result.scalar_one_or_none()
            if doctor is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Doctor profile not found")

            link = await db.execute(
                select(Booking)
                .join(Slot, Booking.slot_id == Slot.id)
                .where(
                    Slot.doctor_id == doctor.id,
                    Booking.user_id == patient_id,
                )
                .limit(1)
            )
            if link.scalar_one_or_none() is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")

        # admin: always allowed

    # ── encounters ────────────────────────────────────────────────────────────

    @staticmethod
    async def create_encounter(
        payload: EncounterCreate,
        db: AsyncSession,
    ) -> Encounter:
        enc = Encounter(
            booking_id=payload.booking_id,
            patient_id=payload.patient_id,
            doctor_id=payload.doctor_id,
            facility_id=payload.facility_id,
            encounter_type=payload.encounter_type,
            chief_complaint=payload.chief_complaint,
            notes=payload.notes,
            encounter_date=payload.encounter_date,
        )
        db.add(enc)
        await db.flush()
        await db.refresh(enc)
        try:
            await WebhookService.enqueue(
                "encounter.created",
                {"event": "encounter.created", "encounter_id": str(enc.id), "patient_id": str(enc.patient_id), "doctor_id": str(enc.doctor_id), "encounter_date": str(enc.encounter_date)},
                db,
            )
        except Exception:
            pass
        return enc

    # ── vitals ────────────────────────────────────────────────────────────────

    @staticmethod
    async def add_vitals(
        encounter_id: uuid.UUID,
        payload: VitalCreate,
        recorder: User,
        db: AsyncSession,
    ) -> Vital:
        enc = await ClinicalService._get_encounter_or_404(encounter_id, db)
        v = Vital(
            encounter_id=encounter_id,
            patient_id=enc.patient_id,
            bp_systolic=payload.bp_systolic,
            bp_diastolic=payload.bp_diastolic,
            heart_rate=payload.heart_rate,
            temperature_f=payload.temperature_f,
            weight_kg=payload.weight_kg,
            height_cm=payload.height_cm,
            spo2=payload.spo2,
            respiratory_rate=payload.respiratory_rate,
            recorded_by=recorder.id,
            recorded_at=datetime.now(timezone.utc),
        )
        db.add(v)
        await db.flush()
        await db.refresh(v)
        return v

    # ── diagnoses ─────────────────────────────────────────────────────────────

    @staticmethod
    async def add_diagnosis(
        encounter_id: uuid.UUID,
        payload: DiagnosisCreate,
        creator: User,
        db: AsyncSession,
    ) -> Diagnosis:
        enc = await ClinicalService._get_encounter_or_404(encounter_id, db)
        d = Diagnosis(
            encounter_id=encounter_id,
            patient_id=enc.patient_id,
            icd10_code=payload.icd10_code,
            description=payload.description,
            diagnosis_type=payload.diagnosis_type,
            onset_date=payload.onset_date,
            created_by=creator.id,
        )
        db.add(d)
        await db.flush()
        await db.refresh(d)
        return d

    # ── prescriptions ─────────────────────────────────────────────────────────

    @staticmethod
    async def add_prescription(
        encounter_id: uuid.UUID,
        payload: PrescriptionCreate,
        prescriber: User,
        db: AsyncSession,
    ) -> Prescription:
        enc = await ClinicalService._get_encounter_or_404(encounter_id, db)
        p = Prescription(
            encounter_id=encounter_id,
            patient_id=enc.patient_id,
            drug_name=payload.drug_name,
            dose=payload.dose,
            frequency=payload.frequency,
            route=payload.route,
            start_date=payload.start_date,
            end_date=payload.end_date,
            refills=payload.refills,
            notes=payload.notes,
            prescriber_id=prescriber.id,
        )
        db.add(p)
        await db.flush()
        await db.refresh(p)
        return p

    # ── allergies ─────────────────────────────────────────────────────────────

    @staticmethod
    async def add_allergy(
        patient_id: uuid.UUID,
        payload: AllergyCreate,
        recorder: User,
        db: AsyncSession,
    ) -> Allergy:
        a = Allergy(
            patient_id=patient_id,
            allergen=payload.allergen,
            reaction=payload.reaction,
            severity=payload.severity,
            onset_date=payload.onset_date,
            recorded_by=recorder.id,
        )
        db.add(a)
        await db.flush()
        await db.refresh(a)
        return a

    # ── problem list ──────────────────────────────────────────────────────────

    @staticmethod
    async def add_problem(
        patient_id: uuid.UUID,
        payload: ProblemCreate,
        noter: User,
        db: AsyncSession,
    ) -> ProblemList:
        pl = ProblemList(
            patient_id=patient_id,
            icd10_code=payload.icd10_code,
            description=payload.description,
            status=payload.status,
            onset_date=payload.onset_date,
            noted_by=noter.id,
        )
        db.add(pl)
        await db.flush()
        await db.refresh(pl)
        return pl

    # ── chart read ────────────────────────────────────────────────────────────

    @staticmethod
    async def get_chart(
        patient_id: uuid.UUID,
        requester: User,
        db: AsyncSession,
    ) -> PatientChartOut:
        await ClinicalService._assert_chart_access(requester, patient_id, db)

        allergies_result = await db.execute(
            select(Allergy)
            .where(Allergy.patient_id == patient_id)
            .order_by(Allergy.created_at)
        )
        allergies = allergies_result.scalars().all()

        problems_result = await db.execute(
            select(ProblemList)
            .where(ProblemList.patient_id == patient_id)
            .order_by(ProblemList.created_at)
        )
        problems = problems_result.scalars().all()

        encounters_result = await db.execute(
            select(Encounter)
            .where(Encounter.patient_id == patient_id)
            .options(
                selectinload(Encounter.vitals),
                selectinload(Encounter.diagnoses),
                selectinload(Encounter.prescriptions),
            )
            .order_by(Encounter.encounter_date.desc())
        )
        encounters = encounters_result.scalars().all()

        await AuditService.log(
            db=db,
            action="CHART_ACCESSED",
            user_id=requester.id,
            target=str(patient_id),
            details={
                "encounters": len(encounters),
                "allergies": len(allergies),
                "problems": len(problems),
            },
        )

        enc_out = []
        for e in encounters:
            enc_out.append(EncounterWithDetails(
                **EncounterOut.model_validate(e).model_dump(),
                vitals=[VitalOut.model_validate(v) for v in e.vitals],
                diagnoses=[DiagnosisOut.model_validate(d) for d in e.diagnoses],
                prescriptions=[PrescriptionOut.model_validate(p) for p in e.prescriptions],
            ))

        return PatientChartOut(
            patient_id=patient_id,
            allergies=[AllergyOut.model_validate(a) for a in allergies],
            problem_list=[ProblemOut.model_validate(p) for p in problems],
            encounters=enc_out,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _get_encounter_or_404(encounter_id: uuid.UUID, db: AsyncSession) -> Encounter:
        result = await db.execute(
            select(Encounter).where(Encounter.id == encounter_id)
        )
        enc = result.scalar_one_or_none()
        if enc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Encounter not found")
        return enc
