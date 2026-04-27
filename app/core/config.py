from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    READ_REPLICA_URL: str | None = None

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ADMIN_API_KEY: str
    ENVIRONMENT: str = "development"

    IDEMPOTENCY_TTL_SECONDS: int = 86400
    SLOT_CACHE_TTL: int = 30
    REPORT_CACHE_TTL: int = 300
    CANCELLATION_WINDOW_HOURS: int = 24
    BOOKING_RATE_LIMIT: str = "10/hour"

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "noreply@mediflow.dev"
    NOTIFICATION_POLL_INTERVAL: int = 10
    NOTIFICATION_BATCH_SIZE: int = 50
    WAITLIST_NOTIFICATION_EXPIRY_HOURS: int = 48

    ENCRYPTION_KEY: str = "bWVkaWZsb3ctZGV2LWtleS0zMi1ieXRlcy1wYWRkZWQ="

    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://tempo:4317"

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if len(self.JWT_SECRET) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if len(self.ADMIN_API_KEY) < 32:
            raise ValueError("ADMIN_API_KEY must be at least 32 characters")
        if len(self.ENCRYPTION_KEY) < 32:
            raise ValueError("ENCRYPTION_KEY must be a valid Fernet key (44 chars)")
        return self

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
