import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import (
    WaitlistEntryCreate, WaitlistEntryOut, WaitlistPositionOut,
    PatientPreferenceOut, PatientPreferenceUpdate, MessageResponse,
)
from app.services.waitlist import WaitlistService
from app.services.preferences import PreferenceService

router = APIRouter(tags=["waitlist"])


# ── Waitlist ──────────────────────────────────────────────────────────────────

@router.post(
    "/waitlist",
    response_model=WaitlistEntryOut,
    status_code=status.HTTP_201_CREATED,
)
async def join_waitlist(
    payload: WaitlistEntryCreate,
    current_user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    return await WaitlistService.join(current_user.id, payload, db)


@router.get("/waitlist", response_model=list[WaitlistEntryOut])
async def list_waitlist(
    current_user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    return await WaitlistService.list_active(current_user.id, db)


@router.get("/waitlist/{entry_id}/position", response_model=WaitlistPositionOut)
async def get_position(
    entry_id: uuid.UUID,
    current_user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    return await WaitlistService.get_position(entry_id, current_user.id, db)


@router.delete(
    "/waitlist/{entry_id}",
    response_model=WaitlistEntryOut,
)
async def leave_waitlist(
    entry_id: uuid.UUID,
    current_user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    return await WaitlistService.leave(entry_id, current_user.id, db)


# ── Preferences ───────────────────────────────────────────────────────────────

@router.get("/preferences/me", response_model=PatientPreferenceOut)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await PreferenceService.get_or_create(current_user.id, db)


@router.put("/preferences/me", response_model=PatientPreferenceOut)
async def update_preferences(
    payload: PatientPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await PreferenceService.update(current_user.id, payload, db)
