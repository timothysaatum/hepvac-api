from sqlalchemy import Column, Integer, String, Table, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.base import Base
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from typing import TYPE_CHECKING, List

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from app.models.user_model import User

# Association table for users <-> roles
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)

# Association table for roles <-> permissions
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)


class Role(Base):
    """Role model for RBAC system."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Many-to-many relationship with permissions
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )

    # Many-to-many relationship with users
    users: Mapped[List["User"]] = relationship(
        "User", secondary=user_roles, back_populates="roles", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name}>"


class Permission(Base):
    """Permission model for RBAC system."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(96), unique=True, index=True)

    # Many-to-many relationship with roles
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Permission id={self.id} name={self.name}>"
