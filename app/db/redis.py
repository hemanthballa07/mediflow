import time
import json
import logging
from enum import Enum
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

_redis: aioredis.Redis | None = None
log = logging.getLogger(__name__)

_FAILURE_THRESHOLD = 5
_RECOVERY_TIMEOUT = 30.0


class _State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


_state = _State.CLOSED
_failure_count = 0
_opened_at: float | None = None


def _transition(new_state: _State) -> None:
    global _state, _failure_count, _opened_at
    old = _state.value
    _state = new_state
    if new_state == _State.OPEN:
        _opened_at = time.monotonic()
    elif new_state == _State.CLOSED:
        _failure_count = 0
        _opened_at = None
    log.info(json.dumps({
        "event": "circuit_breaker_state_change",
        "from": old,
        "to": new_state.value,
        "timestamp": time.time(),
    }))


async def execute_redis(coro) -> Any:
    """Run a Redis coroutine through the circuit breaker.

    Returns None on open circuit or Redis failure — callers treat this as
    a cache miss and degrade gracefully without propagating errors.
    """
    global _state, _failure_count

    if _state == _State.OPEN:
        elapsed = time.monotonic() - (_opened_at or 0.0)
        if elapsed >= _RECOVERY_TIMEOUT:
            _transition(_State.HALF_OPEN)
        else:
            return None

    try:
        result = await coro
        if _state == _State.HALF_OPEN:
            _transition(_State.CLOSED)
        elif _state == _State.CLOSED:
            _failure_count = 0
        return result
    except Exception:
        _failure_count += 1
        if _state == _State.HALF_OPEN or _failure_count >= _FAILURE_THRESHOLD:
            _transition(_State.OPEN)
        return None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
