import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.v1.deps import get_current_user, require_role
from app.models.models import User
from app.services.auth import AuthService
from app.services.compliance import ComplianceService
from app.schemas.schemas import (
    BreakGlassRequest,
    ChangePasswordRequest,
    DeletionRequestOut,
    DeletionRequestReview,
    MessageResponse,
)
from app.core.config import get_settings
import hmac as hmac_mod

router = APIRouter(tags=["compliance"])

_admin_only = require_role("admin")


def _verify_admin_key(x_admin_api_key: str = Header(...)) -> None:
    settings = get_settings()
    if not hmac_mod.compare_digest(x_admin_api_key, settings.ADMIN_API_KEY):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid admin API key")


# ── Break-glass ───────────────────────────────────────────────────────────────

@router.post("/admin/break-glass/{patient_id}")
async def break_glass(
    patient_id: uuid.UUID,
    payload: BreakGlassRequest,
    admin: User = Depends(_admin_only),
    _key: None = Depends(_verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return await ComplianceService.break_glass(admin, patient_id, payload.reason, db)


# ── GDPR export ───────────────────────────────────────────────────────────────

@router.get("/patients/{patient_id}/export")
async def export_patient_data(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ComplianceService.export_patient_data(current_user, patient_id, db)


# ── Deletion requests ─────────────────────────────────────────────────────────

@router.post(
    "/patients/{patient_id}/deletion-requests",
    response_model=DeletionRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_deletion_request(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ComplianceService.create_deletion_request(current_user, patient_id, db)


@router.get(
    "/patients/{patient_id}/deletion-requests",
    response_model=list[DeletionRequestOut],
)
async def list_deletion_requests(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ComplianceService.list_deletion_requests(current_user, patient_id, db)


@router.patch(
    "/deletion-requests/{request_id}/status",
    response_model=DeletionRequestOut,
)
async def review_deletion_request(
    request_id: uuid.UUID,
    payload: DeletionRequestReview,
    admin: User = Depends(_admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await ComplianceService.review_deletion_request(
        admin, request_id, payload.status, payload.notes, db
    )


# ── Password change ───────────────────────────────────────────────────────────

@router.post("/auth/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AuthService.change_password(
        current_user, payload.current_password, payload.new_password, db
    )
    return MessageResponse(message="Password updated successfully")
