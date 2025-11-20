from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List, TYPE_CHECKING
from app.db.base import Base
from sqlalchemy import TIMESTAMP, DateTime, Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import uuid
from app.models.rbac import Role, user_roles

if TYPE_CHECKING:
    from app.models.rbac import Permission
    from app.models.facility_model import Facility
    from app.models.patient_model import (
        Patient,
        Vaccination,
        Payment,
        Prescription,
    )


class User(Base):
    """User model for authentication and authorization."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    roles: Mapped[List[Role]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_suspended: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    max_login_attempts: Mapped[int] = mapped_column(
        default=5,
        nullable=False,
    )
    login_attempts: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    facility_id = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "facilities.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_user_facility_id",
        ),
        nullable=True,
    )

    # Relationships
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    user_sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    facility: Mapped[Optional["Facility"]] = relationship(
        "Facility",
        foreign_keys=[facility_id],
        back_populates="staff",
        lazy="selectin",
    )

    managed_facility: Mapped[Optional["Facility"]] = relationship(
        "Facility",
        foreign_keys="[Facility.facility_manager_id]",
        back_populates="facility_manager",
        uselist=False,
        lazy="selectin",
    )

    # Patient-related relationships
    created_patients: Mapped[List["Patient"]] = relationship(
        "Patient",
        foreign_keys="[Patient.created_by_id]",
        back_populates="created_by",
        overlaps="updated_patients",
    )

    updated_patients: Mapped[List["Patient"]] = relationship(
        "Patient",
        foreign_keys="[Patient.updated_by_id]",
        back_populates="updated_by",
        overlaps="created_patients",
    )

    administered_vaccinations: Mapped[List["Vaccination"]] = relationship(
        "Vaccination",
        foreign_keys="[Vaccination.administered_by_id]",
        back_populates="administered_by",
    )

    received_payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        foreign_keys="[Payment.received_by_id]",
        back_populates="received_by",
    )

    prescribed_prescriptions: Mapped[List["Prescription"]] = relationship(
        "Prescription",
        foreign_keys="[Prescription.prescribed_by_id]",
        back_populates="prescribed_by",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} username={self.username}>"

    def can_login(self) -> Tuple[bool, Optional[str]]:
        """Check if user is allowed to login."""
        if not self.is_active:
            return False, "User account is inactive"
        if self.is_suspended:
            return False, "User account is suspended"

        if not self.roles:
            return False, "User does not have any assigned role"

        return True, None

    def suspend_user(self) -> None:
        """Suspend user if max login attempts reached."""
        if self.login_attempts >= self.max_login_attempts:
            self.is_suspended = True

    def has_exhausted_max_login_attempts(self) -> bool:
        if self.login_attempts >= 5:
            return True
        return False

    def update_login_attempts(self) -> None:
        """Increment failed login attempts."""
        if not self.is_suspended and self.login_attempts < self.max_login_attempts:
            self.login_attempts += 1

    def reset_login_attempts(self) -> None:
        """Reset failed login attempts counter."""
        self.login_attempts = 0

    def activate_user(self) -> None:
        """Activate user account and reset login attempts."""
        self.is_active = True
        self.is_suspended = False
        self.reset_login_attempts()

    def deactivate_user(self) -> None:
        """Deactivate user account."""
        self.is_active = False

    def normalize_email(self) -> None:
        """Convert email to lowercase for consistency."""
        if self.email:
            self.email = self.email.lower()

    def format_phone(self) -> None:
        """Format phone number with proper prefix."""
        if not self.phone or not isinstance(self.phone, str):
            return

        if not self.phone.startswith("+"):
            self.phone = f"+{self.phone}"

        if self.phone.startswith("+0"):
            self.phone = self.phone.replace("+0", "+", 1)

        # Validate length
        digits = "".join(filter(str.isdigit, self.phone))
        if len(digits) > 15 or len(digits) < 10:
            raise ValueError("Phone number length is invalid.")

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return any(role.name == role_name for role in self.roles)

    def has_permission(self, permission_name: str) -> bool:
        """Check if user has a specific permission through any of their roles."""
        for role in self.roles:
            for permission in role.permissions:
                if permission.name == permission_name:
                    return True
        return False


class RefreshToken(Base):
    """Refresh token model for JWT authentication."""

    __tablename__ = "refresh_tokens"

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
    token: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
    )
    device_info: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    absolute_expiry: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=30),
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    usage_count: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id}>"

    def mark_as_used(self) -> None:
        """Mark token as used and update usage stats."""
        self.usage_count += 1
        self.last_used_at = datetime.now(timezone.utc)

    def revoke(self) -> None:
        """Revoke the refresh token."""
        self.is_revoked = True

    def mark_as_expired(self) -> None:
        """Mark token as expired if past absolute expiry."""
        if datetime.now(timezone.utc) >= self.absolute_expiry:
            self.is_revoked = True


class UserSession(Base):
    """User session model for tracking active sessions."""

    __tablename__ = "user_sessions"

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
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    user_agent_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    session_token: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
    )
    device_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    login_method: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_suspicious: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    is_terminated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_terminated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    termination_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    user: Mapped["User"] = relationship("User", back_populates="user_sessions")

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user_id={self.user_id}>"

    def terminate_session(self, reason: Optional[str] = None) -> None:
        """Terminate the session with optional reason."""
        self.is_terminated = True
        self.is_active = False
        self.is_expired = True
        if reason:
            self.termination_reason = reason

    def mark_suspicious(self) -> None:
        """Mark session as suspicious for security monitoring."""
        self.is_suspicious = True

    def refresh_last_active(self) -> None:
        """Update last active timestamp."""
        self.last_active_at = datetime.now(timezone.utc)

    def update_activity(self, current_ip: str) -> None:
        """Update session activity with current IP."""
        self.refresh_last_active()
        if self.ip_address != current_ip:
            self.ip_address = current_ip

    @property
    def is_valid(self) -> bool:
        """Check if session is valid"""
        return self.is_active and not self.is_expired and self.is_terminated_at is None
