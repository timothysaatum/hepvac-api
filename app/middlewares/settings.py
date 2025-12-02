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
        
        # This will create default settings if none exist
        # and populate the cache
        settings = await SettingsService.get_settings(db, use_cache=False)
        
        logger.info(
            f"Settings initialized successfully. "
            f"System status: {settings.system_status}"
        )
        
        # Log important settings
        logger.info(
            f"Configuration: "
            f"Reminder interval: {settings.reminder_interval_days} days, "
            f"Refresh rate: {settings.dashboard_refresh_rate_seconds}s, "
            f"Session timeout: {settings.session_timeout_minutes} mins"
        )
        
        # Warn if system is not in active status
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
        # Don't raise - let application start but log the error


async def settings_middleware(request: Request, call_next):
    """
    Middleware to check system status before processing requests.
    Blocks access when system is in maintenance or suspended mode.
    
    Exempts:
    - Health check endpoints
    - Public settings endpoint
    - Login endpoint
    - Static files
    """
    # Define exempt paths that should always be accessible
    exempt_paths = [
        "/api/v1/health",
        "/api/v1/settings/public",
        "/api/v1/settings/health",
        "/api/v1/auth/login",
        "/speed.hepvac.com",
        "/",
        "/docs",
        "/redoc",
        "/openapi.json"
    ]
    
    # Check if path is exempt
    path = request.url.path
    if any(path.startswith(exempt) for exempt in exempt_paths):
        return await call_next(request)
    
    # Check if path is static files
    if path.startswith("/static"):
        return await call_next(request)
    
    # Get settings from cache (fast)
    try:
        # Import here to avoid circular dependency
        from app.db.session import AsyncSessionLocal
        
        async with AsyncSessionLocal() as db:
            settings = await SettingsService.get_settings(db, use_cache=True)
            
            # Check if system is accessible
            if settings.system_status != SystemStatus.ACTIVE.value:
                logger.warning(
                    f"Request blocked due to system status: "
                    f"{settings.system_status}"
                )
                
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "detail": "System is currently unavailable",
                        "status": settings.system_status,
                        "message": settings.maintenance_message,
                        "maintenance_start": (
                            settings.maintenance_start.isoformat() 
                            if settings.maintenance_start else None
                        ),
                        "maintenance_end": (
                            settings.maintenance_end.isoformat() 
                            if settings.maintenance_end else None
                        )
                    }
                )
    
    except Exception as e:
        logger.error(f"Settings middleware error: {e}")
        # On error, allow request through but log the issue
        # This prevents settings issues from bringing down the entire app
    
    # Process request normally
    return await call_next(request)


def get_system_status_for_config() -> str:
    """
    Get current system status for config/health checks.
    Uses cache if available, falls back to default.
    
    Returns:
        Current system status string
    """
    from app.core.settings_service import _settings_cache    
    if _settings_cache:
        return _settings_cache.system_status
    
    return SystemStatus.ACTIVE.value  # Default fallback