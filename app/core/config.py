from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ADMIN_API_KEY: str
    ENVIRONMENT: str = "development"

    IDEMPOTENCY_TTL_SECONDS: int = 86400
    SLOT_CACHE_TTL: int = 30

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if len(self.JWT_SECRET) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if len(self.ADMIN_API_KEY) < 32:
            raise ValueError("ADMIN_API_KEY must be at least 32 characters")
        return self

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
