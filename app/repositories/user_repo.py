from datetime import datetime, timezone
from app.models.user_model import User as UserModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.rbac import Role
from typing import Optional, List


class UserRepository:
    """Repository layer for user data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_id(self, user_id: str) -> Optional[UserModel]:
        """
        Get user by ID.

        Args:
            user_id: User's unique identifier

        Returns:
            User model or None if not found
        """
        result = await self.db.execute(
            select(UserModel).where(
                UserModel.id == user_id, UserModel.is_deleted == False
            )
        )
        return result.scalars().first()

    async def get_users(self, skip: int = 0, limit: int = 100) -> List[UserModel]:
        """
        Get paginated list of users.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of user models
        """
        result = await self.db.execute(
            select(UserModel)
            .where(UserModel.is_deleted == False)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        """
        Get user by username.

        Args:
            username: User's username

        Returns:
            User model or None if not found
        """
        result = await self.db.execute(
            select(UserModel).where(
                UserModel.username == username, UserModel.is_deleted == False
            )
        )
        return result.scalars().first()

    async def get_user_by_email(self, email: str) -> Optional[UserModel]:
        """
        Get user by email address.

        Args:
            email: User's email address

        Returns:
            User model or None if not found
        """
        result = await self.db.execute(
            select(UserModel).where(
                UserModel.email == email.lower(),
                UserModel.is_deleted == False,
            )
        )
        return result.scalars().first()

    async def create_user(self, user: UserModel) -> UserModel:
        """
        Create a new user in the database.

        Args:
            user: User ORM model (not Pydantic schema!)

        Returns:
            Created user model with ID and timestamps
        """
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def assign_role_to_user(self, user: UserModel, role_name: str) -> None:
        """
        Assign a role to a user.

        Args:
            user: User ORM model
            role_name: Name of the role to assign

        Raises:
            ValueError: If role doesn't exist
        """
        result = await self.db.execute(select(Role).where(Role.name == role_name))
        role = result.scalars().first()

        if not role:
            raise ValueError(f"Role '{role_name}' does not exist")

        if role not in user.roles:
            user.roles.append(role)
            await self.db.commit()
            await self.db.refresh(user)

    async def revoke_user_role(self, user: UserModel, role_name: str) -> None:
        """
        Revoke a role from a user.

        Args:
            user: User ORM model
            role_name: Name of the role to revoke
        """
        result = await self.db.execute(select(Role).where(Role.name == role_name))
        role = result.scalars().first()

        if role and role in user.roles:
            user.roles.remove(role)
            await self.db.commit()
            await self.db.refresh(user)

    async def delete_user(self, user: UserModel) -> None:
        """
        Soft delete a user (mark as deleted).

        Args:
            user: User ORM model to delete
        """
        user.is_deleted = True
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)

    async def update_user(self, user: UserModel) -> UserModel:
        """
        Update an existing user.

        Args:
            user: User ORM model with updated values

        Returns:
            Updated user model
        """
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def suspend_staff(self, user: UserModel) -> UserModel:
        """"
        Suspend Existing user.

        Args:
            user: User ORM model with is_suspended

        Returns:
            A user model
        """
        user.is_suspended = True
        user.is_active = False
        await self.db.commit()
        await self.db.refresh(user)

        return user     