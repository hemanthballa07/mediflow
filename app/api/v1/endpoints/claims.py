import uuid
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.v1.deps import require_role, get_current_user, phi_audit
from app.models.models import User
from app.services.claims import ClaimsService
from app.services.payments import PaymentsService
from app.schemas.schemas import ClaimCreate, ClaimDetailOut, ClaimOut, PaymentCreate, PaymentOut

router = APIRouter(tags=["claims"], dependencies=[Depends(phi_audit)])

_admin_only = require_role("admin")
_doctor_or_admin = require_role("doctor", "admin")
_any_auth = get_current_user


@router.post("/claims", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def create_claim(
    payload: ClaimCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    claim = await ClaimsService.create(payload, current_user, db)
    await db.commit()
    return claim


@router.post("/claims/{claim_id}/submit", response_model=ClaimOut)
async def submit_claim(
    claim_id: uuid.UUID,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    claim = await ClaimsService.submit(claim_id, current_user, db)
    await db.commit()
    return claim


@router.get("/claims/{claim_id}", response_model=ClaimDetailOut)
async def get_claim(
    claim_id: uuid.UUID,
    current_user: User = Depends(_any_auth),
    db: AsyncSession = Depends(get_db),
):
    claim = await ClaimsService.get(claim_id, current_user, db)
    await db.commit()
    return claim


@router.get("/patients/{patient_id}/claims", response_model=list[ClaimOut])
async def list_patient_claims(
    patient_id: uuid.UUID,
    current_user: User = Depends(_any_auth),
    db: AsyncSession = Depends(get_db),
):
    claims = await ClaimsService.list_for_patient(patient_id, current_user, db)
    await db.commit()
    return claims


@router.post("/claims/{claim_id}/payments", response_model=PaymentOut)
async def record_payment(
    claim_id: uuid.UUID,
    payload: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: User = Depends(_admin_only),
    db: AsyncSession = Depends(get_db),
):
    out, http_status = await PaymentsService.record_payment(
        claim_id, payload, idempotency_key, current_user, db
    )
    await db.commit()
    from fastapi.responses import JSONResponse
    return JSONResponse(content=out.model_dump(mode="json"), status_code=http_status)
