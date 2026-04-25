import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.models import Specialty, Facility, Department, Room, Doctor


class CatalogService:

    # ── Specialties ───────────────────────────────────────────────────────────

    @staticmethod
    async def list_specialties(db: AsyncSession) -> list[Specialty]:
        result = await db.execute(select(Specialty).order_by(Specialty.name))
        return list(result.scalars().all())

    @staticmethod
    async def create_specialty(name: str, code: str, db: AsyncSession) -> Specialty:
        spec = Specialty(name=name, code=code.upper())
        db.add(spec)
        await db.commit()
        await db.refresh(spec)
        return spec

    # ── Facilities ────────────────────────────────────────────────────────────

    @staticmethod
    async def list_facilities(db: AsyncSession) -> list[Facility]:
        result = await db.execute(
            select(Facility).where(Facility.active == True).order_by(Facility.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_facility(facility_id: uuid.UUID, db: AsyncSession) -> Facility:
        result = await db.execute(select(Facility).where(Facility.id == facility_id))
        facility = result.scalar_one_or_none()
        if not facility:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Facility not found")
        return facility

    @staticmethod
    async def create_facility(
        name: str, code: str, address: str | None, timezone: str, db: AsyncSession
    ) -> Facility:
        facility = Facility(name=name, code=code.upper(), address=address, timezone=timezone)
        db.add(facility)
        await db.commit()
        await db.refresh(facility)
        return facility

    # ── Departments ───────────────────────────────────────────────────────────

    @staticmethod
    async def list_departments(facility_id: uuid.UUID, db: AsyncSession) -> list[Department]:
        result = await db.execute(
            select(Department)
            .where(Department.facility_id == facility_id)
            .order_by(Department.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_department(
        facility_id: uuid.UUID,
        specialty_id: uuid.UUID | None,
        name: str,
        code: str,
        db: AsyncSession,
    ) -> Department:
        dept = Department(
            facility_id=facility_id,
            specialty_id=specialty_id,
            name=name,
            code=code.upper(),
        )
        db.add(dept)
        await db.commit()
        await db.refresh(dept)
        return dept

    # ── Rooms ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def create_room(
        facility_id: uuid.UUID,
        department_id: uuid.UUID | None,
        name: str,
        kind: str,
        db: AsyncSession,
    ) -> Room:
        valid_kinds = {"exam", "procedure", "imaging", "ward"}
        if kind not in valid_kinds:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"kind must be one of {sorted(valid_kinds)}",
            )
        room = Room(facility_id=facility_id, department_id=department_id, name=name, kind=kind)
        db.add(room)
        await db.commit()
        await db.refresh(room)
        return room

    # ── Doctors (filtered listing) ────────────────────────────────────────────

    @staticmethod
    async def list_doctors(
        db: AsyncSession,
        facility_id: uuid.UUID | None = None,
        department_id: uuid.UUID | None = None,
        specialty_id: uuid.UUID | None = None,
    ) -> list[Doctor]:
        q = select(Doctor)
        if facility_id:
            q = q.where(Doctor.facility_id == facility_id)
        if department_id:
            q = q.where(Doctor.department_id == department_id)
        if specialty_id:
            q = q.where(Doctor.specialty_id == specialty_id)
        result = await db.execute(q)
        return list(result.scalars().all())
