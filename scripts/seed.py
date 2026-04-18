"""
Seed script — run via: docker compose exec api python scripts/seed.py
Creates: 1 admin, 1 doctor user + doctor record, 1 patient, 10 slots, 5 lab reports.
Prints credentials at the end.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date, time, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal, engine
from app.models.models import User, Doctor, Slot, LabReport
from app.core.security import hash_password


async def seed():
    async with engine.begin() as conn:
        pass  # ensure engine is connected

    async with AsyncSessionLocal() as db:
        # ── Admin ──────────────────────────────────────────────────────────────
        admin = User(
            email="admin@mediflow.dev",
            hashed_password=hash_password("admin123"),
            name="Admin User",
            role="admin",
        )
        db.add(admin)
        await db.flush()

        # ── Doctor user ────────────────────────────────────────────────────────
        doc_user = User(
            email="doctor@mediflow.dev",
            hashed_password=hash_password("doctor123"),
            name="Dr. Sarah Chen",
            role="doctor",
        )
        db.add(doc_user)
        await db.flush()

        doctor = Doctor(user_id=doc_user.id, specialty="General Practice")
        db.add(doctor)
        await db.flush()

        # ── Patient ────────────────────────────────────────────────────────────
        patient = User(
            email="patient@mediflow.dev",
            hashed_password=hash_password("patient123"),
            name="John Patient",
            role="patient",
        )
        db.add(patient)
        await db.flush()

        # ── Slots (next 5 days, 2 slots/day) ──────────────────────────────────
        slots = []
        for day_offset in range(1, 6):
            d = date.today() + timedelta(days=day_offset)
            for hour in (9, 14):
                slot = Slot(
                    doctor_id=doctor.id,
                    date=d,
                    start_time=time(hour, 0),
                    end_time=time(hour, 30),
                    status="available",
                )
                db.add(slot)
                slots.append(slot)
        await db.flush()

        # ── Lab Reports ────────────────────────────────────────────────────────
        statuses = ["PENDING", "READY", "READY", "ARCHIVED", "PENDING"]
        types    = ["blood", "xray", "urine", "blood", "xray"]
        for i in range(5):
            report = LabReport(
                patient_id=patient.id,
                report_type=types[i],
                status=statuses[i],
                data=f"Sample {types[i]} report data #{i+1}",
            )
            db.add(report)

        await db.commit()

        print("\n── MediFlow seed complete ───────────────────────────────")
        print(f"Admin    → admin@mediflow.dev       / admin123")
        print(f"Doctor   → doctor@mediflow.dev      / doctor123")
        print(f"Patient  → patient@mediflow.dev     / patient123")
        print(f"Doctor ID:  {doctor.id}")
        print(f"Slots created: {len(slots)}")
        print(f"First slot ID for contention test: {slots[0].id}")
        print("─────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(seed())
