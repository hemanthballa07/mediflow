import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.v1.deps import require_role, get_current_user
from app.models.models import User
from app.services.orders import OrdersService
from app.schemas.schemas import OrderCreate, OrderOut

router = APIRouter(tags=["orders"])

_doctor_or_admin = require_role("doctor", "admin")


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    current_user: User = Depends(_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    order = await OrdersService.create(payload, current_user, db)
    await db.commit()
    return order


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await OrdersService.get(order_id, current_user, db)
    await db.commit()
    return order


@router.get("/encounters/{encounter_id}/orders", response_model=list[OrderOut])
async def list_encounter_orders(
    encounter_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orders = await OrdersService.list_for_encounter(encounter_id, current_user, db)
    await db.commit()
    return orders
