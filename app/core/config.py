from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://mediflow:mediflow@localhost:5432/mediflow"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "dev-secret-change-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ADMIN_API_KEY: str = "changeme-replace-in-prod"
    ENVIRONMENT: str = "development"

    # Idempotency key TTL in seconds (24h)
    IDEMPOTENCY_TTL_SECONDS: int = 86400

    # Redis cache TTL for slot availability (seconds)
    SLOT_CACHE_TTL: int = 30

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
