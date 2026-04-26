import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import PatientPreference
from app.schemas.schemas import PatientPreferenceOut, PatientPreferenceUpdate


class PreferenceService:

    @staticmethod
    async def get_or_create(
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> PatientPreferenceOut:
        result = await db.execute(
            select(PatientPreference).where(PatientPreference.user_id == user_id)
        )
        pref = result.scalar_one_or_none()
        if not pref:
            pref = PatientPreference(user_id=user_id)
            db.add(pref)
            await db.commit()
            await db.refresh(pref)
        return PatientPreferenceOut.model_validate(pref)

    @staticmethod
    async def update(
        user_id: uuid.UUID,
        payload: PatientPreferenceUpdate,
        db: AsyncSession,
    ) -> PatientPreferenceOut:
        result = await db.execute(
            select(PatientPreference).where(PatientPreference.user_id == user_id)
        )
        pref = result.scalar_one_or_none()
        if not pref:
            pref = PatientPreference(user_id=user_id)
            db.add(pref)

        updates = payload.model_dump(exclude_none=True)
        for field, value in updates.items():
            setattr(pref, field, value)
        pref.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(pref)
        return PatientPreferenceOut.model_validate(pref)
