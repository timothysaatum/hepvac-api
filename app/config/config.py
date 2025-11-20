from pydantic import EmailStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    ENVIRONMENT: str
    DATABASE_URL: str
    PRODUCTION_DB_URL: str
    SECRET_KEY: str
    ALEMBIC_DB_URL: str

    # jwt user session management
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    MAX_ACTIVE_SESSIONS: int
    MAX_LOGIN_ATTEMPTS: int
    LOGIN_ATTEMPT_WINDOW_MINUTES: int
    ALGORITHM: str
    CORS_ORIGINS: list[str]

    # project details
    API_PREFIX: str
    PROJECT_NAME: str
    VERSION: str

    # super admin credentials
    SUPER_ADMIN_USER_NAME: str
    SUPER_ADMIN_PASSWORD_HASH: str

    # Notification config

    # email
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: EmailStr
    SMTP_PASSWORD: str
    FROM_EMAIL: EmailStr
    FROM_NAME: str

    # sms
    AFRICAISTALKING: str
    AFRICAISTALKING_AUTH_TOKEN: str
    AFRICAISTALKING_PHONE_NUMBER: str
    TERMII_API_KEY: str
    TERMII_SENDER_ID: str
    SMS_PROVIDER: str

    # redis
    REDIS_URL: str
    CACHE_TYPE: str
    CACHE_ENABLED: bool
    CACHE_DEFAULT_TTL: int
    CACHE_KEY_PREFIX: str

    # system setttings
    SYSTEM_STATUS: str = "up"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
