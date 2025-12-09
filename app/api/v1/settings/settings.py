from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from app.core.permission_checker import require_admin
from app.core.security import get_current_user
from app.core.settings import SystemStatus
from app.core.settings_schemas import SettingPublic, SettingResponse, SettingUpdate, SystemStatusUpdate
from app.core.settings_service import SettingsService, _settings_cache
from app.api.dependencies import get_db
import logging
from app.core.cache import cached


from app.models.user_model import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


@cached(ttl=300, key_prefix="settings")
@router.get("/public", response_model=SettingPublic)
async def get_public_settings(
        db: AsyncSession = Depends(get_db)
    ):
    """
    Get public settings (no authentication required).
    Used by login page and public-facing components.
    
    **Returns:**
    - System status
    - Maintenance information
    - Dashboard refresh settings
    """
    try:
        settings_dict = await SettingsService.get_public_settings(db)
        return settings_dict
    except Exception as e:
        logger.error(f"Error fetching public settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system settings"
        )


@cached(ttl=300, key_prefix="settings")
@router.get("", response_model=SettingResponse)
async def get_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """
    Get all application settings (authenticated users only).
    
    **Permissions:** Any authenticated user
    
    **Returns:** Complete settings object
    """
    try:
        settings = await SettingsService.get_settings(db)
        return settings
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings"
        )


@router.patch("", response_model=SettingResponse)
async def update_settings(
    settings_update: SettingUpdate,
    current_user: Annotated[User, Depends(require_admin())],
    db: AsyncSession = Depends(get_db)
):
    """
    Update application settings.
    
    **Permissions:** Admin only
    
    **Args:**
    - **settings_update**: Settings fields to update (all optional)
    
    **Returns:** Updated settings object
    
    **Notes:**
    - Only provided fields will be updated
    - All changes are logged with user ID
    - Cache is automatically invalidated
    """
    print(f"current_user: {current_user.id}")
    try:
        settings = await SettingsService.update_settings(
            db=db,
            settings_update=settings_update,
            user_id=current_user.id
        )
        
        logger.info(
            f"Settings updated by {current_user.username} "
            f"(ID: {current_user.id})"
        )
        
        return settings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings"
        )


@router.post("/system-status", response_model=SettingResponse)
async def set_system_status(
    status_update: SystemStatusUpdate,
    current_user: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_db)
):
    """
    Update system status (active/maintenance/suspended).
    
    **Permissions:** Admin only
    
    **Args:**
    - **status**: New system status
    - **message**: Optional status message
    - **start_time**: Optional maintenance start time
    - **end_time**: Optional maintenance end time
    
    **Returns:** Updated settings object
    
    **Use Cases:**
    - Set system to maintenance mode before updates
    - Suspend system access during incidents
    - Return system to active status
    """
    try:
        system_status = SystemStatus(status_update.status)
        
        settings = await SettingsService.set_system_status(
            db=db,
            status=system_status,
            user_id=current_user.id,
            message=status_update.message,
            start_time=status_update.start_time,
            end_time=status_update.end_time
        )
        
        logger.warning(
            f"System status changed to {status_update.status} "
            f"by {current_user.username} (ID: {current_user.id})"
        )
        
        return settings
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating system status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update system status"
        )


@router.post("/invalidate-cache")
async def invalidate_settings_cache(
    current_user: Annotated[User, Depends(require_admin)],
):
    """
    Manually invalidate settings cache.
    
    **Permissions:** Admin only
    
    **Returns:** Success message
    
    **Use Case:** Force cache refresh if settings appear stale
    """
    try:
        SettingsService.invalidate_cache()
        logger.info(
            f"Settings cache invalidated by {current_user.username} "
            f"(ID: {current_user.id})"
        )
        return {"message": "Settings cache invalidated successfully"}
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to invalidate cache"
        )


@router.get("/health")
async def settings_health_check(db: AsyncSession = Depends(get_db)):
    """
    Check if settings system is healthy.
    
    **Returns:**
    - Settings exist: Yes/No
    - System accessible: Yes/No
    - Cache status: Active/Inactive
    """
    try:
        settings = await SettingsService.get_settings(db)
        is_accessible = await SettingsService.is_system_accessible(db)
        
        return {
            "settings_exist": True,
            "system_accessible": is_accessible,
            "system_status": settings.system_status,
            "cache_active": _settings_cache is not None
        }
    except Exception as e:
        logger.error(f"Settings health check failed: {e}")
        return {
            "settings_exist": False,
            "system_accessible": False,
            "error": str(e)
        }