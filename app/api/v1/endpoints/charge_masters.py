from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.v1.deps import require_role
from app.models.models import User
from app.services.charge_master import ChargeMasterService
from app.schemas.schemas import ChargeMasterCreate, ChargeMasterOut

router = APIRouter(tags=["charge-masters"])

_admin_only = require_role("admin")
_doctor_or_admin = require_role("doctor", "admin")


@router.post("/admin/charge-masters", response_model=ChargeMasterOut, status_code=status.HTTP_201_CREATED)
async def create_charge_master(
    payload: ChargeMasterCreate,
    current_user: User = Depends(_admin_only),
    db: AsyncSession = Depends(get_db),
):
    entry = await ChargeMasterService.create(payload, db)
    await db.commit()
    return entry


@router.get("/charge-masters", response_model=list[ChargeMasterOut])
async def list_charge_masters(
    cpt_code: str | None = Query(None),
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    entries = await ChargeMasterService.list(cpt_code, db)
    await db.commit()
    return entries
