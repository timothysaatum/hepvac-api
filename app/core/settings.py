from typing import Optional
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Boolean, Text, String, Integer, CheckConstraint, 
    ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db.base import Base


class NotificationTarget(str, Enum):
    """Notification target audience options"""
    ALL_PATIENTS = "all_patients"
    PREGNANT_ONLY = "pregnant_only"
    MOTHERS_ONLY = "mothers_only"
    REGULAR_ONLY = "regular_only"
    STAFF_ONLY = "staff_only"


class SystemStatus(str, Enum):
    """System operational status"""
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    SUSPENDED = "suspended"


class Setting(Base):
    """
    Global application settings - Singleton pattern.
    Only one row allowed in the entire table (id=1).
    """
    __tablename__ = "settings"

    # Singleton pattern - enforce single row
    id: Mapped[int] = mapped_column(
        Integer, 
        primary_key=True, 
        default=1,
        comment="Fixed ID=1 for singleton pattern"
    )
    
    # ==================== NOTIFICATION SETTINGS ====================
    notification_target: Mapped[str] = mapped_column(
        String(50),
        default=NotificationTarget.ALL_PATIENTS.value,
        nullable=False,
        index=True,
        comment="Target audience for notifications"
    )
    
    reminder_interval_days: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
        comment="Days between vaccination reminders (1-30)"
    )
    
    reminder_message: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Custom reminder message template"
    )
    
    # ==================== DASHBOARD SETTINGS ====================
    dashboard_refresh_rate_seconds: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
        comment="Auto-refresh interval in seconds (10-300)"
    )
    
    enable_dashboard_auto_refresh: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Enable/disable dashboard auto-refresh"
    )
    
    # ==================== SYSTEM STATUS ====================
    system_status: Mapped[str] = mapped_column(
        String(20),
        default=SystemStatus.ACTIVE.value,
        nullable=False,
        index=True,
        comment="Current system operational status"
    )
    
    maintenance_message: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Message displayed during maintenance"
    )
    
    maintenance_start: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Scheduled maintenance start time"
    )
    
    maintenance_end: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Scheduled maintenance end time"
    )
    
    # ==================== SECURITY SETTINGS ====================
    require_device_approval: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Require admin approval for new devices"
    )
    
    session_timeout_minutes: Mapped[int] = mapped_column(
        Integer,
        default=480,  # 8 hours
        nullable=False,
        comment="User session timeout in minutes (30-1440)"
    )
    
    max_login_attempts: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
        comment="Maximum failed login attempts before lockout (3-10)"
    )
    
    lockout_duration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
        comment="Account lockout duration in minutes (10-120)"
    )
    
    # ==================== AUDIT TRAIL ====================
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, 
        nullable=False,
        comment="Settings creation timestamp"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        index=True,
        comment="Last update timestamp"
    )
    
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who last updated settings"
    )
    
    # ==================== RELATIONSHIPS ====================
    updated_by = relationship(
        "User", 
        foreign_keys=[updated_by_id],
        lazy="joined"
    )
    
    # ==================== CONSTRAINTS ====================
    __table_args__ = (
        # Enforce singleton pattern
        CheckConstraint('id = 1', name='single_settings_row'),
        
        # Reminder interval validation
        CheckConstraint(
            'reminder_interval_days >= 1 AND reminder_interval_days <= 30',
            name='valid_reminder_interval'
        ),
        
        # Refresh rate validation
        CheckConstraint(
            'dashboard_refresh_rate_seconds >= 10 AND dashboard_refresh_rate_seconds <= 300',
            name='valid_refresh_rate'
        ),
        
        # Session timeout validation
        CheckConstraint(
            'session_timeout_minutes >= 30 AND session_timeout_minutes <= 1440',
            name='valid_session_timeout'
        ),
        
        # Login attempts validation
        CheckConstraint(
            'max_login_attempts >= 3 AND max_login_attempts <= 10',
            name='valid_max_login_attempts'
        ),
        
        # Lockout duration validation
        CheckConstraint(
            'lockout_duration_minutes >= 10 AND lockout_duration_minutes <= 120',
            name='valid_lockout_duration'
        ),
        
        # Indexes for performance
        Index('idx_settings_status', 'system_status'),
        Index('idx_settings_updated', 'updated_at'),
    )
    
    # ==================== VALIDATION ====================
    @validates('notification_target')
    def validate_notification_target(self, key, value):
        """Validate notification target is a valid enum value"""
        valid_values = [e.value for e in NotificationTarget]
        if value not in valid_values:
            raise ValueError(
                f"Invalid notification target: {value}. "
                f"Must be one of: {', '.join(valid_values)}"
            )
        return value
    
    @validates('system_status')
    def validate_system_status(self, key, value):
        """Validate system status is a valid enum value"""
        valid_values = [e.value for e in SystemStatus]
        if value not in valid_values:
            raise ValueError(
                f"Invalid system status: {value}. "
                f"Must be one of: {', '.join(valid_values)}"
            )
        return value
    
    @validates('reminder_interval_days')
    def validate_reminder_interval(self, key, value):
        """Validate reminder interval is within acceptable range"""
        if not 1 <= value <= 30:
            raise ValueError(
                "Reminder interval must be between 1 and 30 days"
            )
        return value
    
    @validates('dashboard_refresh_rate_seconds')
    def validate_refresh_rate(self, key, value):
        """Validate refresh rate is within acceptable range"""
        if not 10 <= value <= 300:
            raise ValueError(
                "Refresh rate must be between 10 and 300 seconds"
            )
        return value
    
    @validates('session_timeout_minutes')
    def validate_session_timeout(self, key, value):
        """Validate session timeout is within acceptable range"""
        if not 30 <= value <= 1440:
            raise ValueError(
                "Session timeout must be between 30 and 1440 minutes (24 hours)"
            )
        return value
    
    @validates('max_login_attempts')
    def validate_max_login_attempts(self, key, value):
        """Validate max login attempts is within acceptable range"""
        if not 3 <= value <= 10:
            raise ValueError(
                "Max login attempts must be between 3 and 10"
            )
        return value
    
    @validates('lockout_duration_minutes')
    def validate_lockout_duration(self, key, value):
        """Validate lockout duration is within acceptable range"""
        if not 10 <= value <= 120:
            raise ValueError(
                "Lockout duration must be between 10 and 120 minutes"
            )
        return value
    
    def __repr__(self) -> str:
        return (
            f"<Setting(id={self.id}, status={self.system_status}, "
            f"updated_at={self.updated_at})>"
        )