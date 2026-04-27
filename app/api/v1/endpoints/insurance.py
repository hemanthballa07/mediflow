import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.v1.deps import require_role, get_current_user, phi_audit
from app.models.models import User
from app.services.insurance import InsuranceService
from app.schemas.schemas import InsurancePlanCreate, InsurancePlanOut, PatientInsuranceCreate, PatientInsuranceOut

router = APIRouter(tags=["insurance"], dependencies=[Depends(phi_audit)])

_admin_only = require_role("admin")
_any_auth = get_current_user


@router.post("/admin/insurance-plans", response_model=InsurancePlanOut, status_code=status.HTTP_201_CREATED)
async def create_insurance_plan(
    payload: InsurancePlanCreate,
    current_user: User = Depends(_admin_only),
    db: AsyncSession = Depends(get_db),
):
    plan = await InsuranceService.create_plan(payload, db)
    await db.commit()
    return plan


@router.post("/patients/{patient_id}/insurance", response_model=PatientInsuranceOut, status_code=status.HTTP_201_CREATED)
async def add_patient_insurance(
    patient_id: uuid.UUID,
    payload: PatientInsuranceCreate,
    current_user: User = Depends(_any_auth),
    db: AsyncSession = Depends(get_db),
):
    policy = await InsuranceService.attach_to_patient(patient_id, payload, current_user, db)
    await db.commit()
    return policy


@router.get("/patients/{patient_id}/insurance", response_model=list[PatientInsuranceOut])
async def list_patient_insurance(
    patient_id: uuid.UUID,
    current_user: User = Depends(_any_auth),
    db: AsyncSession = Depends(get_db),
):
    policies = await InsuranceService.list_for_patient(patient_id, current_user, db)
    await db.commit()
    return policies
