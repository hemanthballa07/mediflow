from starlette.requests import Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings


def get_user_id_from_request(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from app.core.security import decode_access_token
            payload = decode_access_token(token)
            sub = payload.get("sub")
            if sub:
                return sub
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=get_remote_address, storage_uri=get_settings().REDIS_URL)
