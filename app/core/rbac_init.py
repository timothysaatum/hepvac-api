"""
RBAC Initialization Utility

This module provides functions to initialize roles and permissions in the database.
It ensures default roles and permissions exist on application startup.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.rbac import Role, Permission
from app.core.utils import logger
from typing import Dict, List


# Define default permissions by category
DEFAULT_PERMISSIONS = {
    # User Management
    "user.create": "Create new users",
    "user.read": "View user information",
    "user.update": "Update user information",
    "user.delete": "Delete users",
    "user.list": "List all users",
    # Role Management
    "role.create": "Create new roles",
    "role.read": "View role information",
    "role.update": "Update role information",
    "role.delete": "Delete roles",
    "role.assign": "Assign roles to users",
    # Permission Management
    "permission.create": "Create new permissions",
    "permission.read": "View permission information",
    "permission.update": "Update permission information",
    "permission.delete": "Delete permissions",
    # System Management
    "system.settings": "Manage system settings",
    "system.logs": "View system logs",
    "system.backup": "Create system backups",
    "system.restore": "Restore system from backup",
    # Session Management
    "session.view_all": "View all user sessions",
    "session.terminate": "Terminate user sessions",
    # Audit
    "audit.view": "View audit logs",
    "audit.export": "Export audit logs",
}


# Define default roles with their permissions
DEFAULT_ROLES = {
    "superadmin": {
        "description": "Super Administrator with full system access",
        "permissions": [
            # Full access to everything
            "user.create",
            "user.read",
            "user.update",
            "user.delete",
            "user.list",
            "role.create",
            "role.read",
            "role.update",
            "role.delete",
            "role.assign",
            "permission.create",
            "permission.read",
            "permission.update",
            "permission.delete",
            "system.settings",
            "system.logs",
            "system.backup",
            "system.restore",
            "session.view_all",
            "session.terminate",
            "audit.view",
            "audit.export",
        ],
    },
    "admin": {
        "description": "Administrator with user and role management access",
        "permissions": [
            # User management
            "user.create",
            "user.read",
            "user.update",
            "user.list",
            # Role management (limited)
            "role.read",
            "role.assign",
            # Session management
            "session.view_all",
            "session.terminate",
            # Audit
            "audit.view",
        ],
    },
    "staff": {
        "description": "Staff member with basic access",
        "permissions": [
            # Basic user operations
            "user.read",
            "user.list",
            # View roles
            "role.read",
        ],
    },
}


async def create_permission(
    db: AsyncSession, name: str, description: str = None
) -> Permission:
    """
    Create a permission if it doesn't exist.

    Args:
        db: Database session
        name: Permission name
        description: Permission description (optional)

    Returns:
        Permission: Created or existing permission
    """
    # Check if permission already exists
    result = await db.execute(select(Permission).where(Permission.name == name))
    existing_permission = result.scalar_one_or_none()

    if existing_permission:
        return existing_permission

    # Create new permission
    try:
        permission = Permission(name=name)
        db.add(permission)
        await db.commit()
        await db.refresh(permission)

        logger.log_info(
            {
                "event_type": "permission_created",
                "permission_name": name,
                "description": description,
            }
        )

        return permission
    except IntegrityError:
        await db.rollback()
        # If constraint error, fetch the existing one
        result = await db.execute(select(Permission).where(Permission.name == name))
        return result.scalar_one()


async def create_role(
    db: AsyncSession, name: str, permissions: List[str] = None
) -> Role:
    """
    Create a role if it doesn't exist and assign permissions.

    Args:
        db: Database session
        name: Role name
        permissions: List of permission names to assign

    Returns:
        Role: Created or existing role with permissions
    """
    # Check if role already exists
    result = await db.execute(select(Role).where(Role.name == name))
    existing_role = result.scalar_one_or_none()

    if existing_role:
        role = existing_role
    else:
        # Create new role
        try:
            role = Role(name=name)
            db.add(role)
            await db.commit()
            await db.refresh(role)

            logger.log_info({"event_type": "role_created", "role_name": name})
        except IntegrityError:
            await db.rollback()
            # If constraint error, fetch the existing one
            result = await db.execute(select(Role).where(Role.name == name))
            role = result.scalar_one()

    # Assign permissions if provided
    if permissions:
        for perm_name in permissions:
            # Get permission
            result = await db.execute(
                select(Permission).where(Permission.name == perm_name)
            )
            permission = result.scalar_one_or_none()

            if permission and permission not in role.permissions:
                role.permissions.append(permission)

        await db.commit()
        await db.refresh(role)

    return role


async def initialize_permissions(db: AsyncSession) -> Dict[str, Permission]:
    """
    Initialize all default permissions.

    Args:
        db: Database session

    Returns:
        Dict mapping permission names to Permission objects
    """
    permissions = {}

    logger.log_info(
        {
            "event_type": "permissions_initialization_started",
            "total_permissions": len(DEFAULT_PERMISSIONS),
        }
    )

    for perm_name, description in DEFAULT_PERMISSIONS.items():
        permission = await create_permission(db, perm_name, description)
        permissions[perm_name] = permission

    logger.log_info(
        {
            "event_type": "permissions_initialization_completed",
            "total_permissions": len(permissions),
        }
    )

    return permissions


async def initialize_roles(db: AsyncSession) -> Dict[str, Role]:
    """
    Initialize all default roles with their permissions.

    Args:
        db: Database session

    Returns:
        Dict mapping role names to Role objects
    """
    roles = {}

    logger.log_info(
        {
            "event_type": "roles_initialization_started",
            "total_roles": len(DEFAULT_ROLES),
        }
    )

    for role_name, role_config in DEFAULT_ROLES.items():
        role = await create_role(
            db, name=role_name, permissions=role_config["permissions"]
        )
        roles[role_name] = role

        logger.log_info(
            {
                "event_type": "role_initialized",
                "role_name": role_name,
                "permissions_count": len(role.permissions),
            }
        )

    logger.log_info(
        {"event_type": "roles_initialization_completed", "total_roles": len(roles)}
    )

    return roles


async def initialize_rbac(db: AsyncSession) -> None:
    """
    Initialize RBAC system with default roles and permissions.

    This function should be called on application startup to ensure
    all default roles and permissions exist in the database.

    Args:
        db: Database session
    """
    try:
        logger.log_info({"event_type": "rbac_initialization_started"})

        # First, create all permissions
        await initialize_permissions(db)

        # Then, create roles and assign permissions
        await initialize_roles(db)

        logger.log_info(
            {"event_type": "rbac_initialization_completed", "status": "success"}
        )

    except Exception as e:
        logger.log_error(
            {
                "event_type": "rbac_initialization_failed",
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise


async def add_custom_permission(
    db: AsyncSession, name: str, description: str = None
) -> Permission:
    """
    Add a custom permission to the system.

    Args:
        db: Database session
        name: Permission name (use dot notation, e.g., "resource.action")
        description: Permission description

    Returns:
        Permission: Created permission

    Example:
        >>> await add_custom_permission(db, "report.generate", "Generate reports")
    """
    return await create_permission(db, name, description)


async def add_custom_role(db: AsyncSession, name: str, permissions: List[str]) -> Role:
    """
    Add a custom role to the system.

    Args:
        db: Database session
        name: Role name
        permissions: List of permission names to assign

    Returns:
        Role: Created role with assigned permissions

    Example:
        >>> await add_custom_role(db, "moderator", ["user.read", "user.update"])
    """
    return await create_role(db, name, permissions)
