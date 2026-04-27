import logging
import redis.asyncio as aioredis
from app.core.config import get_settings

log = logging.getLogger(__name__)

_pubsub_redis: aioredis.Redis | None = None


async def get_pubsub_redis() -> aioredis.Redis:
    global _pubsub_redis
    if _pubsub_redis is None:
        settings = get_settings()
        _pubsub_redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _pubsub_redis


async def close_pubsub_redis() -> None:
    global _pubsub_redis
    if _pubsub_redis:
        await _pubsub_redis.aclose()
        _pubsub_redis = None


async def publish(channel: str, message: str) -> None:
    try:
        r = await get_pubsub_redis()
        await r.publish(channel, message)
    except Exception as e:
        log.warning("Redis publish failed: %s", e)
