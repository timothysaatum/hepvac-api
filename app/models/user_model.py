"""
User, RefreshToken, and UserSession models.

Core authentication and session management for the application.

"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional, List, TYPE_CHECKING

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.models.rbac import Role, user_roles

if TYPE_CHECKING:
    from app.models.facility_model import Facility
    from app.models.patient_model import Patient, Vaccination, Payment, Prescription, Diagnosis, MedicationSchedule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class LoginCheckResult(NamedTuple):
    """Structured return type for User.can_login()."""
    allowed: bool
    reason: Optional[str]


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class User(Base):
    """
    User model for authentication and authorization.

    A user belongs to one facility and holds one or more roles. Login is
    guarded by active/suspended state and a configurable attempt ceiling.
    """

    __tablename__ = "users"

    # Application-level constant — not stored per-user to prevent privilege
    # escalation by setting a single user's limit to an arbitrarily high value.
    MAX_LOGIN_ATTEMPTS: int = 5

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
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
        TIMESTAMP(timezone=True),
        nullable=True,
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
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "facilities.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_user_facility_id",
        ),
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    roles: Mapped[List[Role]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    user_sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    facility: Mapped[Optional["Facility"]] = relationship(
        "Facility",
        foreign_keys=[facility_id],
        back_populates="staff",
        lazy="select",
    )
    managed_facility: Mapped[Optional["Facility"]] = relationship(
        "Facility",
        foreign_keys="[Facility.facility_manager_id]",
        back_populates="facility_manager",
        uselist=False,
        lazy="select",
    )

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
    # Diagnosis, Prescription, and MedicationSchedule.
    diagnoses_given: Mapped[List["Diagnosis"]] = relationship(
        "Diagnosis",
        foreign_keys="[Diagnosis.diagnosed_by_id]",
        back_populates="diagnosed_by",
    )
    updated_prescriptions: Mapped[List["Prescription"]] = relationship(
        "Prescription",
        foreign_keys="[Prescription.updated_by_id]",
        back_populates="updated_by",
    )
    updated_medication_schedules: Mapped[List["MedicationSchedule"]] = relationship(
        "MedicationSchedule",
        foreign_keys="[MedicationSchedule.updated_by_id]",
        back_populates="updated_by",
    )

    # -----------------------------------------------------------------------
    # Methods
    # -----------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} username={self.username}>"

    def can_login(self) -> LoginCheckResult:
        """
        Return whether this user is permitted to attempt login.

        Returns a LoginCheckResult(allowed, reason) NamedTuple.
        When allowed=False, reason contains a human-readable explanation.

        Order of checks is intentional:
            1. Deleted — hard stop; no further detail given to prevent enumeration.
            2. Active   — account may be deactivated without deletion.
            3. Suspended — temporary lock after failed attempts.
            4. Roles    — misconfigured accounts should not be granted access.
        """
        if self.is_deleted:
            return LoginCheckResult(False, "User account no longer exists.")
        if not self.is_active:
            return LoginCheckResult(False, "User account is inactive.")
        if self.is_suspended:
            return LoginCheckResult(False, "User account is suspended.")
        if not self.roles:
            return LoginCheckResult(False, "User does not have any assigned role.")
        return LoginCheckResult(True, None)

    def has_exhausted_max_login_attempts(self) -> bool:
        """Return True if the user has reached the login attempt ceiling."""
        return self.login_attempts >= self.MAX_LOGIN_ATTEMPTS

    def update_login_attempts(self) -> None:
        """
        Increment the failed login attempt counter if not yet suspended.

        .. warning:: RACE CONDITION — do not call this in high-concurrency paths.
            Two simultaneous failed logins can both read the same
            ``login_attempts`` value, both pass the ceiling check, and both
            write back the same incremented value (lost-update anomaly).

            Use an atomic SQL UPDATE in your auth service instead::

                from sqlalchemy import update
                await db.execute(
                    update(User)
                    .where(User.id == user_id, User.is_suspended.is_(False))
                    .values(login_attempts=User.login_attempts + 1)
                )
                await db.refresh(user, ["login_attempts", "is_suspended"])
                if user.login_attempts >= User.MAX_LOGIN_ATTEMPTS:
                    user.suspend_user()

            This method is retained for use in single-connection contexts
            (tests, scripts) where concurrency is not a concern.
        """
        if not self.is_suspended and not self.has_exhausted_max_login_attempts():
            self.login_attempts += 1

    def suspend_user(self) -> None:
        """Suspend the user if they have reached the max login attempt ceiling."""
        if self.has_exhausted_max_login_attempts():
            self.is_suspended = True

    def reset_login_attempts(self) -> None:
        """Reset the failed login attempt counter to zero."""
        self.login_attempts = 0

    def activate_user(self) -> None:
        """Activate the account and lift any suspension."""
        self.is_active = True
        self.is_suspended = False
        self.reset_login_attempts()

    def deactivate_user(self) -> None:
        """Deactivate the user account."""
        self.is_active = False

    @validates("email")
    def validate_email(self, key: str, value: Optional[str]) -> Optional[str]:
        """
        Normalise email to lowercase and strip whitespace on every assignment.

        Replaces the old `normalize_email()` manual method.  SQLAlchemy calls
        this validator whenever `user.email = ...` is executed.
        """
        if value is None:
            return value
        return value.strip().lower()

    @validates("phone")
    def validate_phone(self, key: str, value: Optional[str]) -> Optional[str]:
        """
        Normalise phone to E.164 format (+<digits>) on every assignment.

        Replaces the old `format_phone()` manual method.  Raises ValueError
        for numbers outside the 10–15 digit range.

        Passing None or an empty string is accepted (phone is nullable).
        """
        if not value or not isinstance(value, str):
            return value

        digits = re.sub(r"\D", "", value)

        if not (10 <= len(digits) <= 15):
            raise ValueError(
                f"Phone number must be 10–15 digits; got {len(digits)}."
            )

        return f"+{digits}"

    def normalize_email(self) -> None:
        """
        Normalise email to lowercase.

        .. deprecated::
            Assign to ``user.email`` directly — the ``@validates("email")``
            decorator now handles normalisation automatically.  This method
            is kept for backwards compatibility and will be removed in a
            future release.
        """
        if self.email:
            self.email = self.email.strip().lower()

    def format_phone(self) -> None:
        """
        Normalise phone to E.164 format.

        .. deprecated::
            Assign to ``user.phone`` directly — the ``@validates("phone")``
            decorator now handles normalisation automatically.  This method
            is kept for backwards compatibility and will be removed in a
            future release.
        """
        if not self.phone or not isinstance(self.phone, str):
            return

        digits = re.sub(r"\D", "", self.phone)

        if not (10 <= len(digits) <= 15):
            raise ValueError(
                f"Phone number must be 10–15 digits; got {len(digits)}."
            )

        self.phone = f"+{digits}"

    def has_role(self, role_name: str) -> bool:
        """Return True if the user holds the named role."""
        return any(role.name == role_name for role in self.roles)

    def has_permission(self, permission_name: str) -> bool:
        """Return True if any of the user's roles grants the named permission."""
        return any(
            permission.name == permission_name
            for role in self.roles
            for permission in role.permissions
        )


# ---------------------------------------------------------------------------
# RefreshToken
# ---------------------------------------------------------------------------


class RefreshToken(Base):
    """
    Refresh token for JWT authentication.

    Tokens have a sliding expiry (expires_at) and an absolute expiry
    (absolute_expiry) so they cannot be refreshed indefinitely.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
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
    # String(45) is correct — covers IPv4 (15) and full IPv6 (39) with room.
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
        """Increment usage counter and record last-used timestamp."""
        self.usage_count += 1
        self.last_used_at = datetime.now(timezone.utc)

    def revoke(self) -> None:
        """Permanently revoke this token."""
        self.is_revoked = True

    def mark_as_expired(self) -> None:
        """Revoke the token if it has passed its absolute expiry."""
        if datetime.now(timezone.utc) >= self.absolute_expiry:
            self.is_revoked = True


# ---------------------------------------------------------------------------
# UserSession
# ---------------------------------------------------------------------------


class UserSession(Base):
    """
    Active session record for a logged-in user.

    Tracks device, IP, and session state. Sessions can be terminated
    explicitly or expire naturally via `expires_at`.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
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
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_expired: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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
    terminated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    termination_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    user: Mapped["User"] = relationship("User", back_populates="user_sessions")

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user_id={self.user_id}>"

    def terminate_session(self, reason: Optional[str] = None) -> None:
        """
        Terminate this session.

        Sets `is_terminated=True` as the single authoritative flag.
        `is_active` and `is_expired` are also updated for query compatibility.
        """
        now = datetime.now(timezone.utc)
        self.is_terminated = True
        self.is_active = False
        self.is_expired = True
        self.terminated_at = now
        if reason:
            self.termination_reason = reason

    def mark_suspicious(self) -> None:
        """Flag this session for security review."""
        self.is_suspicious = True

    def refresh_last_active(self) -> None:
        """Update last-active timestamp to now."""
        self.last_active_at = datetime.now(timezone.utc)

    def update_activity(self, current_ip: str) -> None:
        """Record current activity and update IP if it has changed."""
        self.refresh_last_active()
        if self.ip_address != current_ip:
            self.ip_address = current_ip

    @property
    def is_valid(self) -> bool:
        """
        Return True if this session is currently valid.

        Checks the real ``expires_at`` timestamp rather than the stored
        ``is_expired`` boolean flag. The flag can be stale if the background
        cleanup job has not yet run; the timestamp is always authoritative.

        ``is_expired`` is retained as a queryable/filterable column but must
        never be used as the single source of truth in application logic.

        Uses ``.astimezone()`` (not ``.replace()``) so an already-timezone-aware
        ``expires_at`` from Postgres is correctly converted rather than having
        its tzinfo silently overwritten.
        """
        return (
            self.is_active
            and not self.is_terminated
            and datetime.now(timezone.utc) < self.expires_at.astimezone(timezone.utc)
        )