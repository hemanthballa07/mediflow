from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid as _uuid_mod

from app.models.models import User, AuditLog
from app.core.encryption import encrypt as encrypt_value, email_hash as hmac_email


def parse_message(raw: str) -> dict:
    raw = raw.replace("\r\n", "\r").replace("\n", "\r")
    segments = [s for s in raw.split("\r") if s.strip()]
    result: dict[str, list[list[list[str]]]] = {}
    for seg in segments:
        fields = seg.split("|")
        seg_name = fields[0]
        parsed_fields = []
        for f in fields[1:]:
            repetitions = f.split("~")
            parsed_fields.append([comp.split("^") for comp in repetitions])
        result.setdefault(seg_name, []).append(parsed_fields)
    return result


def _field(parsed: dict, seg: str, field_idx: int, comp_idx: int = 0, rep_idx: int = 0) -> str:
    segs = parsed.get(seg, [])
    if not segs:
        return ""
    fields = segs[0]
    # MSH.1 = field separator (|) is not stored in parsed_fields, so MSH field N is at index N-2
    actual_idx = field_idx - 2 if seg == "MSH" else field_idx - 1
    if actual_idx < 0 or actual_idx >= len(fields):
        return ""
    reps = fields[actual_idx]
    if rep_idx >= len(reps):
        return ""
    comps = reps[rep_idx]
    if comp_idx >= len(comps):
        return ""
    return comps[comp_idx].strip()


def build_ack(parsed: dict, code: str, error: str | None = None) -> str:
    msh = parsed.get("MSH", [])
    control_id = _field(parsed, "MSH", 10) if msh else "UNKNOWN"
    sending_app = _field(parsed, "MSH", 3) or "UNKNOWN"
    sending_fac = _field(parsed, "MSH", 4) or "UNKNOWN"
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ack_msh = f"MSH|^~\\&|MEDIFLOW||{sending_app}|{sending_fac}|{now}||ACK|{control_id}ACK|P|2.5"
    error_text = error or ""
    ack_msa = f"MSA|{code}|{control_id}|{error_text}"
    return f"{ack_msh}\r{ack_msa}\r"


async def handle_a01(parsed: dict, db: AsyncSession) -> None:
    patient_id_raw = _field(parsed, "PID", 3)
    family_name = _field(parsed, "PID", 5, 0)
    given_name = _field(parsed, "PID", 5, 1)
    dob_raw = _field(parsed, "PID", 7)
    phone = _field(parsed, "PID", 13)

    name = f"{given_name} {family_name}".strip() or "Unknown"
    stub_email = f"hl7_{patient_id_raw}@hl7.import" if patient_id_raw else f"hl7_{_uuid_mod.uuid4().hex[:8]}@hl7.import"

    encrypted_email = encrypt_value(stub_email)
    hashed_email = hmac_email(stub_email)

    result = await db.execute(select(User).where(User.email_hash == hashed_email))
    user = result.scalar_one_or_none()

    if user is None:
        import bcrypt
        random_pw = _uuid_mod.uuid4().hex
        hashed_pw = bcrypt.hashpw(random_pw.encode(), bcrypt.gensalt()).decode()
        user = User(
            email=encrypted_email,
            email_hash=hashed_email,
            hashed_password=hashed_pw,
            name=name,
            role="patient",
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
    else:
        user.name = name
        user.email = encrypted_email
        await db.flush()

    audit = AuditLog(
        ts=datetime.now(timezone.utc),
        user_id=user.id,
        action="HL7_INGESTED",
        target=str(user.id),
        details={
            "message_type": "ADT^A01",
            "patient_id_raw": patient_id_raw,
            "dob": dob_raw,
            "phone_present": bool(phone),
        },
    )
    db.add(audit)


async def handle_a08(parsed: dict, db: AsyncSession) -> None:
    patient_id_raw = _field(parsed, "PID", 3)
    family_name = _field(parsed, "PID", 5, 0)
    given_name = _field(parsed, "PID", 5, 1)
    dob_raw = _field(parsed, "PID", 7)

    name = f"{given_name} {family_name}".strip()
    stub_email = f"hl7_{patient_id_raw}@hl7.import" if patient_id_raw else None
    if not stub_email:
        return

    hashed_email = hmac_email(stub_email)
    result = await db.execute(select(User).where(User.email_hash == hashed_email))
    user = result.scalar_one_or_none()
    if user is None:
        return

    if name:
        user.name = name
    await db.flush()

    audit = AuditLog(
        ts=datetime.now(timezone.utc),
        user_id=user.id,
        action="HL7_INGESTED",
        target=str(user.id),
        details={
            "message_type": "ADT^A08",
            "patient_id_raw": patient_id_raw,
            "dob": dob_raw,
        },
    )
    db.add(audit)
