"""
RBAC Tests

Tests for role-based access control, permissions, and authorization.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user_model import User
from app.models.rbac import Role, Permission


@pytest.mark.asyncio
@pytest.mark.rbac
class TestRoleAssignment:
    """Test role assignment and management."""

    async def test_create_staff_user_admin(
        self, client: AsyncClient, admin_headers: dict
    ):
        """Test admin can create staff user."""
        staff_data = {
            "username": "staffuser",
            "email": "staff@example.com",
            "full_name": "Staff User",
            "password": "Test123!@#",
            "password_confirm": "Test123!@#",
            "roles": [],
        }

        response = await client.post(
            "/users/create-staff", json=staff_data, headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert any(role["name"] == "staff" for role in data["roles"])

    async def test_create_staff_user_unauthorized(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test regular user cannot create staff user."""
        staff_data = {
            "username": "staffuser",
            "email": "staff@example.com",
            "full_name": "Staff User",
            "password": "Test123!@#",
            "password_confirm": "Test123!@#",
            "roles": [],
        }

        response = await client.post(
            "/users/create-staff", json=staff_data, headers=auth_headers
        )

        assert response.status_code == 403

    async def test_user_has_role(self, admin_user: User):
        """Test user has assigned role."""
        assert admin_user.has_role("admin")
        assert not admin_user.has_role("superadmin")
        assert not admin_user.has_role("nonexistent")

    async def test_user_has_permission(
        self, admin_user: User, db_session: AsyncSession
    ):
        """Test user has permissions through roles."""
        # Admin should have user management permissions
        assert admin_user.has_permission("user.read")
        assert admin_user.has_permission("user.create")

    async def test_staff_limited_permissions(self, staff_user: User):
        """Test staff user has limited permissions."""
        assert staff_user.has_role("staff")
        # Staff should have read permission
        assert staff_user.has_permission("user.read")
        # Staff should NOT have delete permission
        assert not staff_user.has_permission("user.delete")


@pytest.mark.asyncio
@pytest.mark.rbac
class TestRoleBasedEndpointAccess:
    """Test endpoint access based on roles."""

    async def test_admin_can_list_users(self, client: AsyncClient, admin_headers: dict):
        """Test admin can access user list endpoint."""
        response = await client.get("/users", headers=admin_headers)
        assert response.status_code == 200

    async def test_staff_cannot_list_users(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test staff cannot access admin endpoints."""
        # Create staff user and get token
        from app.core.security import get_password_hash

        staff = User(
            username="stafftest",
            email="stafftest@example.com",
            full_name="Staff Test",
            password=get_password_hash("Staff123!@#"),
            is_active=True,
        )
        db_session.add(staff)
        await db_session.commit()

        # Assign staff role
        result = await db_session.execute(select(Role).where(Role.name == "staff"))
        staff_role = result.scalar_one()
        staff.roles.append(staff_role)
        await db_session.commit()

        # Login as staff
        login_data = {"username": "stafftest", "password": "Staff123!@#"}
        response = await client.post("/users/login", json=login_data)
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try to access admin endpoint
        response = await client.get("/users", headers=headers)
        assert response.status_code == 403

    async def test_regular_user_cannot_access_admin_endpoints(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test regular user (no roles) cannot access admin endpoints."""
        response = await client.get("/users", headers=auth_headers)
        assert response.status_code == 403

    async def test_admin_can_delete_users(
        self, client: AsyncClient, admin_headers: dict, test_user: User
    ):
        """Test admin has delete permissions."""
        response = await client.delete(f"/users/{test_user.id}", headers=admin_headers)
        assert response.status_code == 204

    async def test_regular_user_cannot_delete_users(
        self, client: AsyncClient, auth_headers: dict, test_user: User
    ):
        """Test regular user cannot delete users."""
        response = await client.delete(f"/users/{test_user.id}", headers=auth_headers)
        assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.rbac
class TestRoleInitialization:
    """Test that default roles and permissions are initialized."""

    async def test_default_roles_exist(self, db_session: AsyncSession):
        """Test that default roles are created."""
        result = await db_session.execute(select(Role))
        roles = result.scalars().all()
        role_names = [role.name for role in roles]

        assert "superadmin" in role_names
        assert "admin" in role_names
        assert "staff" in role_names

    async def test_default_permissions_exist(self, db_session: AsyncSession):
        """Test that default permissions are created."""
        result = await db_session.execute(select(Permission))
        permissions = result.scalars().all()
        permission_names = [perm.name for perm in permissions]

        # Check some key permissions
        assert "user.create" in permission_names
        assert "user.read" in permission_names
        assert "user.update" in permission_names
        assert "user.delete" in permission_names

    async def test_superadmin_has_all_permissions(self, db_session: AsyncSession):
        """Test that superadmin role has all permissions."""
        result = await db_session.execute(select(Role).where(Role.name == "superadmin"))
        superadmin_role = result.scalar_one()

        # Superadmin should have many permissions
        assert len(superadmin_role.permissions) > 10

    async def test_admin_has_limited_permissions(self, db_session: AsyncSession):
        """Test that admin role has fewer permissions than superadmin."""
        result = await db_session.execute(select(Role).where(Role.name == "admin"))
        admin_role = result.scalar_one()

        result = await db_session.execute(select(Role).where(Role.name == "superadmin"))
        superadmin_role = result.scalar_one()

        # Admin should have fewer permissions than superadmin
        assert len(admin_role.permissions) < len(superadmin_role.permissions)

    async def test_staff_has_minimal_permissions(self, db_session: AsyncSession):
        """Test that staff role has minimal permissions."""
        result = await db_session.execute(select(Role).where(Role.name == "staff"))
        staff_role = result.scalar_one()

        # Staff should have the fewest permissions
        assert len(staff_role.permissions) > 0
        assert len(staff_role.permissions) < 5


@pytest.mark.asyncio
@pytest.mark.rbac
class TestPermissionChecks:
    """Test permission checking logic."""

    async def test_check_specific_permission(self, admin_user: User):
        """Test checking for specific permissions."""
        # Admin should have user.create permission
        assert admin_user.has_permission("user.create") == True

        # Admin should not have a non-existent permission
        assert admin_user.has_permission("nonexistent.permission") == False

    async def test_multiple_roles_combine_permissions(self, db_session: AsyncSession):
        """Test that users with multiple roles have combined permissions."""
        from app.core.security import get_password_hash

        # Create user
        user = User(
            username="multirole",
            email="multirole@example.com",
            full_name="Multi Role",
            password=get_password_hash("Test123!@#"),
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        # Assign both admin and staff roles
        result = await db_session.execute(select(Role).where(Role.name == "admin"))
        admin_role = result.scalar_one()

        result = await db_session.execute(select(Role).where(Role.name == "staff"))
        staff_role = result.scalar_one()

        user.roles.extend([admin_role, staff_role])
        await db_session.commit()
        await db_session.refresh(user)

        # User should have admin role
        assert user.has_role("admin")
        # User should have staff role
        assert user.has_role("staff")
        # User should have admin permissions
        assert user.has_permission("user.create")
