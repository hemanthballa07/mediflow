import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.models import Claim, IdempotencyKey, Payment, User
from app.schemas.schemas import PaymentCreate, PaymentOut
from app.services.audit import AuditService


class PaymentsService:

    @staticmethod
    async def record_payment(
        claim_id: uuid.UUID,
        payload: PaymentCreate,
        idempotency_key: str,
        current_user: User,
        db: AsyncSession,
    ) -> tuple[PaymentOut, int]:
        existing = await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == current_user.id,
                IdempotencyKey.key == idempotency_key,
            )
        )
        idem: IdempotencyKey | None = existing.scalar_one_or_none()

        if idem:
            if idem.status == "SUCCESS" and idem.response:
                return PaymentOut(**idem.response), 200
            if idem.status == "PENDING":
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Request in progress")
            if idem.status == "ERROR":
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Previous attempt failed")

        idem_record = IdempotencyKey(
            user_id=current_user.id,
            key=idempotency_key,
            status="PENDING",
        )
        db.add(idem_record)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Duplicate idempotency key")

        result = await db.execute(
            text("SELECT id FROM claims WHERE id = :cid FOR UPDATE"),
            {"cid": str(claim_id)},
        )
        if result.fetchone() is None:
            idem_record.status = "ERROR"
            idem_record.updated_at = datetime.now(timezone.utc)
            await db.commit()
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Claim not found")

        result = await db.execute(select(Claim).where(Claim.id == claim_id))
        claim: Claim = result.scalar_one()

        if claim.status in ("rejected",):
            idem_record.status = "ERROR"
            idem_record.updated_at = datetime.now(timezone.utc)
            await db.commit()
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Cannot record payment on claim in status '{claim.status}'")

        payment = Payment(
            claim_id=claim_id,
            payer=payload.payer,
            amount=Decimal(str(payload.amount)),
            payment_method=payload.payment_method,
            reference_number=payload.reference_number,
            paid_at=payload.paid_at,
        )
        db.add(payment)
        await db.flush()
        await db.refresh(payment)

        new_total_paid = Decimal(str(claim.total_paid)) + Decimal(str(payload.amount))
        claim.total_paid = new_total_paid
        if new_total_paid >= Decimal(str(claim.total_charged)):
            claim.status = "paid"
            claim.adjudicated_at = datetime.now(timezone.utc)
        await db.flush()

        out = PaymentOut.model_validate(payment)
        idem_record.status = "SUCCESS"
        idem_record.response = out.model_dump(mode="json")
        idem_record.updated_at = datetime.now(timezone.utc)

        await AuditService.log(
            db=db,
            action="PAYMENT_RECORDED",
            user_id=current_user.id,
            target=str(claim_id),
            details={"payment_id": str(payment.id), "amount": str(payload.amount), "payer": payload.payer},
        )

        return out, 201
