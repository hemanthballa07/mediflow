import uuid
from datetime import date as date_type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status

from app.models.models import InsurancePlan, PatientInsurance, User
from app.schemas.schemas import InsurancePlanCreate, PatientInsuranceCreate
from app.services.audit import AuditService


class InsuranceService:

    @staticmethod
    async def create_plan(
        payload: InsurancePlanCreate,
        db: AsyncSession,
    ) -> InsurancePlan:
        plan = InsurancePlan(
            name=payload.name,
            payer_id=payload.payer_id,
            plan_type=payload.plan_type,
        )
        db.add(plan)
        await db.flush()
        await db.refresh(plan)
        return plan

    @staticmethod
    async def attach_to_patient(
        patient_id: uuid.UUID,
        payload: PatientInsuranceCreate,
        current_user: User,
        db: AsyncSession,
    ) -> PatientInsurance:
        if current_user.role == "patient" and current_user.id != patient_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        result = await db.execute(select(User).where(User.id == patient_id, User.role == "patient"))
        patient = result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")

        result = await db.execute(select(InsurancePlan).where(InsurancePlan.id == payload.insurance_plan_id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Insurance plan not found")

        if payload.termination_date and payload.termination_date < payload.effective_date:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="termination_date must be >= effective_date")

        if payload.is_primary:
            await db.execute(
                update(PatientInsurance)
                .where(PatientInsurance.patient_id == patient_id, PatientInsurance.is_primary == True)  # noqa: E712
                .values(is_primary=False)
            )

        policy = PatientInsurance(
            patient_id=patient_id,
            insurance_plan_id=payload.insurance_plan_id,
            member_id=payload.member_id,
            group_number=payload.group_number,
            effective_date=payload.effective_date,
            termination_date=payload.termination_date,
            is_primary=payload.is_primary,
        )
        db.add(policy)
        await db.flush()
        await db.refresh(policy)
        return policy

    @staticmethod
    async def list_for_patient(
        patient_id: uuid.UUID,
        current_user: User,
        db: AsyncSession,
    ) -> list[PatientInsurance]:
        if current_user.role == "patient" and current_user.id != patient_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        result = await db.execute(
            select(PatientInsurance)
            .where(PatientInsurance.patient_id == patient_id)
            .order_by(PatientInsurance.is_primary.desc(), PatientInsurance.created_at.desc())
        )
        policies = list(result.scalars().all())
        await AuditService.log(
            db=db,
            action="INSURANCE_ACCESSED",
            user_id=current_user.id,
            target=str(patient_id),
            details={"count": len(policies)},
        )
        return policies
