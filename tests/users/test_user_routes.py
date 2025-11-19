"""
User Routes Tests

Tests for user CRUD operations, registration, and profile management.
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_model import User
from app.core.security import get_password_hash
from conftest import assert_valid_user_response, assert_paginated_response


@pytest.mark.asyncio
class TestUserRegistration:
    """Test user registration/creation functionality."""

    async def test_create_user_success(self, client: AsyncClient):
        """Test successful user creation with valid data."""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "full_name": "New User Test",
            "phone": "+1234567890",
            "password": "Test123!@#",
            "password_confirm": "Test123!@#",
            "roles": [],
        }

        response = await client.post("/users", json=user_data)

        assert response.status_code == 201
        data = response.json()
        assert_valid_user_response(data)
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User Test"

    async def test_create_user_duplicate_username(
        self, client: AsyncClient, test_user: User
    ):
        """Test creating user with existing username."""
        user_data = {
            "username": "testuser",  # Already exists
            "email": "different@example.com",
            "full_name": "Different User",
            "password": "Test123!@#",
            "password_confirm": "Test123!@#",
            "roles": [],
        }

        response = await client.post("/users", json=user_data)

        assert response.status_code == 400
        assert "username" in response.json()["detail"].lower()

    async def test_create_user_duplicate_email(
        self, client: AsyncClient, test_user: User
    ):
        """Test creating user with existing email."""
        user_data = {
            "username": "differentuser",
            "email": "test@example.com",  # Already exists
            "full_name": "Different User",
            "password": "Test123!@#",
            "password_confirm": "Test123!@#",
            "roles": [],
        }

        response = await client.post("/users", json=user_data)

        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()

    async def test_create_user_password_mismatch(self, client: AsyncClient):
        """Test creating user with mismatched passwords."""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "full_name": "New User",
            "password": "Test123!@#",
            "password_confirm": "Different123!@#",
            "roles": [],
        }

        response = await client.post("/users", json=user_data)

        assert response.status_code == 422

    async def test_create_user_weak_password(self, client: AsyncClient):
        """Test creating user with password that doesn't meet requirements."""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "full_name": "New User",
            "password": "weak",
            "password_confirm": "weak",
            "roles": [],
        }

        response = await client.post("/users", json=user_data)

        assert response.status_code == 422

    async def test_create_user_invalid_email(self, client: AsyncClient):
        """Test creating user with invalid email format."""
        user_data = {
            "username": "newuser",
            "email": "notanemail",
            "full_name": "New User",
            "password": "Test123!@#",
            "password_confirm": "Test123!@#",
            "roles": [],
        }

        response = await client.post("/users", json=user_data)

        assert response.status_code == 422

    async def test_create_user_short_username(self, client: AsyncClient):
        """Test creating user with username that's too short."""
        user_data = {
            "username": "ab",  # Too short
            "email": "test@example.com",
            "full_name": "Test User",
            "password": "Test123!@#",
            "password_confirm": "Test123!@#",
            "roles": [],
        }

        response = await client.post("/users", json=user_data)

        assert response.status_code == 422


@pytest.mark.asyncio
class TestUserRetrieval:
    """Test getting user information."""

    async def test_get_user_own_profile(self, client: AsyncClient, auth_headers: dict):
        """Test user can view their own profile."""
        # Login to get own user ID
        login_data = {"username": "authuser", "password": "Test123!@#"}
        login_response = await client.post("/users/login", json=login_data)
        user_id = login_response.json()["id"]

        response = await client.get(f"/users/{user_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert_valid_user_response(data)
        assert data["id"] == user_id
        assert data["username"] == "authuser"

    async def test_get_other_user_forbidden(
        self, client: AsyncClient, auth_headers: dict, test_user: User
    ):
        """Test regular user cannot view another user's profile."""
        response = await client.get(f"/users/{test_user.id}", headers=auth_headers)

        assert response.status_code == 403

    async def test_get_user_as_admin(
        self, client: AsyncClient, admin_headers: dict, test_user: User
    ):
        """Test admin can view any user's profile."""
        response = await client.get(f"/users/{test_user.id}", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert_valid_user_response(data)
        assert data["username"] == "testuser"

    async def test_get_user_not_found(self, client: AsyncClient, admin_headers: dict):
        """Test getting non-existent user returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/users/{fake_id}", headers=admin_headers)

        assert response.status_code == 404

    async def test_get_user_without_auth(self, client: AsyncClient, test_user: User):
        """Test getting user without authentication."""
        response = await client.get(f"/users/{test_user.id}")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestUserUpdate:
    """Test updating user information."""

    async def test_update_user_admin(
        self, client: AsyncClient, admin_headers: dict, test_user: User
    ):
        """Test admin can update user."""
        update_data = {"full_name": "Updated Name", "email": "updated@example.com"}

        response = await client.patch(
            f"/users/{test_user.id}", json=update_data, headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"
        assert data["email"] == "updated@example.com"

    async def test_update_user_unauthorized(
        self, client: AsyncClient, auth_headers: dict, test_user: User
    ):
        """Test regular user cannot update another user."""
        update_data = {"full_name": "Hacker Name"}

        response = await client.patch(
            f"/users/{test_user.id}", json=update_data, headers=auth_headers
        )

        assert response.status_code == 403

    async def test_update_user_not_found(
        self, client: AsyncClient, admin_headers: dict
    ):
        """Test updating non-existent user returns 404."""
        fake_id = str(uuid.uuid4())
        update_data = {"full_name": "Test"}

        response = await client.patch(
            f"/users/{fake_id}", json=update_data, headers=admin_headers
        )

        assert response.status_code == 404

    async def test_update_user_invalid_email(
        self, client: AsyncClient, admin_headers: dict, test_user: User
    ):
        """Test updating user with invalid email."""
        update_data = {"email": "notanemail"}

        response = await client.patch(
            f"/users/{test_user.id}", json=update_data, headers=admin_headers
        )

        assert response.status_code == 422


@pytest.mark.asyncio
class TestUserDeletion:
    """Test deleting users."""

    async def test_delete_user_admin(
        self, client: AsyncClient, admin_headers: dict, test_user: User
    ):
        """Test admin can delete user."""
        response = await client.delete(f"/users/{test_user.id}", headers=admin_headers)

        assert response.status_code == 204

    async def test_delete_self_forbidden(
        self, client: AsyncClient, admin_headers: dict
    ):
        """Test admin cannot delete their own account."""
        # Get admin user ID
        login_data = {"username": "admintest", "password": "Admin123!@#"}
        login_response = await client.post("/users/login", json=login_data)
        admin_id = login_response.json()["id"]

        response = await client.delete(f"/users/{admin_id}", headers=admin_headers)

        assert response.status_code == 400
        assert "cannot delete your own" in response.json()["detail"].lower()

    async def test_delete_user_unauthorized(
        self, client: AsyncClient, auth_headers: dict, test_user: User
    ):
        """Test regular user cannot delete users."""
        response = await client.delete(f"/users/{test_user.id}", headers=auth_headers)

        assert response.status_code == 403

    async def test_delete_user_not_found(
        self, client: AsyncClient, admin_headers: dict
    ):
        """Test deleting non-existent user returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.delete(f"/users/{fake_id}", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.asyncio
class TestUserList:
    """Test listing and pagination of users."""

    async def test_list_users_admin(
        self, client: AsyncClient, admin_headers: dict, test_user: User
    ):
        """Test admin can list all users."""
        response = await client.get("/users", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert_paginated_response(data)
        assert len(data["items"]) > 0

    async def test_list_users_unauthorized(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test regular user cannot list users."""
        response = await client.get("/users", headers=auth_headers)

        assert response.status_code == 403

    async def test_list_users_pagination(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ):
        """Test pagination works correctly."""
        # Create multiple users
        for i in range(15):
            user = User(
                username=f"user{i}",
                email=f"user{i}@example.com",
                full_name=f"User {i}",
                password=get_password_hash("Test123!@#"),
            )
            db_session.add(user)
        await db_session.commit()

        # Get first page
        response = await client.get("/users?page=1&page_size=10", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page_info"]["current_page"] == 1
        assert data["page_info"]["has_next"] == True
        assert data["page_info"]["page_size"] == 10

    async def test_list_users_search(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ):
        """Test searching users by username."""
        # Create users with specific usernames
        user1 = User(
            username="john_doe",
            email="john@example.com",
            full_name="John Doe",
            password=get_password_hash("Test123!@#"),
        )
        user2 = User(
            username="jane_smith",
            email="jane@example.com",
            full_name="Jane Smith",
            password=get_password_hash("Test123!@#"),
        )
        db_session.add_all([user1, user2])
        await db_session.commit()

        response = await client.get("/users?search=john", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert any("john" in item["username"].lower() for item in data["items"])

    async def test_list_users_filter_active(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ):
        """Test filtering users by active status."""
        # Create active and inactive users
        active_user = User(
            username="active_user",
            email="active@example.com",
            full_name="Active User",
            password=get_password_hash("Test123!@#"),
            is_active=True,
        )
        inactive_user = User(
            username="inactive_user",
            email="inactive@example.com",
            full_name="Inactive User",
            password=get_password_hash("Test123!@#"),
            is_active=False,
        )
        db_session.add_all([active_user, inactive_user])
        await db_session.commit()

        response = await client.get("/users?is_active=true", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert all(item["is_active"] for item in data["items"])
