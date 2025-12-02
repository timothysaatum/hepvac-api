from typing import Optional
from datetime import datetime
import uuid
from pydantic import BaseModel, Field, field_validator

from app.core.settings import NotificationTarget, SystemStatus


class SettingBase(BaseModel):
    """Base schema for settings"""
    notification_target: Optional[str] = Field(
        None, 
        description="Target audience for notifications"
    )
    reminder_interval_days: Optional[int] = Field(
        None, 
        ge=1, 
        le=30,
        description="Days between vaccination reminders (1-30)"
    )
    reminder_message: Optional[str] = Field(
        None,
        max_length=1000,
        description="Custom reminder message template"
    )
    dashboard_refresh_rate_seconds: Optional[int] = Field(
        None,
        ge=10,
        le=300,
        description="Dashboard auto-refresh interval in seconds (10-300)"
    )
    enable_dashboard_auto_refresh: Optional[bool] = Field(
        None,
        description="Enable/disable dashboard auto-refresh"
    )
    system_status: Optional[str] = Field(
        None,
        description="System operational status"
    )
    maintenance_message: Optional[str] = Field(
        None,
        max_length=500,
        description="Message displayed during maintenance"
    )
    maintenance_start: Optional[datetime] = Field(
        None,
        description="Scheduled maintenance start time"
    )
    maintenance_end: Optional[datetime] = Field(
        None,
        description="Scheduled maintenance end time"
    )
    require_device_approval: Optional[bool] = Field(
        None,
        description="Require admin approval for new devices"
    )
    session_timeout_minutes: Optional[int] = Field(
        None,
        ge=30,
        le=1440,
        description="User session timeout in minutes (30-1440)"
    )
    max_login_attempts: Optional[int] = Field(
        None,
        ge=3,
        le=10,
        description="Maximum failed login attempts before lockout (3-10)"
    )
    lockout_duration_minutes: Optional[int] = Field(
        None,
        ge=10,
        le=120,
        description="Account lockout duration in minutes (10-120)"
    )
    
    @field_validator('notification_target')
    @classmethod
    def validate_notification_target(cls, v):
        if v is not None:
            valid_values = [e.value for e in NotificationTarget]
            if v not in valid_values:
                raise ValueError(
                    f"Must be one of: {', '.join(valid_values)}"
                )
        return v
    
    @field_validator('system_status')
    @classmethod
    def validate_system_status(cls, v):
        if v is not None:
            valid_values = [e.value for e in SystemStatus]
            if v not in valid_values:
                raise ValueError(
                    f"Must be one of: {', '.join(valid_values)}"
                )
        return v
    
    @field_validator('maintenance_end')
    @classmethod
    def validate_maintenance_end(cls, v, info):
        if v is not None and info.data.get('maintenance_start'):
            if v <= info.data['maintenance_start']:
                raise ValueError(
                    "Maintenance end time must be after start time"
                )
        return v


class SettingCreate(SettingBase):
    """Schema for creating settings (not typically used - auto-created)"""
    pass


class SettingUpdate(SettingBase):
    """Schema for updating settings - all fields optional"""
    pass


class SettingResponse(SettingBase):
    """Schema for settings response"""
    id: int
    created_at: datetime
    updated_at: datetime
    updated_by_id: Optional[uuid.UUID] = None
    
    # Include all fields with their current values
    notification_target: str
    reminder_interval_days: int
    dashboard_refresh_rate_seconds: int
    enable_dashboard_auto_refresh: bool
    system_status: str
    require_device_approval: bool
    session_timeout_minutes: int
    max_login_attempts: int
    lockout_duration_minutes: int
    
    class Config:
        from_attributes = True


class SettingPublic(BaseModel):
    """Public settings safe to expose to frontend"""
    system_status: str
    maintenance_message: Optional[str] = None
    maintenance_start: Optional[datetime] = None
    maintenance_end: Optional[datetime] = None
    dashboard_refresh_rate_seconds: int
    enable_dashboard_auto_refresh: bool
    
    class Config:
        from_attributes = True


class SystemStatusUpdate(BaseModel):
    """Schema for updating system status"""
    status: str = Field(description="New system status")
    message: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional status message"
    )
    start_time: Optional[datetime] = Field(
        None,
        description="Optional maintenance start time"
    )
    end_time: Optional[datetime] = Field(
        None,
        description="Optional maintenance end time"
    )
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        valid_values = [e.value for e in SystemStatus]
        if v not in valid_values:
            raise ValueError(
                f"Must be one of: {', '.join(valid_values)}"
            )
        return v
    
    @field_validator('end_time')
    @classmethod
    def validate_end_time(cls, v, info):
        if v is not None and info.data.get('start_time'):
            if v <= info.data['start_time']:
                raise ValueError(
                    "End time must be after start time"
                )
        return v