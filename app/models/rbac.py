"""
RBAC (Role-Based Access Control) models.

Defines Role, Permission, and their many-to-many association tables.
Roles are assigned to users; permissions are assigned to roles.

"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING, List, Optional

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_model import User


# ---------------------------------------------------------------------------
# Association tables
# NOTE: These use the SQLAlchemy Core Table() API intentionally — they are
# pure join tables with no ORM identity of their own. `assigned_at` is added
# for audit purposes (when was this role/permission granted?).
# ---------------------------------------------------------------------------

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "role_id",
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    # Audit: when was this role assigned to this user?
    Column(
        "assigned_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "permission_id",
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    # Audit: when was this permission granted to this role?
    Column(
        "assigned_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Role(Base):
    """
    Role model for RBAC system.

    A role represents a job function (e.g. "facility_manager", "nurse").
    Users are assigned one or more roles; roles grant permissions.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    # Human-readable description of what this role grants — required for
    # healthcare compliance (auditors need to understand what access exists).
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Many-to-many: role → permissions (selectin is fine; permission sets are small).
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )

    # Many-to-many: role → users.
    # PERFORMANCE: `noload` here — loading every user for a role is almost never
    # needed and would be catastrophic for high-volume roles (e.g. "nurse").
    # Query users for a role explicitly in your service layer when needed.
    users: Mapped[List["User"]] = relationship(
        "User",
        secondary=user_roles,
        back_populates="roles",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name}>"


class Permission(Base):
    """
    Permission model for RBAC system.

    A permission is a discrete action (e.g. "patient:create", "report:export").
    Follow the convention `resource:action` for names.
    """

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(96), unique=True, index=True, nullable=False)

    # Human-readable description of what this permission allows.
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # PERFORMANCE: `noload` — iterating all roles that have a permission is an
    # admin-only operation; don't pay for it on every permission load.
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Permission id={self.id} name={self.name}>"