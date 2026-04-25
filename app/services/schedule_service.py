import uuid
from datetime import date, time, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status

from app.models.models import DoctorSchedule, DoctorTimeOff, Slot, Doctor
from app.core.metrics import slots_generated_total


class ScheduleService:

    @staticmethod
    async def create_schedule(
        doctor_id: uuid.UUID,
        facility_id: uuid.UUID,
        day_of_week: int,
        start_time: time,
        end_time: time,
        slot_duration_min: int,
        effective_from: date,
        effective_to: date | None,
        db: AsyncSession,
    ) -> DoctorSchedule:
        if day_of_week not in range(7):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="day_of_week must be 0–6 (Mon–Sun)")
        if end_time <= start_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="end_time must be after start_time")
        if effective_to and effective_to < effective_from:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="effective_to must be >= effective_from")

        schedule = DoctorSchedule(
            doctor_id=doctor_id,
            facility_id=facility_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            slot_duration_min=slot_duration_min,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        db.add(schedule)
        await db.commit()
        await db.refresh(schedule)
        return schedule

    @staticmethod
    async def list_schedules(doctor_id: uuid.UUID, db: AsyncSession) -> list[DoctorSchedule]:
        result = await db.execute(
            select(DoctorSchedule)
            .where(DoctorSchedule.doctor_id == doctor_id)
            .order_by(DoctorSchedule.day_of_week, DoctorSchedule.start_time)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_time_off(
        doctor_id: uuid.UUID,
        start_ts: datetime,
        end_ts: datetime,
        reason: str | None,
        db: AsyncSession,
    ) -> DoctorTimeOff:
        if end_ts <= start_ts:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="end_ts must be after start_ts")
        toff = DoctorTimeOff(doctor_id=doctor_id, start_ts=start_ts, end_ts=end_ts, reason=reason)
        db.add(toff)
        await db.commit()
        await db.refresh(toff)
        return toff

    @staticmethod
    async def list_time_off(doctor_id: uuid.UUID, db: AsyncSession) -> list[DoctorTimeOff]:
        result = await db.execute(
            select(DoctorTimeOff)
            .where(DoctorTimeOff.doctor_id == doctor_id)
            .order_by(DoctorTimeOff.start_ts)
        )
        return list(result.scalars().all())

    @staticmethod
    async def generate_slots(
        doctor_id: uuid.UUID,
        from_date: date,
        to_date: date,
        db: AsyncSession,
    ) -> int:
        """
        Materialize slots from DoctorSchedule records for [from_date, to_date].
        Skips dates covered by DoctorTimeOff.
        Skips slots that already exist (idempotent).
        Returns count of newly created slots.
        """
        if to_date < from_date:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="to_date must be >= from_date")
        if (to_date - from_date).days > 180:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Range cannot exceed 180 days")

        # Load doctor to get facility/department
        doc_result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
        doctor: Doctor | None = doc_result.scalar_one_or_none()
        if not doctor:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Doctor not found")

        # Load schedules active during the date range
        sched_result = await db.execute(
            select(DoctorSchedule).where(
                DoctorSchedule.doctor_id == doctor_id,
                DoctorSchedule.effective_from <= to_date,
                (DoctorSchedule.effective_to == None) | (DoctorSchedule.effective_to >= from_date),
            )
        )
        schedules = list(sched_result.scalars().all())

        # Load time-off windows overlapping the date range
        toff_result = await db.execute(
            select(DoctorTimeOff).where(
                DoctorTimeOff.doctor_id == doctor_id,
                DoctorTimeOff.start_ts < datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc),
                DoctorTimeOff.end_ts > datetime.combine(from_date, time.min, tzinfo=timezone.utc),
            )
        )
        time_offs = list(toff_result.scalars().all())

        # Load already-existing slots for this doctor in the date range (for dedup)
        existing_result = await db.execute(
            select(Slot.date, Slot.start_time).where(
                Slot.doctor_id == doctor_id,
                Slot.date >= from_date,
                Slot.date <= to_date,
            )
        )
        existing_keys = {(row.date, row.start_time) for row in existing_result.all()}

        created = 0
        current = from_date
        while current <= to_date:
            dow = current.weekday()  # 0=Mon

            for sched in schedules:
                if sched.day_of_week != dow:
                    continue
                if current < sched.effective_from:
                    continue
                if sched.effective_to and current > sched.effective_to:
                    continue

                # Generate slot start times within the schedule window
                slot_start = datetime.combine(current, sched.start_time, tzinfo=timezone.utc)
                window_end = datetime.combine(current, sched.end_time, tzinfo=timezone.utc)
                duration = timedelta(minutes=sched.slot_duration_min)

                while slot_start + duration <= window_end:
                    slot_end = slot_start + duration

                    # Skip if covered by time-off
                    in_time_off = any(
                        toff.start_ts <= slot_start < toff.end_ts
                        for toff in time_offs
                    )
                    if in_time_off:
                        slot_start = slot_end
                        continue

                    key = (current, slot_start.time())
                    if key not in existing_keys:
                        db.add(Slot(
                            doctor_id=doctor_id,
                            facility_id=sched.facility_id,
                            department_id=doctor.department_id,
                            date=current,
                            start_time=slot_start.time(),
                            end_time=slot_end.time(),
                            status="available",
                        ))
                        existing_keys.add(key)
                        created += 1

                    slot_start = slot_end

            current += timedelta(days=1)

        await db.commit()
        slots_generated_total.inc(created)
        return created
