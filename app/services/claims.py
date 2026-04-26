import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.models import Claim, ClaimLineItem, Doctor, Encounter, PatientInsurance, User
from app.schemas.schemas import ClaimCreate
from app.services.audit import AuditService
from app.services.charge_master import ChargeMasterService


class ClaimsService:

    @staticmethod
    async def _resolve_doctor(user: User, db: AsyncSession) -> Doctor:
        result = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
        doctor = result.scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Doctor profile not found")
        return doctor

    @staticmethod
    async def create(
        payload: ClaimCreate,
        current_user: User,
        db: AsyncSession,
    ) -> Claim:
        result = await db.execute(select(Encounter).where(Encounter.id == payload.encounter_id))
        encounter = result.scalar_one_or_none()
        if encounter is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Encounter not found")

        result = await db.execute(
            select(PatientInsurance).where(PatientInsurance.id == payload.patient_insurance_id)
        )
        patient_insurance = result.scalar_one_or_none()
        if patient_insurance is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient insurance not found")
        if patient_insurance.patient_id != encounter.patient_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Insurance does not belong to encounter patient")

        if current_user.role == "doctor":
            doctor = await ClaimsService._resolve_doctor(current_user, db)
            ordering_doctor_id = doctor.id
        else:
            if payload.ordering_doctor_id is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="ordering_doctor_id required for admin")
            ordering_doctor_id = payload.ordering_doctor_id

        if not payload.line_items:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="At least one line item required")

        total_charged = Decimal("0")
        line_item_rows = []
        for item in payload.line_items:
            unit_price = item.unit_price
            if unit_price is None:
                cm = await ChargeMasterService.get_by_cpt(item.cpt_code, db)
                if cm is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"No charge master entry for CPT {item.cpt_code}; provide unit_price",
                    )
                unit_price = float(cm.base_price)
            total_price = Decimal(str(unit_price)) * item.units
            total_charged += total_price
            line_item_rows.append({
                "order_id": item.order_id,
                "cpt_code": item.cpt_code,
                "icd10_codes": item.icd10_codes,
                "description": item.description,
                "units": item.units,
                "unit_price": Decimal(str(unit_price)),
                "total_price": total_price,
            })

        claim = Claim(
            patient_id=encounter.patient_id,
            encounter_id=encounter.id,
            patient_insurance_id=patient_insurance.id,
            ordering_doctor_id=ordering_doctor_id,
            status="draft",
            total_charged=total_charged,
            total_paid=Decimal("0"),
        )
        db.add(claim)
        await db.flush()

        for row in line_item_rows:
            li = ClaimLineItem(claim_id=claim.id, **row)
            db.add(li)

        await db.flush()
        await db.refresh(claim)
        return claim

    @staticmethod
    async def submit(
        claim_id: uuid.UUID,
        current_user: User,
        db: AsyncSession,
    ) -> Claim:
        claim = await ClaimsService._get_claim_or_404(claim_id, current_user, db, allow_patient=False)
        if claim.status != "draft":
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Cannot submit claim in status '{claim.status}'")
        claim.status = "submitted"
        claim.submitted_at = datetime.now(timezone.utc)
        await db.flush()
        await AuditService.log(
            db=db,
            action="CLAIM_SUBMITTED",
            user_id=current_user.id,
            target=str(claim_id),
        )
        return claim

    @staticmethod
    async def get(
        claim_id: uuid.UUID,
        current_user: User,
        db: AsyncSession,
    ) -> Claim:
        claim = await ClaimsService._get_claim_or_404(claim_id, current_user, db, allow_patient=True)
        await AuditService.log(
            db=db,
            action="CLAIM_ACCESSED",
            user_id=current_user.id,
            target=str(claim_id),
        )
        return claim

    @staticmethod
    async def list_for_patient(
        patient_id: uuid.UUID,
        current_user: User,
        db: AsyncSession,
    ) -> list[Claim]:
        if current_user.role == "patient" and current_user.id != patient_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        q = select(Claim).where(Claim.patient_id == patient_id)

        if current_user.role == "doctor":
            doctor = await ClaimsService._resolve_doctor(current_user, db)
            q = q.where(Claim.ordering_doctor_id == doctor.id)

        result = await db.execute(q.order_by(Claim.created_at.desc()))
        claims = list(result.scalars().all())
        await AuditService.log(
            db=db,
            action="PATIENT_CLAIMS_LISTED",
            user_id=current_user.id,
            target=str(patient_id),
            details={"count": len(claims)},
        )
        return claims

    @staticmethod
    async def _get_claim_or_404(
        claim_id: uuid.UUID,
        current_user: User,
        db: AsyncSession,
        allow_patient: bool,
    ) -> Claim:
        result = await db.execute(select(Claim).where(Claim.id == claim_id))
        claim = result.scalar_one_or_none()
        if claim is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Claim not found")

        if current_user.role == "patient":
            if not allow_patient:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
            if claim.patient_id != current_user.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Claim not found")

        if current_user.role == "doctor":
            doctor = await ClaimsService._resolve_doctor(current_user, db)
            if claim.ordering_doctor_id != doctor.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Claim not found")

        return claim
