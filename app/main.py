from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.db.session import engine
from app.db.redis import get_redis, close_redis
from app.models import models  # noqa: F401 — ensure models are registered
from app.core.metrics import start_metrics_server
from app.middleware.metrics import MetricsMiddleware
from app.core.logging import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting MediFlow API")
    # Start Prometheus metrics server on :9100 (separate from API port)
    start_metrics_server(port=9100)
    # Warm Redis connection
    await get_redis()
    yield
    log.info("Shutting down MediFlow API")
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="MediFlow",
    description="Hospital scheduling and lab report access platform",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "mediflow"}
