from pydantic import EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List

class Settings(BaseSettings):
    # environment
    ENVIRONMENT: str
    DATABASE_URL: str
    PRODUCTION_DB_URL: str
    SECRET_KEY: str
    ALEMBIC_DB_URL: str
    DEVICE_FINGERPRINT_SECRET: str

    # jwt user session management
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    MAX_ACTIVE_SESSIONS: int
    MAX_LOGIN_ATTEMPTS: int
    LOGIN_ATTEMPT_WINDOW_MINUTES: int
    ALGORITHM: str
    CORS_ORIGINS: List[str]

    # project details
    API_PREFIX: str
    PROJECT_NAME: str
    VERSION: str

    # super admin credentials
    SUPER_ADMIN_USER_NAME: str
    SUPER_ADMIN_PASSWORD_HASH: str
    SUPER_ADMIN_TOKEN_EXPIRE_MINUTES: int

    # email
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: EmailStr
    SMTP_PASSWORD: str
    FROM_EMAIL: EmailStr
    FROM_NAME: str

    # sms
    SMS_PROVIDER: str = "arkesel"

    # arkesel sms
    ARKESEL_API_KEY: str | None = None   # Required in production
    ARKESEL_BASE_URL: str = "https://sms.arkesel.com/sms/api"
    ARKESEL_SENDER_ID: str = "HepVac"

    # reminder settings
    REMINDER_SCAN_INTERVAL: int = 300        # seconds between reminder scans (default 5 min)
    REMINDER_ADVANCE_DAYS: int = 1           # days ahead to scan for due reminders
    REMINDER_MAX_RETRIES: int = 3

    # redis / caching
    REDIS_URL: str
    CACHE_TYPE: str
    CACHE_ENABLED: bool
    CACHE_DEFAULT_TTL: int
    CACHE_KEY_PREFIX: str

    # system settings
    SYSTEM_STATUS: str = "up"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

# lru_cache so settings are singleton
@lru_cache()
def get_settings() -> Settings:
    return Settings() # type: ignore

settings = get_settings()