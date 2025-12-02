from typing import Optional
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from functools import lru_cache
from app.core.settings import NotificationTarget, Setting, SystemStatus
from fastapi import HTTPException, status
import logging

from app.core.settings_schemas import SettingUpdate

logger = logging.getLogger(__name__)

# In-memory cache for settings (refreshed periodically)
_settings_cache: Optional[Setting] = None
_cache_timestamp: Optional[datetime] = None
CACHE_TTL_SECONDS = 60  # Cache for 60 seconds


class SettingsService:
    """
    Service layer for managing application settings.
    Implements caching for performance and singleton pattern for data integrity.
    """
    
    @staticmethod
    async def get_settings(
        db: AsyncSession, 
        use_cache: bool = True
    ) -> Setting:
        """
        Get application settings. Uses cache by default for performance.
        
        Args:
            db: Database session
            use_cache: Whether to use cached settings (default True)
            
        Returns:
            Setting object
            
        Raises:
            HTTPException: If settings don't exist and can't be created
        """
        global _settings_cache, _cache_timestamp
        
        # Check cache first
        if use_cache and _settings_cache and _cache_timestamp:
            cache_age = (datetime.utcnow() - _cache_timestamp).total_seconds()
            if cache_age < CACHE_TTL_SECONDS:
                logger.debug("Returning cached settings")
                return _settings_cache
        
        # Fetch from database
        logger.debug("Fetching settings from database")
        result = await db.execute(
            select(Setting).where(Setting.id == 1)
        )
        settings = result.scalar_one_or_none()
        
        if not settings:
            # Auto-create default settings if none exist
            logger.warning("No settings found, creating default settings")
            settings = await SettingsService.create_default_settings(db)
        
        # Update cache
        _settings_cache = settings
        _cache_timestamp = datetime.utcnow()
        
        return settings
    
    @staticmethod
    async def create_default_settings(db: AsyncSession) -> Setting:
        """
        Create default settings (used on first startup).
        
        Args:
            db: Database session
            
        Returns:
            Created Setting object
        """
        settings = Setting(
            id=1,  # Singleton ID
            notification_target=NotificationTarget.ALL_PATIENTS.value,
            reminder_interval_days=3,
            reminder_message=None,
            dashboard_refresh_rate_seconds=30,
            enable_dashboard_auto_refresh=True,
            system_status=SystemStatus.ACTIVE.value,
            maintenance_message=None,
            maintenance_start=None,
            maintenance_end=None,
            require_device_approval=True,
            session_timeout_minutes=480,
            max_login_attempts=5,
            lockout_duration_minutes=30,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            updated_by_id=None
        )
        
        try:
            db.add(settings)
            await db.commit()
            await db.refresh(settings)
            logger.info("Default settings created successfully")
            return settings
        except IntegrityError as e:
            await db.rollback()
            logger.error(f"Failed to create default settings: {e}")
            # If creation failed, try to fetch again (race condition)
            result = await db.execute(
                select(Setting).where(Setting.id == 1)
            )
            settings = result.scalar_one_or_none()
            if not settings:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create or retrieve settings"
                )
            return settings
    
    @staticmethod
    async def update_settings(
        db: AsyncSession,
        settings_update: SettingUpdate,
        user_id: uuid.UUID
    ) -> Setting:
        """
        Update application settings.
        
        Args:
            db: Database session
            settings_update: Settings update data
            user_id: ID of user making the update
            
        Returns:
            Updated Setting object
            
        Raises:
            HTTPException: If settings don't exist or update fails
        """
        # Get current settings (bypass cache for updates)
        settings = await SettingsService.get_settings(db, use_cache=False)
        
        # Update only provided fields
        update_data = settings_update.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(settings, field, value)
        
        # Update audit fields
        settings.updated_at = datetime.utcnow()
        settings.updated_by_id = user_id
        
        try:
            await db.commit()
            await db.refresh(settings)
            
            # Invalidate cache
            SettingsService.invalidate_cache()
            
            logger.info(
                f"Settings updated by user {user_id}. "
                f"Fields: {', '.join(update_data.keys())}"
            )
            
            return settings
        except IntegrityError as e:
            await db.rollback()
            logger.error(f"Failed to update settings: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid settings data"
            )
    
    @staticmethod
    async def set_system_status(
        db: AsyncSession,
        status: SystemStatus,
        user_id: uuid.UUID,
        message: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Setting:
        """
        Set system status (active/maintenance/suspended).
        
        Args:
            db: Database session
            status: New system status
            user_id: ID of user making the change
            message: Optional status message
            start_time: Optional maintenance start time
            end_time: Optional maintenance end time
            
        Returns:
            Updated Setting object
        """
        settings = await SettingsService.get_settings(db, use_cache=False)
        
        settings.system_status = status.value
        settings.maintenance_message = message
        settings.maintenance_start = start_time
        settings.maintenance_end = end_time
        settings.updated_at = datetime.utcnow()
        settings.updated_by_id = user_id
        
        await db.commit()
        await db.refresh(settings)
        
        # Invalidate cache
        SettingsService.invalidate_cache()
        
        logger.warning(
            f"System status changed to {status.value} by user {user_id}"
        )
        
        return settings
    
    @staticmethod
    def invalidate_cache():
        """Invalidate the settings cache"""
        global _settings_cache, _cache_timestamp
        _settings_cache = None
        _cache_timestamp = None
        logger.debug("Settings cache invalidated")
    
    @staticmethod
    async def get_public_settings(db: AsyncSession) -> dict:
        """
        Get public-facing settings (safe to expose to frontend).
        
        Args:
            db: Database session
            
        Returns:
            Dictionary of public settings
        """
        settings = await SettingsService.get_settings(db)
        
        return {
            "system_status": settings.system_status,
            "maintenance_message": settings.maintenance_message,
            "maintenance_start": settings.maintenance_start,
            "maintenance_end": settings.maintenance_end,
            "dashboard_refresh_rate_seconds": settings.dashboard_refresh_rate_seconds,
            "enable_dashboard_auto_refresh": settings.enable_dashboard_auto_refresh,
        }
    
    @staticmethod
    async def is_system_accessible(db: AsyncSession) -> bool:
        """
        Check if system is accessible (not in maintenance or suspended).
        
        Args:
            db: Database session
            
        Returns:
            True if system is accessible, False otherwise
        """
        settings = await SettingsService.get_settings(db)
        return settings.system_status == SystemStatus.ACTIVE.value