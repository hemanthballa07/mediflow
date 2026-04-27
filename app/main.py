from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api.v1 import api_router
from app.api.v1.endpoints import fhir as fhir_router
from app.api.v1.endpoints import hl7 as hl7_router
from app.api.v1.endpoints import websockets as ws_router
from app.db.session import engine, AsyncSessionLocal, _replica_engine
from app.db.redis import get_redis, close_redis
from app.db.redis_pubsub import get_pubsub_redis, close_pubsub_redis
from app.models import models  # noqa: F401 — ensure models are registered
from app.core.metrics import start_metrics_server
from app.core.telemetry import setup_telemetry
from app.middleware.metrics import MetricsMiddleware
from app.core.logging import get_logger
from app.core.limiter import limiter

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting MediFlow API")
    start_metrics_server(port=9100)
    setup_telemetry(app)
    await get_redis()
    await get_pubsub_redis()
    yield
    log.info("Shutting down MediFlow API")
    await close_redis()
    await close_pubsub_redis()
    await engine.dispose()
    if _replica_engine is not None:
        await _replica_engine.dispose()


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)


app = FastAPI(
    title="MediFlow",
    description="Hospital scheduling and lab report access platform",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api_router)
app.include_router(fhir_router.router)
app.include_router(hl7_router.router)
app.include_router(ws_router.router)


@app.get("/health/live", tags=["health"])
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_ready():
    db_status = "ok"
    redis_status = "ok"

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        r = await get_redis()
        await r.ping()
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "error"
    return JSONResponse(
        content={"status": overall, "service": "mediflow", "db": db_status, "redis": redis_status},
        status_code=200 if overall == "ok" else 503,
    )
