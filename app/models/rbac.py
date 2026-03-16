"""
RBAC (Role-Based Access Control) models.

Defines Role, Permission, and their many-to-many association tables.
Roles are assigned to users; permissions are assigned to roles.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING, List, Optional

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_model import User


# ---------------------------------------------------------------------------
# Association tables
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
    Column(
        "assigned_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    # Lookup all roles for a user (most common RBAC query)
    Index("idx_user_roles_user_id", "user_id"),
    # Lookup all users with a given role (admin queries)
    Index("idx_user_roles_role_id", "role_id"),
    # Audit: when was a role assigned to a user
    Index("idx_user_roles_assigned_at", "assigned_at"),
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
    Column(
        "assigned_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
    # Lookup all permissions for a role (every auth check)
    Index("idx_role_permissions_role_id", "role_id"),
    # Lookup all roles that have a permission (admin queries)
    Index("idx_role_permissions_permission_id", "permission_id"),
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

    __table_args__ = (
        # Composite index for audit queries filtering by name + creation date
        Index("idx_roles_name_created_at", "name", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )

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

    __table_args__ = (
        # Composite index for filtering permissions by resource prefix
        # e.g. WHERE name LIKE 'patient:%'
        Index("idx_permissions_name_created_at", "name", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(96), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Permission id={self.id} name={self.name}>"