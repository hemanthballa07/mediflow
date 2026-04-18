import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.metrics import http_requests_total, http_request_duration_seconds
from app.core.logging import get_logger

log = get_logger(__name__)

# Endpoints to skip tracking (noisy, low-value)
_SKIP = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        endpoint = request.url.path
        method = request.method
        status_code = str(response.status_code)

        http_requests_total.labels(
            method=method, endpoint=endpoint, status_code=status_code
        ).inc()
        http_request_duration_seconds.labels(
            method=method, endpoint=endpoint
        ).observe(duration)

        # Attach trace context to response headers for correlation
        log.info(
            "request",
            extra={
                "method": method,
                "path": endpoint,
                "status": status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        return response
