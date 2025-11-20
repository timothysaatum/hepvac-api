import uuid
from datetime import datetime
from typing import Optional
from enum import Enum
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    String,
    Text,
    Enum as SQLEnum,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db.base import Base
from app.models.user_model import User


class DeviceStatus(str, Enum):
    """Device trust status"""

    PENDING = "pending"  # Awaiting admin approval
    TRUSTED = "trusted"  # Approved and trusted
    BLOCKED = "blocked"  # Explicitly blocked
    SUSPICIOUS = "suspicious"  # Flagged for review


class TrustedDevice(Base):
    """
    Track trusted devices instead of IPs.
    More reliable than IP whitelisting.
    """

    __tablename__ = "trusted_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Device fingerprint (combination of browser, OS, screen resolution, etc.)
    device_fingerprint: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )

    # Device information
    device_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    browser: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    os: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # mobile, desktop, tablet

    # Last known IP (for reference, not for blocking)
    last_ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Trust status
    status: Mapped[DeviceStatus] = mapped_column(
        SQLEnum(DeviceStatus),
        default=DeviceStatus.PENDING,
        nullable=False,
        index=True,
    )

    # First and last seen
    first_seen: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    last_seen: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Approval tracking
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    approved_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Automatic trust expiry (optional)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="selectin")

    approved_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[approved_by_id], lazy="selectin"
    )

    def is_expired(self) -> bool:
        """Check if device trust has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def is_active(self) -> bool:
        """Check if device is actively trusted"""
        return self.status == DeviceStatus.TRUSTED and not self.is_expired()


class LoginAttempt(Base):
    """
    Track all login attempts for security monitoring.
    More useful than IP blocking for detecting attacks.
    """

    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    device_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Attempt details
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Location data (from IP geolocation)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Device info
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    attempted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


class GeographicRestriction(Base):
    """
    Optional: Restrict access based on country/region.
    More practical than individual IP whitelisting.
    """

    __tablename__ = "geographic_restrictions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Allowed countries (ISO country codes)
    allowed_countries: Mapped[list] = mapped_column(
        Text, nullable=False
    )  # JSON array: ["GH", "NG", "KE"]

    # Or blocked countries
    blocked_countries: Mapped[Optional[list]] = mapped_column(
        Text, nullable=True
    )  # JSON array

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
