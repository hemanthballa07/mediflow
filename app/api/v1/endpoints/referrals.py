import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.v1.deps import require_role, get_current_user
from app.models.models import User
from app.services.referrals import ReferralsService
from app.schemas.schemas import ReferralCreate, ReferralOut, ReferralStatusUpdate

router = APIRouter(tags=["referrals"])

_doctor_or_admin = require_role("doctor", "admin")


@router.post("/referrals", response_model=ReferralOut, status_code=status.HTTP_201_CREATED)
async def create_referral(
    payload: ReferralCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    ref = await ReferralsService.create(payload, current_user, db)
    await db.commit()
    return ref


@router.get("/referrals/sent", response_model=list[ReferralOut])
async def list_sent_referrals(
    current_user: User = Depends(require_role("doctor")),
    db: AsyncSession = Depends(get_db),
):
    refs = await ReferralsService.list_sent(current_user, db)
    await db.commit()
    return refs


@router.get("/referrals/received", response_model=list[ReferralOut])
async def list_received_referrals(
    current_user: User = Depends(require_role("doctor")),
    db: AsyncSession = Depends(get_db),
):
    refs = await ReferralsService.list_received(current_user, db)
    await db.commit()
    return refs


@router.get("/referrals/my", response_model=list[ReferralOut])
async def list_my_referrals(
    current_user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    refs = await ReferralsService.list_for_patient(current_user, db)
    await db.commit()
    return refs


@router.patch("/referrals/{referral_id}/status", response_model=ReferralOut)
async def update_referral_status(
    referral_id: uuid.UUID,
    payload: ReferralStatusUpdate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    ref = await ReferralsService.update_status(referral_id, payload, current_user, db)
    await db.commit()
    return ref
