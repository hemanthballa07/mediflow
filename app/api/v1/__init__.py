from fastapi import APIRouter
from app.api.v1.endpoints import auth, bookings, reports, admin, catalog

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(bookings.router)
api_router.include_router(reports.router)
api_router.include_router(admin.router)
api_router.include_router(catalog.router)
