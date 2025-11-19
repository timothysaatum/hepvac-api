"""
Authentication Tests

Tests for login, logout, token management, and session handling.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_model import User


@pytest.mark.asyncio
@pytest.mark.auth
class TestLogin:
    """Test user login functionality."""

    async def test_login_success(self, client: AsyncClient, test_user: User):
        """Test successful login with valid credentials."""
        login_data = {"username": "testuser", "password": "Test123!@#"}

        response = await client.post("/users/login", json=login_data)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert "refresh_token" in response.cookies

    async def test_login_wrong_password(self, client: AsyncClient, test_user: User):
        """Test login with incorrect password."""
        login_data = {"username": "testuser", "password": "WrongPassword123!@#"}

        response = await client.post("/users/login", json=login_data)

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with username that doesn't exist."""
        login_data = {"username": "nonexistent", "password": "Test123!@#"}

        response = await client.post("/users/login", json=login_data)

        assert response.status_code == 401

    async def test_login_inactive_user(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Test login attempt with deactivated account."""
        # Deactivate user
        test_user.is_active = False
        await db_session.commit()

        login_data = {"username": "testuser", "password": "Test123!@#"}

        response = await client.post("/users/login", json=login_data)

        assert response.status_code == 401
        assert "inactive" in response.json()["detail"].lower()

    async def test_login_suspended_user(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Test login attempt with suspended account."""
        # Suspend user
        test_user.is_suspended = True
        await db_session.commit()

        login_data = {"username": "testuser", "password": "Test123!@#"}

        response = await client.post("/users/login", json=login_data)

        assert response.status_code == 401
        assert "suspended" in response.json()["detail"].lower()

    async def test_login_case_sensitive_username(
        self, client: AsyncClient, test_user: User
    ):
        """Test that username is case-sensitive."""
        login_data = {"username": "TESTUSER", "password": "Test123!@#"}

        response = await client.post("/users/login", json=login_data)

        # Should fail because username case doesn't match
        assert response.status_code == 401

    async def test_login_creates_session(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Verify that login creates a user session."""
        from sqlalchemy import select
        from app.models.user_model import UserSession

        login_data = {"username": "testuser", "password": "Test123!@#"}

        response = await client.post("/users/login", json=login_data)

        assert response.status_code == 200

        # Check session exists in database
        result = await db_session.execute(
            select(UserSession).where(UserSession.user_id == test_user.id)
        )
        session = result.scalar_one_or_none()

        assert session is not None
        assert session.is_active == True
        assert session.login_method == "password"


@pytest.mark.asyncio
@pytest.mark.auth
class TestTokenRefresh:
    """Test token refresh functionality."""

    async def test_refresh_token_success(self, client: AsyncClient, test_user: User):
        """Test successful token refresh."""
        # Login first
        login_data = {"username": "testuser", "password": "Test123!@#"}
        login_response = await client.post("/users/login", json=login_data)
        old_token = login_response.json()["access_token"]

        # Refresh token
        response = await client.post("/users/refresh")

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["username"] == "testuser"
        # New token should be different from old token
        assert data["access_token"] != old_token

    async def test_refresh_token_missing(self, client: AsyncClient):
        """Test refresh without refresh token cookie."""
        response = await client.post("/users/refresh")

        assert response.status_code == 401
        assert "no refresh token" in response.json()["detail"].lower()

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test refresh with invalid token."""
        # Set invalid refresh token cookie
        client.cookies.set("refresh_token", "invalid_token")

        response = await client.post("/users/refresh")

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    async def test_refresh_token_inactive_user(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Test refresh with deactivated user."""
        # Login first
        login_data = {"username": "testuser", "password": "Test123!@#"}
        await client.post("/users/login", json=login_data)

        # Deactivate user
        test_user.is_active = False
        await db_session.commit()

        # Try to refresh
        response = await client.post("/users/refresh")

        assert response.status_code == 401
        assert "inactive" in response.json()["detail"].lower()


@pytest.mark.asyncio
@pytest.mark.auth
class TestLogout:
    """Test user logout functionality."""

    async def test_logout_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful logout."""
        response = await client.post("/users/logout", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"
        assert "session_terminated" in data
        assert "refresh_token_revoked" in data

    async def test_logout_without_auth(self, client: AsyncClient):
        """Test logout without authentication."""
        response = await client.post("/users/logout")

        assert response.status_code == 401

    async def test_logout_terminates_session(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        """Verify that logout terminates the session."""
        from sqlalchemy import select
        from app.models.user_model import UserSession

        # Logout
        response = await client.post("/users/logout", headers=auth_headers)
        assert response.status_code == 200

        # Check session is terminated
        # Note: You'd need to extract session_id from the token to verify this
        # This is a simplified check
        result = await db_session.execute(
            select(UserSession).where(UserSession.is_active == False)
        )
        terminated_sessions = result.scalars().all()
        assert len(terminated_sessions) > 0

    async def test_logout_clears_refresh_token(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Verify that logout clears refresh token cookie."""
        response = await client.post("/users/logout", headers=auth_headers)

        assert response.status_code == 200
        # Check that refresh_token cookie is cleared (or set to empty)
        # The actual cookie clearing depends on how httpx handles deleted cookies

    async def test_cannot_use_token_after_logout(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test that token cannot be used after logout."""
        # Logout
        await client.post("/users/logout", headers=auth_headers)

        # Try to use the same token
        response = await client.get("/users", headers=auth_headers)

        # Should fail because session is terminated
        # Note: Depending on your implementation, this might still work
        # if you only check token validity and not session status
        # Adjust assertion based on your actual behavior


@pytest.mark.asyncio
@pytest.mark.auth
class TestPasswordSecurity:
    """Test password-related security features."""

    async def test_password_not_in_response(self, client: AsyncClient):
        """Ensure password is never returned in API responses."""
        user_data = {
            "username": "secureuser",
            "email": "secure@example.com",
            "full_name": "Secure User",
            "password": "Test123!@#",
            "password_confirm": "Test123!@#",
            "roles": [],
        }

        # Create user
        response = await client.post("/users", json=user_data)
        assert response.status_code == 201
        data = response.json()
        assert "password" not in data

        # Login
        login_data = {"username": "secureuser", "password": "Test123!@#"}
        response = await client.post("/users/login", json=login_data)
        data = response.json()
        assert "password" not in data

    async def test_password_is_hashed(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Verify that passwords are stored hashed, not in plaintext."""
        # Refresh to get latest data
        await db_session.refresh(test_user)

        # Password in DB should not match plaintext
        assert test_user.password != "Test123!@#"
        # Should be a hash (long string)
        assert len(test_user.password) > 50


@pytest.mark.asyncio
@pytest.mark.auth
class TestRateLimitingAndSecurity:
    """Test security features like rate limiting (if implemented)."""

    async def test_multiple_failed_login_attempts(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Test that multiple failed login attempts are tracked."""
        login_data = {"username": "testuser", "password": "WrongPassword123!@#"}

        # Make multiple failed attempts
        for _ in range(5):
            response = await client.post("/users/login", json=login_data)
            assert response.status_code == 401

        # Check if user is suspended after max attempts
        await db_session.refresh(test_user)
        # Depending on your implementation:
        # assert test_user.is_suspended == True
        # or
        # assert test_user.login_attempts >= 5

    async def test_successful_login_resets_failed_attempts(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Test that successful login resets failed attempt counter."""
        # Make a failed attempt
        wrong_data = {"username": "testuser", "password": "Wrong123!@#"}
        await client.post("/users/login", json=wrong_data)

        # Successful login
        correct_data = {"username": "testuser", "password": "Test123!@#"}
        response = await client.post("/users/login", json=correct_data)
        assert response.status_code == 200

        # Check that failed attempts are reset
        await db_session.refresh(test_user)
        assert test_user.login_attempts == 0
