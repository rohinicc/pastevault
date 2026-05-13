from pydantic_settings import BaseSettings
from pydantic import model_validator


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@db:5432/pastevault"
    REDIS_URL: str = "redis://redis:6379/0"
    ENCRYPTION_KEY: str = ""
    BASE_URL: str = "http://localhost:8000"
    LOG_LEVEL: str = "INFO"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    RATE_LIMIT_PER_MINUTE: int = 100
    CLEANUP_INTERVAL_SECONDS: int = 3600
    MAX_PASTE_SIZE: int = 500_000

    @model_validator(mode="after")
    def check_encryption_key(self) -> "Settings":
        if not self.ENCRYPTION_KEY:
            raise ValueError(
                "ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
                "and add it to your .env file."
            )
        return self

    model_config = {"env_file": ".env"}


settings = Settings()
