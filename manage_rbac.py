#!/usr/bin/env python
"""
RBAC Management CLI

Command-line tool for managing roles and permissions.

Usage:
    python manage_rbac.py init                          # Initialize default roles/permissions
    python manage_rbac.py list-roles                    # List all roles
    python manage_rbac.py list-permissions              # List all permissions
    python manage_rbac.py show-role <role_name>         # Show role details
    python manage_rbac.py add-permission <name> [desc]  # Add custom permission
    python manage_rbac.py add-role <name> <perms>       # Add custom role
    python manage_rbac.py assign-role <username> <role> # Assign role to user
"""
import asyncio
import sys
from typing import Optional

from sqlalchemy import select

from app.core.rbac_init import (
    DEFAULT_PERMISSIONS, 
    DEFAULT_ROLES, 
    add_custom_permission, 
    add_custom_role, initialize_rbac
)
from app.db.session import AsyncSessionLocal as async_session_maker
from app.models.rbac import Role, Permission
from app.repositories.user_repo import UserRepository


async def initialize_system():
    """Initialize RBAC system with default roles and permissions."""
    async with async_session_maker() as db:
        await initialize_rbac(db)
        print("RBAC system initialized successfully!")


async def list_roles():
    """List all roles with their permissions."""
    async with async_session_maker() as db:
        result = await db.execute(select(Role))
        roles = result.scalars().all()

        if not roles:
            print("No roles found.")
            return

        print(f"\n{'Role':<20} {'Permissions':<50}")
        print("-" * 70)

        for role in roles:
            perms = ", ".join([p.name for p in role.permissions])
            print(f"{role.name:<20} {perms:<50}")


async def list_permissions():
    """List all permissions."""
    async with async_session_maker() as db:
        result = await db.execute(select(Permission))
        permissions = result.scalars().all()

        if not permissions:
            print("No permissions found.")
            return

        print(f"\n{'Permission':<40} {'Used in Roles':<30}")
        print("-" * 70)

        for perm in permissions:
            roles = ", ".join([r.name for r in perm.roles])
            print(f"{perm.name:<40} {roles:<30}")


async def show_role(role_name: str):
    """Show detailed information about a role."""
    async with async_session_maker() as db:
        result = await db.execute(select(Role).where(Role.name == role_name))
        role = result.scalar_one_or_none()

        if not role:
            print(f"Role '{role_name}' not found.")
            return

        print(f"\n📋 Role: {role.name}")
        print(f"   ID: {role.id}")

        if role_name in DEFAULT_ROLES:
            print(f"   Description: {DEFAULT_ROLES[role_name]['description']}")

        print(f"\n   Permissions ({len(role.permissions)}):")
        for perm in sorted(role.permissions, key=lambda p: p.name):
            desc = DEFAULT_PERMISSIONS.get(perm.name, "")
            print(f"• {perm.name:<40} {desc}")


async def add_permission(name: str, description: Optional[str] = None):
    """Add a custom permission."""
    async with async_session_maker() as db:
        try:
            permission = await add_custom_permission(db, name, description)
            print(f"Permission '{permission.name}' created successfully!")
        except Exception as e:
            print(f"Error creating permission: {str(e)}")


async def add_role_cli(name: str, permissions: str):
    """Add a custom role with permissions."""
    async with async_session_maker() as db:
        try:
            perm_list = [p.strip() for p in permissions.split(",")]
            role = await add_custom_role(db, name, perm_list)
            print(
                f"Role '{role.name}' created with {len(role.permissions)} permissions!"
            )
        except Exception as e:
            print(f"Error creating role: {str(e)}")


async def assign_role_to_user(username: str, role_name: str):
    """Assign a role to a user."""
    async with async_session_maker() as db:
        try:
            user_repo = UserRepository(db)

            # Get user
            user = await user_repo.get_user_by_username(username)
            if not user:
                print(f"User '{username}' not found.")
                return

            # Assign role
            await user_repo.assign_role_to_user(user, role_name)
            print(f"Role '{role_name}' assigned to user '{username}'!")

        except ValueError as e:
            print(f"{str(e)}")
        except Exception as e:
            print(f"Error assigning role: {str(e)}")


def print_usage():
    """Print usage information."""
    print(__doc__)


async def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1].lower()

    if command == "init":
        await initialize_system()

    elif command == "list-roles":
        await list_roles()

    elif command == "list-permissions":
        await list_permissions()

    elif command == "show-role":
        if len(sys.argv) < 3:
            print("Error: Role name required")
            print("Usage: python manage_rbac.py show-role <role_name>")
            return
        await show_role(sys.argv[2])

    elif command == "add-permission":
        if len(sys.argv) < 3:
            print("Error: Permission name required")
            print("Usage: python manage_rbac.py add-permission <name> [description]")
            return
        name = sys.argv[2]
        description = sys.argv[3] if len(sys.argv) > 3 else None
        await add_permission(name, description)

    elif command == "add-role":
        if len(sys.argv) < 4:
            print("Error: Role name and permissions required")
            print("Usage: python manage_rbac.py add-role <name> <perm1,perm2,perm3>")
            return
        await add_role_cli(sys.argv[2], sys.argv[3])

    elif command == "assign-role":
        if len(sys.argv) < 4:
            print("Error: Username and role name required")
            print("Usage: python manage_rbac.py assign-role <username> <role_name>")
            return
        await assign_role_to_user(sys.argv[2], sys.argv[3])

    else:
        print(f"Unknown command: {command}")
        print_usage()


if __name__ == "__main__":
    asyncio.run(main())
