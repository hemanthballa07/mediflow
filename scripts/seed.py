"""
Seed script — run via: docker compose exec api python scripts/seed.py
Creates: 2 facilities, 3 specialties, 4 departments, 2 doctors, 1 admin, 1 patient,
         10 slots, 5 lab reports. Prints credentials at the end.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import uuid
from datetime import date, time, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal, engine
from app.models.models import User, Doctor, Slot, LabReport, Facility, Department, Specialty, Room
from app.core.security import hash_password
from app.core.encryption import encrypt, email_hash as compute_email_hash

# Match the backfill UUIDs from migration 002 so re-seeding on existing DB is idempotent
DEFAULT_FACILITY_ID  = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_SPECIALTY_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
DEFAULT_DEPT_ID      = uuid.UUID("00000000-0000-0000-0000-000000000003")


async def seed():
    async with engine.begin() as conn:
        pass  # ensure engine is connected

    async with AsyncSessionLocal() as db:

        # ── Specialties (skip if already inserted by migration backfill) ─────────
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        await db.execute(
            pg_insert(Specialty).values(
                id=DEFAULT_SPECIALTY_ID, name="General Practice", code="GP"
            ).on_conflict_do_nothing()
        )
        cardio_spec = Specialty(name="Cardiology", code="CARD")
        radiology_spec = Specialty(name="Radiology", code="RAD")
        db.add_all([cardio_spec, radiology_spec])
        await db.flush()
        # reload the GP specialty so we have the ORM object
        from sqlalchemy import select as sa_select
        gp_spec = (await db.execute(sa_select(Specialty).where(Specialty.id == DEFAULT_SPECIALTY_ID))).scalar_one()

        # ── Facilities ─────────────────────────────────────────────────────────
        await db.execute(
            pg_insert(Facility).values(
                id=DEFAULT_FACILITY_ID,
                name="MediFlow General Hospital",
                code="MGH",
                address="1 Hospital Drive, New York, NY 10001",
                timezone="America/New_York",
                active=True,
            ).on_conflict_do_nothing()
        )
        west_clinic = Facility(
            name="MediFlow West Clinic",
            code="MWC",
            address="500 West Ave, Brooklyn, NY 11201",
            timezone="America/New_York",
        )
        db.add(west_clinic)
        await db.flush()
        main_hospital = (await db.execute(sa_select(Facility).where(Facility.id == DEFAULT_FACILITY_ID))).scalar_one()

        # ── Departments ────────────────────────────────────────────────────────
        await db.execute(
            pg_insert(Department).values(
                id=DEFAULT_DEPT_ID,
                facility_id=DEFAULT_FACILITY_ID,
                specialty_id=DEFAULT_SPECIALTY_ID,
                name="General Medicine",
                code="GM",
            ).on_conflict_do_nothing()
        )
        cardio_dept = Department(
            facility_id=main_hospital.id,
            specialty_id=cardio_spec.id,
            name="Cardiology",
            code="CARD",
        )
        radiology_dept = Department(
            facility_id=main_hospital.id,
            specialty_id=radiology_spec.id,
            name="Radiology",
            code="RAD",
        )
        west_gp_dept = Department(
            facility_id=west_clinic.id,
            specialty_id=gp_spec.id,
            name="General Practice",
            code="GP",
        )
        db.add_all([cardio_dept, radiology_dept, west_gp_dept])
        await db.flush()
        gen_med_dept = (await db.execute(sa_select(Department).where(Department.id == DEFAULT_DEPT_ID))).scalar_one()

        # ── Rooms ──────────────────────────────────────────────────────────────
        db.add_all([
            Room(facility_id=main_hospital.id, department_id=gen_med_dept.id, name="Room 101", kind="exam"),
            Room(facility_id=main_hospital.id, department_id=gen_med_dept.id, name="Room 102", kind="exam"),
            Room(facility_id=main_hospital.id, department_id=cardio_dept.id, name="Cath Lab 1", kind="procedure"),
            Room(facility_id=main_hospital.id, department_id=radiology_dept.id, name="MRI Suite A", kind="imaging"),
            Room(facility_id=west_clinic.id, department_id=west_gp_dept.id, name="Room 201", kind="exam"),
        ])
        await db.flush()

        def make_user(email: str, password: str, name: str, role: str, **kwargs) -> User:
            return User(
                email=encrypt(email),
                email_hash=compute_email_hash(email),
                hashed_password=hash_password(password),
                name=encrypt(name),
                role=role,
                **kwargs,
            )

        # ── Admin ──────────────────────────────────────────────────────────────
        admin = make_user(
            "admin@mediflow.dev", "admin123", "Admin User", "admin",
            home_facility_id=main_hospital.id,
        )
        db.add(admin)
        await db.flush()

        # ── Doctor 1 — General Practice (main hospital) ────────────────────────
        doc_user = make_user(
            "doctor@mediflow.dev", "doctor123", "Dr. Sarah Chen", "doctor",
            home_facility_id=main_hospital.id,
        )
        db.add(doc_user)
        await db.flush()

        doctor = Doctor(
            user_id=doc_user.id,
            specialty="General Practice",
            facility_id=main_hospital.id,
            department_id=gen_med_dept.id,
            specialty_id=gp_spec.id,
        )
        db.add(doctor)
        await db.flush()

        # ── Doctor 2 — Cardiology (main hospital) ──────────────────────────────
        cardio_user = make_user(
            "cardiologist@mediflow.dev", "cardio123", "Dr. James Park", "doctor",
            home_facility_id=main_hospital.id,
        )
        db.add(cardio_user)
        await db.flush()

        cardiologist = Doctor(
            user_id=cardio_user.id,
            specialty="Cardiology",
            facility_id=main_hospital.id,
            department_id=cardio_dept.id,
            specialty_id=cardio_spec.id,
        )
        db.add(cardiologist)
        await db.flush()

        # ── Patient ────────────────────────────────────────────────────────────
        patient = make_user(
            "patient@mediflow.dev", "patient123", "John Patient", "patient",
            home_facility_id=main_hospital.id,
        )
        db.add(patient)
        await db.flush()

        # ── Slots — Dr. Chen (next 5 days, 2 slots/day) ────────────────────────
        slots = []
        for day_offset in range(1, 6):
            d = date.today() + timedelta(days=day_offset)
            for hour in (9, 14):
                slot = Slot(
                    doctor_id=doctor.id,
                    facility_id=main_hospital.id,
                    department_id=gen_med_dept.id,
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
                facility_id=main_hospital.id,
                department_id=radiology_dept.id if types[i] == "xray" else gen_med_dept.id,
                report_type=types[i],
                status=statuses[i],
                data=f"Sample {types[i]} report data #{i+1}",
            )
            db.add(report)

        await db.commit()

        print("\n── MediFlow seed complete ───────────────────────────────────────────")
        print(f"Admin         → admin@mediflow.dev          / admin123")
        print(f"Doctor (GP)   → doctor@mediflow.dev         / doctor123")
        print(f"Doctor (Card) → cardiologist@mediflow.dev   / cardio123")
        print(f"Patient       → patient@mediflow.dev        / patient123")
        print(f"")
        print(f"Facility: {main_hospital.name}  ({main_hospital.id})")
        print(f"Facility: {west_clinic.name}   ({west_clinic.id})")
        print(f"Doctor (GP) ID:    {doctor.id}")
        print(f"Doctor (Card) ID:  {cardiologist.id}")
        print(f"Slots created: {len(slots)}")
        print(f"First slot ID for contention test: {slots[0].id}")
        print("────────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(seed())
