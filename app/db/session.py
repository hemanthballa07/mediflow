import time
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.metrics import db_query_duration_seconds

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    elapsed = time.perf_counter() - conn.info["query_start_time"].pop()
    db_query_duration_seconds.observe(elapsed)


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# ── Optional read replica ─────────────────────────────────────────────────────
_replica_engine = None
_ReplicaSessionLocal = None

if settings.READ_REPLICA_URL:
    _replica_engine = create_async_engine(
        settings.READ_REPLICA_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )
    _ReplicaSessionLocal = async_sessionmaker(
        _replica_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """Routes SELECT-only handlers to read replica when READ_REPLICA_URL is set.

    Falls back to primary if replica is not configured — zero behavior change
    in environments without READ_REPLICA_URL.
    """
    factory = _ReplicaSessionLocal if _ReplicaSessionLocal is not None else AsyncSessionLocal
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
