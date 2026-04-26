import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.models import Order, Encounter, Doctor, User
from app.schemas.schemas import OrderCreate
from app.services.audit import AuditService


class OrdersService:

    @staticmethod
    async def _resolve_doctor(user: User, db: AsyncSession) -> Doctor:
        result = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
        doctor = result.scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Doctor profile not found")
        return doctor

    @staticmethod
    async def _get_encounter_or_404(encounter_id: uuid.UUID, db: AsyncSession) -> Encounter:
        result = await db.execute(select(Encounter).where(Encounter.id == encounter_id))
        enc = result.scalar_one_or_none()
        if enc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Encounter not found")
        return enc

    @staticmethod
    async def create(
        payload: OrderCreate,
        current_user: User,
        db: AsyncSession,
    ) -> Order:
        enc = await OrdersService._get_encounter_or_404(payload.encounter_id, db)

        if current_user.role == "doctor":
            doctor = await OrdersService._resolve_doctor(current_user, db)
            ordering_doctor_id = doctor.id
        else:
            if payload.ordering_doctor_id is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    detail="ordering_doctor_id required for admin")
            ordering_doctor_id = payload.ordering_doctor_id

        order = Order(
            encounter_id=enc.id,
            patient_id=enc.patient_id,
            ordering_doctor_id=ordering_doctor_id,
            order_type=payload.order_type,
            cpt_code=payload.cpt_code,
            description=payload.description,
            priority=payload.priority,
            notes=payload.notes,
        )
        db.add(order)
        await db.flush()
        await db.refresh(order)
        return order

    @staticmethod
    async def get(
        order_id: uuid.UUID,
        current_user: User,
        db: AsyncSession,
    ) -> Order:
        if current_user.role == "patient":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Patients cannot access orders")

        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()

        if order is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")

        if current_user.role == "doctor":
            doctor = await OrdersService._resolve_doctor(current_user, db)
            if order.ordering_doctor_id != doctor.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found")

        await AuditService.log(
            db=db,
            action="ORDER_ACCESSED",
            user_id=current_user.id,
            target=str(order_id),
        )
        return order

    @staticmethod
    async def list_for_encounter(
        encounter_id: uuid.UUID,
        current_user: User,
        db: AsyncSession,
    ) -> list[Order]:
        if current_user.role == "patient":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Patients cannot access orders")

        enc = await OrdersService._get_encounter_or_404(encounter_id, db)

        if current_user.role == "doctor":
            doctor = await OrdersService._resolve_doctor(current_user, db)
            if enc.doctor_id != doctor.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                                    detail="Access denied to this encounter's orders")

        result = await db.execute(
            select(Order)
            .where(Order.encounter_id == encounter_id)
            .order_by(Order.ordered_at.desc())
        )
        orders = list(result.scalars().all())
        await AuditService.log(
            db=db,
            action="ENCOUNTER_ORDERS_LISTED",
            user_id=current_user.id,
            target=str(encounter_id),
            details={"count": len(orders)},
        )
        return orders
