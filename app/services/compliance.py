import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.models import (
    User, Booking, LabReport, Encounter, Allergy, ProblemList,
    Referral, Order, PatientInsurance, Claim, DeletionRequest,
)
from app.services.audit import AuditService
from app.core.encryption import decrypt


def _decrypt_user(user: User) -> None:
    user.email = decrypt(user.email)
    user.name = decrypt(user.name)


class ComplianceService:

    # ── break-glass ────────────────────────────────────────────────────────────

    @staticmethod
    async def break_glass(
        admin: User, patient_id: uuid.UUID, reason: str, db: AsyncSession
    ) -> dict:
        result = await db.execute(select(User).where(User.id == patient_id))
        patient: User | None = result.scalar_one_or_none()
        if not patient:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")

        await AuditService.log(
            db,
            action="BREAK_GLASS_ACCESS",
            user_id=admin.id,
            target=str(patient_id),
            details={"admin_id": str(admin.id), "reason": reason},
        )

        from app.services.clinical import ClinicalService
        chart = await ClinicalService.get_chart(patient_id, admin, db)
        await db.commit()
        return chart

    # ── GDPR export ────────────────────────────────────────────────────────────

    @staticmethod
    async def export_patient_data(
        requester: User, patient_id: uuid.UUID, db: AsyncSession
    ) -> dict:
        if requester.role == "patient" and requester.id != patient_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
        if requester.role not in ("patient", "admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        result = await db.execute(select(User).where(User.id == patient_id))
        patient: User | None = result.scalar_one_or_none()
        if not patient:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")

        await AuditService.log(
            db, action="GDPR_EXPORT",
            user_id=requester.id, target=str(patient_id),
        )

        bookings_r = await db.execute(
            select(Booking).where(Booking.user_id == patient_id)
        )
        reports_r = await db.execute(
            select(LabReport).where(LabReport.patient_id == patient_id)
        )
        encounters_r = await db.execute(
            select(Encounter)
            .options(
                selectinload(Encounter.vitals),
                selectinload(Encounter.diagnoses),
                selectinload(Encounter.prescriptions),
            )
            .where(Encounter.patient_id == patient_id)
        )
        allergies_r = await db.execute(
            select(Allergy).where(Allergy.patient_id == patient_id)
        )
        problems_r = await db.execute(
            select(ProblemList).where(ProblemList.patient_id == patient_id)
        )
        referrals_r = await db.execute(
            select(Referral).where(Referral.patient_id == patient_id)
        )
        orders_r = await db.execute(
            select(Order).where(Order.patient_id == patient_id)
        )
        insurance_r = await db.execute(
            select(PatientInsurance).where(PatientInsurance.patient_id == patient_id)
        )
        claims_r = await db.execute(
            select(Claim).where(Claim.patient_id == patient_id)
        )

        def _row_to_dict(obj) -> dict:
            d = {}
            for col in obj.__table__.columns:
                val = getattr(obj, col.name)
                if isinstance(val, (uuid.UUID, datetime)):
                    val = str(val)
                d[col.name] = val
            return d

        enc_rows = encounters_r.scalars().all()
        encounter_dicts = []
        for enc in enc_rows:
            ed = _row_to_dict(enc)
            ed["vitals"] = [_row_to_dict(v) for v in enc.vitals]
            ed["diagnoses"] = [_row_to_dict(d) for d in enc.diagnoses]
            ed["prescriptions"] = [_row_to_dict(p) for p in enc.prescriptions]
            encounter_dicts.append(ed)

        await db.commit()

        return {
            "patient_id": str(patient_id),
            "email": decrypt(patient.email),
            "name": decrypt(patient.name),
            "role": patient.role,
            "created_at": str(patient.created_at),
            "bookings": [_row_to_dict(b) for b in bookings_r.scalars().all()],
            "lab_reports": [_row_to_dict(r) for r in reports_r.scalars().all()],
            "encounters": encounter_dicts,
            "allergies": [_row_to_dict(a) for a in allergies_r.scalars().all()],
            "problem_list": [_row_to_dict(p) for p in problems_r.scalars().all()],
            "referrals": [_row_to_dict(r) for r in referrals_r.scalars().all()],
            "orders": [_row_to_dict(o) for o in orders_r.scalars().all()],
            "insurance": [_row_to_dict(i) for i in insurance_r.scalars().all()],
            "claims": [_row_to_dict(c) for c in claims_r.scalars().all()],
        }

    # ── deletion requests ─────────────────────────────────────────────────────

    @staticmethod
    async def create_deletion_request(
        requester: User, patient_id: uuid.UUID, db: AsyncSession
    ) -> DeletionRequest:
        if requester.role == "patient" and requester.id != patient_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
        if requester.role not in ("patient", "admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        result = await db.execute(select(User).where(User.id == patient_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")

        req = DeletionRequest(patient_id=patient_id)
        db.add(req)
        await AuditService.log(
            db, action="DELETION_REQUEST_CREATED",
            user_id=requester.id, target=str(patient_id),
        )
        await db.commit()
        await db.refresh(req)
        return req

    @staticmethod
    async def list_deletion_requests(
        requester: User, patient_id: uuid.UUID, db: AsyncSession
    ) -> list[DeletionRequest]:
        if requester.role == "patient" and requester.id != patient_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
        if requester.role not in ("patient", "admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        result = await db.execute(
            select(DeletionRequest).where(DeletionRequest.patient_id == patient_id)
            .order_by(DeletionRequest.requested_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def review_deletion_request(
        admin: User,
        request_id: uuid.UUID,
        new_status: str,
        notes: str | None,
        db: AsyncSession,
    ) -> DeletionRequest:
        result = await db.execute(
            select(DeletionRequest).where(DeletionRequest.id == request_id)
        )
        req: DeletionRequest | None = result.scalar_one_or_none()
        if not req:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Deletion request not found")

        if req.status not in ("pending",):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Request already in terminal state: {req.status}",
            )

        req.status = new_status
        req.reviewed_by = admin.id
        req.reviewed_at = datetime.now(timezone.utc)
        req.notes = notes

        await AuditService.log(
            db, action="DELETION_REQUEST_REVIEWED",
            user_id=admin.id, target=str(request_id),
            details={"status": new_status},
        )
        await db.commit()
        await db.refresh(req)
        return req
