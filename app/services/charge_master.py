import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.models import ChargeMaster
from app.schemas.schemas import ChargeMasterCreate


class ChargeMasterService:

    @staticmethod
    async def create(
        payload: ChargeMasterCreate,
        db: AsyncSession,
    ) -> ChargeMaster:
        entry = ChargeMaster(
            cpt_code=payload.cpt_code,
            description=payload.description,
            base_price=payload.base_price,
            department_id=payload.department_id,
            active=payload.active,
        )
        db.add(entry)
        await db.flush()
        await db.refresh(entry)
        return entry

    @staticmethod
    async def list(
        cpt_code: str | None,
        db: AsyncSession,
    ) -> list[ChargeMaster]:
        q = select(ChargeMaster).where(ChargeMaster.active == True)  # noqa: E712
        if cpt_code:
            q = q.where(ChargeMaster.cpt_code == cpt_code)
        result = await db.execute(q.order_by(ChargeMaster.cpt_code))
        return list(result.scalars().all())

    @staticmethod
    async def get_by_cpt(
        cpt_code: str,
        db: AsyncSession,
    ) -> ChargeMaster | None:
        result = await db.execute(
            select(ChargeMaster)
            .where(ChargeMaster.cpt_code == cpt_code, ChargeMaster.active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()
