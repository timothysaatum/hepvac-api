# test_services.py
"""
Service Layer Tests

Tests for business logic in service layer.
"""
import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.user_service import UserService
from app.schemas.user_schemas import UserCreateSchema, UserUpdateSchema
from app.models.user_model import User
from app.core.security import get_password_hash


@pytest.mark.asyncio
@pytest.mark.unit
class TestUserService:
    """Test UserService business logic."""

    async def test_create_user_service(self, db_session: AsyncSession):
        """Test creating user through service."""
        service = UserService(db_session)
        user_data = UserCreateSchema(
            username="serviceuser",
            email="service@example.com",
            full_name="Service User",
            password="Test123!@#",
            password_confirm="Test123!@#",
            roles=[],
        )

        user = await service.create_user(user_data)

        assert user.username == "serviceuser"
        assert user.email == "service@example.com"
        assert user.password != "Test123!@#"  # Should be hashed

    async def test_create_user_duplicate_username(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test service prevents duplicate usernames."""
        service = UserService(db_session)
        user_data = UserCreateSchema(
            username="testuser",  # Already exists
            email="different@example.com",
            full_name="Different User",
            password="Test123!@#",
            password_confirm="Test123!@#",
            roles=[],
        )

        with pytest.raises(Exception):  # Should raise HTTPException
            await service.create_user(user_data)

    async def test_get_user_by_id_service(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test getting user by ID through service."""
        service = UserService(db_session)

        user = await service.get_user_by_id(test_user.id)

        assert user is not None
        assert user.id == test_user.id
        assert user.username == test_user.username

    async def test_get_user_by_id_not_found(self, db_session: AsyncSession):
        """Test getting non-existent user returns None."""
        service = UserService(db_session)
        fake_id = uuid.uuid4()

        user = await service.get_user_by_id(fake_id)

        assert user is None

    async def test_update_user_service(self, db_session: AsyncSession, test_user: User):
        """Test updating user through service."""
        service = UserService(db_session)
        update_data = UserUpdateSchema(
            full_name="Updated Name", email="updated@example.com"
        )

        updated_user = await service.update_user_account(test_user.id, update_data)

        assert updated_user.full_name == "Updated Name"
        assert updated_user.email == "updated@example.com"

    async def test_delete_user_service(self, db_session: AsyncSession, test_user: User):
        """Test soft deleting user through service."""
        service = UserService(db_session)

        success = await service.delete_user(test_user.id)

        assert success == True

        # Verify user is marked as deleted
        await db_session.refresh(test_user)
        assert test_user.is_deleted == True

    async def test_list_users_service(self, db_session: AsyncSession, test_user: User):
        """Test listing users through service."""
        service = UserService(db_session)

        users = await service.list_users(skip=0, limit=10)

        assert len(users) > 0
        assert isinstance(users, list)


# test_repositories.py
"""
Repository Layer Tests

Tests for data access layer (repositories).
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repo import UserRepository
from app.models.user_model import User
from app.core.security import get_password_hash


@pytest.mark.asyncio
@pytest.mark.unit
class TestUserRepository:
    """Test UserRepository data access methods."""

    async def test_create_user_repo(self, db_session: AsyncSession):
        """Test creating user in repository."""
        repo = UserRepository(db_session)
        user = User(
            username="repouser",
            email="repo@example.com",
            full_name="Repo User",
            password=get_password_hash("Test123!@#"),
        )

        created_user = await repo.create_user(user)

        assert created_user.id is not None
        assert created_user.username == "repouser"

    async def test_get_user_by_id_repo(self, db_session: AsyncSession, test_user: User):
        """Test getting user by ID from repository."""
        repo = UserRepository(db_session)

        user = await repo.get_user_by_id(str(test_user.id))

        assert user is not None
        assert user.id == test_user.id

    async def test_get_user_by_username_repo(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test getting user by username from repository."""
        repo = UserRepository(db_session)

        user = await repo.get_user_by_username("testuser")

        assert user is not None
        assert user.username == "testuser"

    async def test_get_user_by_email_repo(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test getting user by email from repository."""
        repo = UserRepository(db_session)

        user = await repo.get_user_by_email("test@example.com")

        assert user is not None
        assert user.email == "test@example.com"

    async def test_update_user_repo(self, db_session: AsyncSession, test_user: User):
        """Test updating user in repository."""
        repo = UserRepository(db_session)

        test_user.full_name = "Updated Name"
        updated_user = await repo.update_user(test_user)

        assert updated_user.full_name == "Updated Name"

    async def test_delete_user_repo(self, db_session: AsyncSession, test_user: User):
        """Test soft deleting user in repository."""
        repo = UserRepository(db_session)

        await repo.delete_user(test_user)

        # Verify user is marked as deleted
        await db_session.refresh(test_user)
        assert test_user.is_deleted == True
        assert test_user.is_active == False

    async def test_get_users_pagination_repo(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test getting paginated users from repository."""
        repo = UserRepository(db_session)

        # Create additional users
        for i in range(5):
            user = User(
                username=f"paginuser{i}",
                email=f"pagin{i}@example.com",
                full_name=f"Pagin User {i}",
                password=get_password_hash("Test123!@#"),
            )
            db_session.add(user)
        await db_session.commit()

        # Get first page
        users = await repo.get_users(skip=0, limit=3)

        assert len(users) == 3

        # Get second page
        users = await repo.get_users(skip=3, limit=3)

        assert len(users) >= 1

    async def test_assign_role_to_user_repo(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test assigning role to user in repository."""
        repo = UserRepository(db_session)

        await repo.assign_role_to_user(test_user, "staff")

        # Verify role was assigned
        await db_session.refresh(test_user)
        assert any(role.name == "staff" for role in test_user.roles)

    async def test_assign_nonexistent_role_repo(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test assigning non-existent role raises error."""
        repo = UserRepository(db_session)

        with pytest.raises(ValueError):
            await repo.assign_role_to_user(test_user, "nonexistent")

    async def test_revoke_role_from_user_repo(
        self, db_session: AsyncSession, staff_user: User
    ):
        """Test revoking role from user in repository."""
        repo = UserRepository(db_session)

        await repo.revoke_user_role(staff_user, "staff")

        # Verify role was revoked
        await db_session.refresh(staff_user)
        assert not any(role.name == "staff" for role in staff_user.roles)
