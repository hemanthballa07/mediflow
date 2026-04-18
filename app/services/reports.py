import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
import redis.asyncio as aioredis

from app.models.models import LabReport
from app.schemas.schemas import ReportOut, ReportPage, ReportCreate
from app.core.config import get_settings
from app.core.metrics import reports_accessed_total, cache_hits_total, cache_misses_total
from app.core.logging import get_logger
from app.services.audit import AuditService

log = get_logger(__name__)
settings = get_settings()


class ReportService:

    @staticmethod
    async def create_report(
        payload: ReportCreate,
        db: AsyncSession,
    ) -> ReportOut:
        report = LabReport(
            patient_id=payload.patient_id,
            report_type=payload.report_type,
            data=payload.data,
            status="PENDING",
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return ReportOut.model_validate(report)

    @staticmethod
    async def get_report(
        report_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
        db: AsyncSession,
    ) -> ReportOut:
        result = await db.execute(select(LabReport).where(LabReport.id == report_id))
        report: LabReport | None = result.scalar_one_or_none()

        if not report:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Report not found")
        if report.patient_id != requesting_user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        reports_accessed_total.labels(status="hit").inc()
        await AuditService.log(
            db, action="REPORT_ACCESSED",
            user_id=requesting_user_id,
            target=str(report_id),
        )
        await db.commit()
        return ReportOut.model_validate(report)

    @staticmethod
    async def list_reports(
        patient_id: uuid.UUID,
        report_status: str | None,
        cursor: uuid.UUID | None,  # keyset pagination — id of last seen report
        limit: int,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> ReportPage:
        """
        Keyset pagination: WHERE id > :cursor ORDER BY id LIMIT n
        Far more efficient than OFFSET for large result sets.
        Cache the first page (no cursor) per patient+status.
        """
        use_cache = cursor is None and limit <= 20
        cache_key = f"reports:{patient_id}:{report_status or 'ALL'}:first"

        if use_cache:
            cached = await redis.get(cache_key)
            if cached:
                cache_hits_total.labels(cache_key_prefix="reports").inc()
                raw = json.loads(cached)
                return ReportPage(
                    items=[ReportOut(**r) for r in raw["items"]],
                    next_cursor=uuid.UUID(raw["next_cursor"]) if raw["next_cursor"] else None,
                )
            cache_misses_total.labels(cache_key_prefix="reports").inc()

        # ── Keyset query ──────────────────────────────────────────────────────
        q = select(LabReport).where(LabReport.patient_id == patient_id)
        if report_status:
            q = q.where(LabReport.status == report_status)
        if cursor:
            # Use created_at-based cursor for stability; fall back to id comparison
            q = q.where(LabReport.id > cursor)
        q = q.order_by(LabReport.id).limit(limit + 1)  # fetch one extra to detect next page

        result = await db.execute(q)
        rows = result.scalars().all()

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = items[-1].id if has_more else None

        out_items = [ReportOut.model_validate(r) for r in items]
        page = ReportPage(items=out_items, next_cursor=next_cursor)

        if use_cache:
            payload = {
                "items": [r.model_dump(mode="json") for r in out_items],
                "next_cursor": str(next_cursor) if next_cursor else None,
            }
            await redis.setex(cache_key, 300, json.dumps(payload))  # 5-min TTL for report list

        reports_accessed_total.labels(status="list").inc()
        return page
