import hmac
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.config import get_settings
from app.services import hl7 as hl7_svc
from fastapi import Depends

router = APIRouter(tags=["hl7"])
settings = get_settings()

_HL7_CONTENT_TYPE = "x-application/hl7-v2+er7"


def verify_admin_key(x_admin_api_key: str = Header(..., alias="X-Admin-Api-Key")):
    if not hmac.compare_digest(x_admin_api_key, settings.ADMIN_API_KEY):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API key")


@router.post("/hl7/adt")
async def ingest_adt(
    request: Request,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    body_bytes = await request.body()
    try:
        raw = body_bytes.decode("utf-8")
    except Exception:
        raw = body_bytes.decode("latin-1")

    try:
        parsed = hl7_svc.parse_message(raw)
    except Exception as exc:
        ack = hl7_svc.build_ack({}, "AE", f"Parse error: {str(exc)[:200]}")
        return Response(content=ack, media_type=_HL7_CONTENT_TYPE)

    msg_class = hl7_svc._field(parsed, "MSH", 9, 0)
    msg_event = hl7_svc._field(parsed, "MSH", 9, 1)
    msg_type_field = f"{msg_class}^{msg_event}" if msg_class else ""

    try:
        if msg_type_field.startswith("ADT^A01"):
            await hl7_svc.handle_a01(parsed, db)
            await db.commit()
        elif msg_type_field.startswith("ADT^A08"):
            await hl7_svc.handle_a08(parsed, db)
            await db.commit()
        else:
            ack = hl7_svc.build_ack(parsed, "AE", f"Unsupported message type: {msg_type_field}")
            return Response(content=ack, media_type=_HL7_CONTENT_TYPE)
    except Exception as exc:
        await db.rollback()
        ack = hl7_svc.build_ack(parsed, "AE", str(exc)[:200])
        return Response(content=ack, media_type=_HL7_CONTENT_TYPE)

    ack = hl7_svc.build_ack(parsed, "AA")
    return Response(content=ack, media_type=_HL7_CONTENT_TYPE)
