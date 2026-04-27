import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.api.v1.deps import require_role, get_current_user
from app.models.models import AuditLog, CdsRule, User
from app.schemas.schemas import CdsAlertOut, CdsRuleCreate, CdsRuleOut, CdsRulePatch

router = APIRouter(tags=["cds"])

_doctor_or_admin = require_role("doctor", "admin")
_admin_only = require_role("admin")


@router.get("/encounters/{encounter_id}/cds-alerts", response_model=list[CdsAlertOut])
async def get_encounter_cds_alerts(
    encounter_id: uuid.UUID,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.action == "CDS_ALERT_FIRED",
            AuditLog.target == str(encounter_id),
        )
        .order_by(AuditLog.ts.asc())
    )
    rows = result.scalars().all()
    alerts = []
    for row in rows:
        d = row.details or {}
        alerts.append(CdsAlertOut(
            rule_type=d.get("rule_type", ""),
            severity=d.get("severity", ""),
            message=d.get("message", ""),
            rule_key=d.get("rule_key"),
        ))
    return alerts


@router.get("/admin/cds-rules", response_model=list[CdsRuleOut])
async def list_cds_rules(
    current_user: User = Depends(_admin_only),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CdsRule).order_by(CdsRule.rule_type, CdsRule.rule_key)
    )
    return list(result.scalars().all())


@router.post("/admin/cds-rules", response_model=CdsRuleOut, status_code=status.HTTP_201_CREATED)
async def create_cds_rule(
    payload: CdsRuleCreate,
    current_user: User = Depends(_admin_only),
    db: AsyncSession = Depends(get_db),
):
    rule = CdsRule(
        facility_id=payload.facility_id,
        rule_type=payload.rule_type,
        rule_key=payload.rule_key,
        severity=payload.severity,
        message=payload.message,
        active=True,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    await db.commit()
    return rule


@router.patch("/admin/cds-rules/{rule_id}", response_model=CdsRuleOut)
async def patch_cds_rule(
    rule_id: uuid.UUID,
    payload: CdsRulePatch,
    current_user: User = Depends(_admin_only),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    result = await db.execute(select(CdsRule).where(CdsRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="CDS rule not found")
    if payload.active is not None:
        rule.active = payload.active
    if payload.severity is not None:
        rule.severity = payload.severity
    if payload.message is not None:
        rule.message = payload.message
    await db.flush()
    await db.refresh(rule)
    await db.commit()
    return rule
