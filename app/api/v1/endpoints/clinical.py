import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db, get_read_db
from app.api.v1.deps import require_role, get_current_user, phi_audit
from app.models.models import User
from app.services.clinical import ClinicalService
from app.schemas.schemas import (
    EncounterCreate, EncounterOut,
    VitalCreate, VitalOut, VitalCreatedOut,
    DiagnosisCreate, DiagnosisOut,
    PrescriptionCreate, PrescriptionOut, PrescriptionCreatedOut,
    AllergyCreate, AllergyOut,
    ProblemCreate, ProblemOut,
    PatientChartOut,
)

router = APIRouter(tags=["clinical"], dependencies=[Depends(phi_audit)])

_doctor_or_admin = require_role("doctor", "admin")


@router.post("/encounters", response_model=EncounterOut, status_code=status.HTTP_201_CREATED)
async def create_encounter(
    payload: EncounterCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    enc = await ClinicalService.create_encounter(payload, db)
    await db.commit()
    return enc


@router.post(
    "/encounters/{encounter_id}/vitals",
    response_model=VitalCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_vitals(
    encounter_id: uuid.UUID,
    payload: VitalCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    vital, cds_alerts = await ClinicalService.add_vitals(encounter_id, payload, current_user, db)
    await db.commit()
    return VitalCreatedOut(vital=VitalOut.model_validate(vital), cds_alerts=cds_alerts)


@router.post(
    "/encounters/{encounter_id}/diagnoses",
    response_model=DiagnosisOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_diagnosis(
    encounter_id: uuid.UUID,
    payload: DiagnosisCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    dx = await ClinicalService.add_diagnosis(encounter_id, payload, current_user, db)
    await db.commit()
    return dx


@router.post(
    "/encounters/{encounter_id}/prescriptions",
    response_model=PrescriptionCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_prescription(
    encounter_id: uuid.UUID,
    payload: PrescriptionCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    rx, cds_alerts = await ClinicalService.add_prescription(encounter_id, payload, current_user, db)
    await db.commit()
    return PrescriptionCreatedOut(prescription=PrescriptionOut.model_validate(rx), cds_alerts=cds_alerts)


@router.post(
    "/patients/{patient_id}/allergies",
    response_model=AllergyOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_allergy(
    patient_id: uuid.UUID,
    payload: AllergyCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    allergy = await ClinicalService.add_allergy(patient_id, payload, current_user, db)
    await db.commit()
    return allergy


@router.post(
    "/patients/{patient_id}/problems",
    response_model=ProblemOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_problem(
    patient_id: uuid.UUID,
    payload: ProblemCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    problem = await ClinicalService.add_problem(patient_id, payload, current_user, db)
    await db.commit()
    return problem


@router.get("/patients/{patient_id}/chart", response_model=PatientChartOut)
async def get_patient_chart(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    chart = await ClinicalService.get_chart(patient_id, current_user, db)
    await db.commit()
    return chart
