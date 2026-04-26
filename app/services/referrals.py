import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.models import Referral, Doctor, User
from app.schemas.schemas import ReferralCreate, ReferralStatusUpdate
from app.services.audit import AuditService

_VALID_TRANSITIONS = {"pending": {"accepted", "rejected"}, "accepted": {"completed"}}


class ReferralsService:

    @staticmethod
    async def _resolve_doctor(user: User, db: AsyncSession) -> Doctor:
        result = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
        doctor = result.scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Doctor profile not found")
        return doctor

    @staticmethod
    async def create(
        payload: ReferralCreate,
        current_user: User,
        db: AsyncSession,
    ) -> Referral:
        if current_user.role == "doctor":
            doctor = await ReferralsService._resolve_doctor(current_user, db)
            referring_doctor_id = doctor.id
        else:
            if payload.referring_doctor_id is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    detail="referring_doctor_id required for admin")
            referring_doctor_id = payload.referring_doctor_id

        ref = Referral(
            patient_id=payload.patient_id,
            referring_doctor_id=referring_doctor_id,
            receiving_department_id=payload.receiving_department_id,
            encounter_id=payload.encounter_id,
            reason=payload.reason,
            urgency=payload.urgency,
            notes=payload.notes,
        )
        db.add(ref)
        await db.flush()
        await db.refresh(ref)
        return ref

    @staticmethod
    async def list_sent(current_user: User, db: AsyncSession) -> list[Referral]:
        doctor = await ReferralsService._resolve_doctor(current_user, db)
        result = await db.execute(
            select(Referral)
            .where(Referral.referring_doctor_id == doctor.id)
            .order_by(Referral.created_at.desc())
        )
        refs = list(result.scalars().all())
        await AuditService.log(
            db=db,
            action="REFERRALS_SENT_LISTED",
            user_id=current_user.id,
            details={"count": len(refs)},
        )
        return refs

    @staticmethod
    async def list_received(current_user: User, db: AsyncSession) -> list[Referral]:
        doctor = await ReferralsService._resolve_doctor(current_user, db)
        if doctor.department_id is None:
            return []
        result = await db.execute(
            select(Referral)
            .where(Referral.receiving_department_id == doctor.department_id)
            .order_by(Referral.created_at.desc())
        )
        refs = list(result.scalars().all())
        await AuditService.log(
            db=db,
            action="REFERRALS_RECEIVED_LISTED",
            user_id=current_user.id,
            details={"department_id": str(doctor.department_id), "count": len(refs)},
        )
        return refs

    @staticmethod
    async def list_for_patient(current_user: User, db: AsyncSession) -> list[Referral]:
        result = await db.execute(
            select(Referral)
            .where(Referral.patient_id == current_user.id)
            .order_by(Referral.created_at.desc())
        )
        refs = list(result.scalars().all())
        await AuditService.log(
            db=db,
            action="REFERRALS_PATIENT_LISTED",
            user_id=current_user.id,
            target=str(current_user.id),
            details={"count": len(refs)},
        )
        return refs

    @staticmethod
    async def update_status(
        referral_id: uuid.UUID,
        payload: ReferralStatusUpdate,
        current_user: User,
        db: AsyncSession,
    ) -> Referral:
        result = await db.execute(select(Referral).where(Referral.id == referral_id))
        ref = result.scalar_one_or_none()
        if ref is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Referral not found")

        if current_user.role == "doctor":
            doctor = await ReferralsService._resolve_doctor(current_user, db)
            if doctor.department_id != ref.receiving_department_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                                    detail="Only doctor in receiving department may update status")

        allowed = _VALID_TRANSITIONS.get(ref.status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot transition from '{ref.status}' to '{payload.status}'",
            )

        old_status = ref.status
        ref.status = payload.status
        if payload.notes is not None:
            ref.notes = payload.notes
        ref.responded_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(ref)
        await AuditService.log(
            db=db,
            action="REFERRAL_STATUS_UPDATED",
            user_id=current_user.id,
            target=str(referral_id),
            details={"old": old_status, "new": payload.status},
        )
        return ref
