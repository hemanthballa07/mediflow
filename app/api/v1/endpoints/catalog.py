import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.schemas import DoctorOut, FacilityOut, DepartmentOut, SpecialtyOut
from app.services.catalog_service import CatalogService

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/specialties", response_model=list[SpecialtyOut])
async def list_specialties(db: AsyncSession = Depends(get_db)):
    return await CatalogService.list_specialties(db)


@router.get("/facilities", response_model=list[FacilityOut])
async def list_facilities(db: AsyncSession = Depends(get_db)):
    return await CatalogService.list_facilities(db)


@router.get("/facilities/{facility_id}/departments", response_model=list[DepartmentOut])
async def list_departments(facility_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await CatalogService.get_facility(facility_id, db)
    return await CatalogService.list_departments(facility_id, db)


@router.get("/doctors", response_model=list[DoctorOut])
async def list_doctors(
    facility_id: uuid.UUID | None = Query(None),
    department_id: uuid.UUID | None = Query(None),
    specialty_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService.list_doctors(
        db,
        facility_id=facility_id,
        department_id=department_id,
        specialty_id=specialty_id,
    )
