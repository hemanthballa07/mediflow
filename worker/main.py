"""
Notification worker — polls the notifications outbox, dispatches email/SMS,
handles exponential-backoff retries.

Run: python -m worker.main
"""
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.models import Notification
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("worker.notifications")
settings = get_settings()

# Backoff delays (minutes) for attempt 1, 2, 3+
_BACKOFF_MINUTES = [1, 5, 15]


# ── Dispatchers ───────────────────────────────────────────────────────────────

async def _dispatch_email(notif: Notification) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = notif.subject or notif.type
    msg["From"] = settings.SMTP_FROM
    msg["To"] = notif.recipient
    msg.attach(MIMEText(notif.body, "plain"))

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _smtp_send, msg.as_string(), notif.recipient)


def _smtp_send(raw_message: str, recipient: str) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        smtp.sendmail(settings.SMTP_FROM, [recipient], raw_message)


async def _dispatch_sms(notif: Notification) -> None:
    log.info("SMS dispatch (stub)", extra={
        "recipient": notif.recipient, "body_preview": notif.body[:80]
    })


_DISPATCHERS = {
    "email": _dispatch_email,
    "sms": _dispatch_sms,
}


# ── Batch processor ───────────────────────────────────────────────────────────

async def _process_batch() -> int:
    now = datetime.now(timezone.utc)
    processed = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Notification)
            .where(
                Notification.status == "pending",
                Notification.next_attempt_at <= now,
            )
            .order_by(Notification.next_attempt_at)
            .limit(settings.NOTIFICATION_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        notifications = result.scalars().all()

        for notif in notifications:
            dispatcher = _DISPATCHERS.get(notif.channel)
            if not dispatcher:
                notif.status = "skipped"
                notif.updated_at = now
                processed += 1
                continue

            try:
                await dispatcher(notif)
                notif.status = "sent"
                notif.sent_at = now
                notif.updated_at = now
                log.info("Notification sent", extra={
                    "id": str(notif.id), "type": notif.type, "channel": notif.channel
                })
            except Exception as exc:
                notif.attempts += 1
                notif.error = str(exc)[:500]
                notif.updated_at = now

                if notif.attempts >= notif.max_attempts:
                    notif.status = "failed"
                    log.error("Notification permanently failed", extra={
                        "id": str(notif.id), "error": notif.error
                    })
                else:
                    delay = _BACKOFF_MINUTES[min(notif.attempts - 1, len(_BACKOFF_MINUTES) - 1)]
                    notif.next_attempt_at = now + timedelta(minutes=delay)
                    log.warning("Notification retry queued", extra={
                        "id": str(notif.id),
                        "attempt": notif.attempts,
                        "next_at": notif.next_attempt_at.isoformat(),
                    })
            processed += 1

        await db.commit()

    return processed


# ── Main loop ─────────────────────────────────────────────────────────────────

async def _run() -> None:
    log.info("Notification worker started", extra={
        "smtp_host": settings.SMTP_HOST,
        "smtp_port": settings.SMTP_PORT,
        "poll_interval": settings.NOTIFICATION_POLL_INTERVAL,
    })
    while True:
        try:
            n = await _process_batch()
            if n:
                log.info(f"Dispatched {n} notifications")
        except Exception as exc:
            log.error("Worker iteration error", extra={"error": str(exc)})

        await asyncio.sleep(settings.NOTIFICATION_POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(_run())
