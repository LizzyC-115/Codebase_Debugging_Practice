"""
Application Configuration

Centralized configuration management using Pydantic settings.
Loads from environment variables with fallback to .env file.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Note: We use lru_cache on get_settings() to ensure we only load
    configuration once, avoiding repeated file I/O and env parsing.
    This is a common pattern but can bite you during testing if you
    need to modify settings - you'll need to clear the cache.
    """

    # Database settings
    # FIXME: In production, we should split read/write replicas
    # but for now using single connection string
    DATABASE_URL: str = "postgresql://localhost/saas_dev"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40

    # Security settings
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Redis for caching and rate limiting
    REDIS_URL: str = "redis://localhost:6379/0"

    # Application settings
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Rate limiting
    # TODO: Make these per-tenant configurable in database
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Using lru_cache ensures we only instantiate settings once.
    This is efficient but means settings are immutable at runtime.
    """
    return Settings()
