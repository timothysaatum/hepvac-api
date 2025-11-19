"""
Shared test fixtures and configuration for pytest.
"""

import pytest
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.rbac_init import initialize_rbac
from app.main import app
from app.db.base import Base
from app.models.user_model import User
from app.models.rbac import Role
from app.api.dependencies import get_db
from app.core.security import get_password_hash


# Test database configuration
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)

# Create test session maker
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database session for each test.

    This fixture:
    - Creates all tables
    - Initializes RBAC (roles and permissions)
    - Yields a session
    - Drops all tables after test
    """
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async with TestSessionLocal() as session:
        # Initialize RBAC
        await initialize_rbac(session)
        yield session

    # Drop tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def override_get_db(db_session: AsyncSession):
    """Override the get_db dependency for testing."""

    async def _override_get_db():
        yield db_session

    return _override_get_db


@pytest.fixture
async def client(override_get_db) -> AsyncGenerator[AsyncClient, None]:
    """
    Create test client with database override.

    This fixture overrides the database dependency to use the test database.
    """
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a standard test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        phone="+1234567890",
        password=get_password_hash("Test123!@#"),
        is_active=True,
        is_suspended=False,
        is_deleted=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin test user."""
    user = User(
        username="admin",
        email="admin@example.com",
        full_name="Admin User",
        password=get_password_hash("Admin123!@#"),
        is_active=True,
        is_suspended=False,
        is_deleted=False,
    )
    db_session.add(user)
    await db_session.commit()

    # Assign admin role
    from sqlalchemy import select

    result = await db_session.execute(select(Role).where(Role.name == "admin"))
    admin_role = result.scalar_one()
    user.roles.append(admin_role)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest.fixture
async def staff_user(db_session: AsyncSession) -> User:
    """Create a staff test user."""
    user = User(
        username="staff",
        email="staff@example.com",
        full_name="Staff User",
        password=get_password_hash("Staff123!@#"),
        is_active=True,
        is_suspended=False,
        is_deleted=False,
    )
    db_session.add(user)
    await db_session.commit()

    # Assign staff role
    from sqlalchemy import select

    result = await db_session.execute(select(Role).where(Role.name == "staff"))
    staff_role = result.scalar_one()
    user.roles.append(staff_role)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Get authentication headers for a regular user."""
    # Create user
    user_data = {
        "username": "authuser",
        "email": "auth@example.com",
        "full_name": "Auth User",
        "password": "Test123!@#",
        "password_confirm": "Test123!@#",
        "roles": [],
    }
    await client.post("/users", json=user_data)

    # Login
    login_data = {"username": "authuser", "password": "Test123!@#"}
    response = await client.post("/users/login", json=login_data)
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_headers(client: AsyncClient, db_session: AsyncSession) -> dict:
    """Get authentication headers for an admin user."""
    # Create admin user
    admin = User(
        username="admintest",
        email="admintest@example.com",
        full_name="Admin Test",
        password=get_password_hash("Admin123!@#"),
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()

    # Assign admin role
    from sqlalchemy import select

    result = await db_session.execute(select(Role).where(Role.name == "admin"))
    admin_role = result.scalar_one()
    admin.roles.append(admin_role)
    await db_session.commit()

    # Login
    login_data = {"username": "admintest", "password": "Admin123!@#"}
    response = await client.post("/users/login", json=login_data)
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_user_data() -> dict:
    """Sample user data for testing."""
    return {
        "username": "sampleuser",
        "email": "sample@example.com",
        "full_name": "Sample User",
        "phone": "+1234567890",
        "password": "Test123!@#",
        "password_confirm": "Test123!@#",
        "roles": [],
    }


# Helper functions for tests
def assert_valid_user_response(data: dict):
    """Assert that response contains valid user data."""
    assert "id" in data
    assert "username" in data
    assert "email" in data
    assert "full_name" in data
    assert "is_active" in data
    assert "created_at" in data
    assert "password" not in data  # Password should never be in response


def assert_paginated_response(data: dict):
    """Assert that response is a valid paginated response."""
    assert "items" in data
    assert "page_info" in data
    assert "total_items" in data["page_info"]
    assert "total_pages" in data["page_info"]
    assert "current_page" in data["page_info"]
    assert "page_size" in data["page_info"]
    assert "has_next" in data["page_info"]
    assert "has_previous" in data["page_info"]
