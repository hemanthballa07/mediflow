from fastapi import APIRouter
from app.api.v1.endpoints import auth, bookings, reports, admin, catalog, waitlist, clinical, referrals, orders, insurance, charge_masters, claims, compliance

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(bookings.router)
api_router.include_router(reports.router)
api_router.include_router(admin.router)
api_router.include_router(catalog.router)
api_router.include_router(waitlist.router)
api_router.include_router(clinical.router)
api_router.include_router(referrals.router)
api_router.include_router(orders.router)
api_router.include_router(insurance.router)
api_router.include_router(charge_masters.router)
api_router.include_router(claims.router)
api_router.include_router(compliance.router)
