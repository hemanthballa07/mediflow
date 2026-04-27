import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.session import get_db, get_read_db
from app.db.redis import get_redis
from app.schemas.schemas import ReportOut, ReportPage, ReportCreate
from app.services.reports import ReportService
from app.api.v1.deps import get_current_user, require_role, phi_audit
from app.models.models import User

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(phi_audit)])


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(
    payload: ReportCreate,
    _: User = Depends(require_role("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    return await ReportService.create_report(payload, db)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
):
    return await ReportService.get_report(report_id, current_user.id, db)


@router.get("", response_model=ReportPage)
async def list_reports(
    patient_id: uuid.UUID,
    report_status: str | None = Query(None),
    cursor: uuid.UUID | None = Query(None, description="Keyset cursor — id of last seen report"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    if current_user.role == "patient" and current_user.id != patient_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
    return await ReportService.list_reports(patient_id, report_status, cursor, limit, db, redis)
