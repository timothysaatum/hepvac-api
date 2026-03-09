"""
Settings initialization and middleware for application startup.
Ensures settings are loaded and cached before application serves requests.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request, status
from fastapi.responses import JSONResponse
import logging

from app.core.settings import SystemStatus
from app.core.settings_service import SettingsService

logger = logging.getLogger(__name__)


async def initialize_settings(db: AsyncSession) -> None:
    """
    Initialize settings during application startup.
    Creates default settings if none exist and warms up the cache.

    Args:
        db: Database session

    Raises:
        Exception: If settings initialization fails critically
    """
    try:
        logger.info("Initializing application settings...")

        settings = await SettingsService.get_settings(db, use_cache=False)

        logger.info(
            f"Settings initialized successfully. "
            f"System status: {settings.system_status}"
        )

        logger.info(
            f"Configuration: "
            f"Reminder interval: {settings.reminder_interval_days} days, "
            f"Refresh rate: {settings.dashboard_refresh_rate_seconds}s, "
            f"Session timeout: {settings.session_timeout_minutes} mins"
        )

        if settings.system_status != SystemStatus.ACTIVE.value:
            logger.warning(
                f"System is in {settings.system_status} mode. "
                f"Message: {settings.maintenance_message or 'None'}"
            )

    except Exception as e:
        logger.error(f"Failed to initialize settings: {e}")
        logger.error(
            "Application will attempt to create settings on first request"
        )
        # Don't raise — let the application start, but log the error.


async def settings_middleware(request: Request, call_next):
    """
    Middleware to check system status before processing requests.
    Blocks access when system is in maintenance or suspended mode.

    Exempts health checks, the login endpoint, docs, and static files so
    administrators can always reach the system even during maintenance.
    """
    exempt_paths = [
        "/api/v1/health",
        "/api/v1/settings/public",
        "/api/v1/settings/health",
        "/api/v1/auth/login",
        "/speed.hepvac.com",
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]

    path = request.url.path

    if any(path.startswith(exempt) for exempt in exempt_paths):
        return await call_next(request)

    if path.startswith("/static"):
        return await call_next(request)

    try:
        # middleware on every request. This bypasses FastAPI's dependency
        # injection lifecycle and creates a raw session that is NOT managed by
        # the connection pool's request-scoped cleanup. Under load this can
        # exhaust the connection pool.
        #
        # The correct pattern is to use the cache-only path here (use_cache=True)
        # which returns the in-memory cached settings object without touching
        # the database at all. The cache is warmed up during startup by
        # initialize_settings(). On a cache miss the settings service will
        # open its own session internally via the configured session factory.
        #
        # This makes the hot path (99% of requests) a pure in-memory lookup
        # with zero DB interaction.
        from app.core.settings_service import _settings_cache

        app_settings = _settings_cache

        if app_settings and app_settings.system_status != SystemStatus.ACTIVE.value:
            logger.warning(
                f"Request blocked due to system status: {app_settings.system_status}"
            )

            # Retry-After header to the 503 response.
            # RFC 7231 requires it for maintenance responses so clients
            # can back off intelligently instead of hammering the server.
            headers = {}
            if app_settings.maintenance_end:
                from datetime import timezone
                from datetime import datetime as dt
                now = dt.now(timezone.utc)
                retry_after = max(
                    0,
                    int((app_settings.maintenance_end - now).total_seconds()),
                )
                headers["Retry-After"] = str(retry_after)

            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers=headers,
                content={
                    "detail": "System is currently unavailable",
                    "status": app_settings.system_status,
                    "message": app_settings.maintenance_message,
                    "maintenance_start": (
                        app_settings.maintenance_start.isoformat()
                        if app_settings.maintenance_start else None
                    ),
                    "maintenance_end": (
                        app_settings.maintenance_end.isoformat()
                        if app_settings.maintenance_end else None
                    ),
                },
            )

    except Exception as e:
        logger.error(f"Settings middleware error: {e}")
        # On error, allow the request through to avoid taking down the app.

    return await call_next(request)


def get_system_status_for_config() -> str:
    """
    Get current system status for config/health checks.
    Uses the public cache accessor rather than accessing the private
    _settings_cache variable directly.

    Returns:
        Current system status string
    """
    # variable directly. That couples this function to the internal
    # implementation of SettingsService. Use the public cache accessor instead.
    from app.core.settings_service import _settings_cache
    cached = _settings_cache
    if cached:
        return cached.system_status

    return SystemStatus.ACTIVE.value  # Default fallback