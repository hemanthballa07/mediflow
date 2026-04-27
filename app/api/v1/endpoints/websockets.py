import json
import uuid
import asyncio
from datetime import date as date_type
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from jwt.exceptions import InvalidTokenError

from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.db.redis_pubsub import get_pubsub_redis
from app.models.models import Doctor, Slot, User

router = APIRouter(tags=["websockets"])


async def _ws_authenticate(websocket: WebSocket, token: str | None) -> User | None:
    if not token:
        await websocket.close(code=4001)
        return None
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        await websocket.close(code=4001)
        return None

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001)
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()

    if user is None:
        await websocket.close(code=4001)
        return None
    return user


@router.websocket("/ws/slots/{doctor_id}/{date}")
async def ws_slot_availability(
    websocket: WebSocket,
    doctor_id: uuid.UUID,
    date: str,
    token: str | None = None,
):
    user = await _ws_authenticate(websocket, token)
    if user is None:
        return

    await websocket.accept()

    # Send initial snapshot
    try:
        async with AsyncSessionLocal() as db:
            parsed_date = date_type.fromisoformat(date)
            result = await db.execute(
                select(Slot).where(
                    Slot.doctor_id == doctor_id,
                    Slot.date == parsed_date,
                    Slot.status == "available",
                ).order_by(Slot.start_time)
            )
            slots = result.scalars().all()
            snapshot = [
                {"slot_id": str(s.id), "status": s.status, "start_time": str(s.start_time), "end_time": str(s.end_time)}
                for s in slots
            ]
        await websocket.send_json({"type": "snapshot", "slots": snapshot})
    except Exception:
        pass

    # Subscribe to Redis channel
    channel = f"slots:{doctor_id}:{date}"
    r = await get_pubsub_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)

    try:
        while True:
            message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0), timeout=2.0)
            if message and message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                except Exception:
                    pass
    except (WebSocketDisconnect, asyncio.TimeoutError, Exception):
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


@router.websocket("/ws/encounters/{encounter_id}/cds")
async def ws_encounter_cds(
    websocket: WebSocket,
    encounter_id: uuid.UUID,
    token: str | None = None,
):
    user = await _ws_authenticate(websocket, token)
    if user is None:
        return

    if user.role not in ("doctor", "admin"):
        await websocket.close(code=4003)
        return

    await websocket.accept()

    # Send existing alerts from audit log
    try:
        from app.models.models import AuditLog
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "CDS_ALERT_FIRED",
                    AuditLog.target == str(encounter_id),
                ).order_by(AuditLog.ts.asc())
            )
            rows = result.scalars().all()
            existing = []
            for row in rows:
                d = row.details or {}
                existing.append({
                    "rule_type": d.get("rule_type", ""),
                    "severity": d.get("severity", ""),
                    "message": d.get("message", ""),
                    "rule_key": d.get("rule_key"),
                })
        await websocket.send_json({"type": "existing_alerts", "alerts": existing})
    except Exception:
        pass

    # Subscribe to Redis channel
    channel = f"cds:{encounter_id}"
    r = await get_pubsub_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)

    try:
        while True:
            message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0), timeout=2.0)
            if message and message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await websocket.send_json({"type": "cds_alert", **data})
                except Exception:
                    pass
    except (WebSocketDisconnect, asyncio.TimeoutError, Exception):
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
