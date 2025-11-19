from typing import List, Optional, Tuple
import uuid
from fastapi import Request, Response, HTTPException, status
from app.core.sessions import SessionManager, TokenManager
from app.middlewares.auth_middleware import authenticate_user, set_refresh_token_cookie
from app.models.user_model import User
from app.schemas.user_schemas import UserCreateSchema, UserUpdateSchema
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repo import UserRepository
from app.core.security import get_password_hash


class UserService:
    """Service layer for user business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(self.db)

    async def create_user(self, user_data: UserCreateSchema) -> User:
        """
        Create a new user from Pydantic schema.

        Args:
            user_data: UserCreateSchema with user creation data

        Returns:
            User: Created ORM user model

        Raises:
            HTTPException: If user already exists
        """

        # Check if username already exists
        existing_user = await self.repo.get_user_by_username(user_data.username)
        if existing_user:

            if existing_user.email in user_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists"
                )

        user_dict = user_data.model_dump(exclude={"password_confirm", "roles"})

        # Hash the password before storing
        user_dict["password"] = get_password_hash(user_data.password)

        db_user = User(**user_dict)

        # Create the user in database
        created_user = await self.repo.create_user(db_user)

        # Assign roles if provided
        if user_data.roles:
            for role_name in user_data.roles:
                try:
                    await self.repo.assign_role_to_user(created_user, role_name)
                except Exception as e:
                    # Log role assignment failure but don't fail user creation
                    print(f"Failed to assign role {role_name}: {str(e)}")

        # Refresh to get updated roles
        await self.db.refresh(created_user)

        return created_user

    async def login_user(
        self,
        username: str,
        password: str,
        ip_address: str = None,
        user_agent: str = None,
        request: Request = None,
        response: Response = None,
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Login user with enhanced security features.

        Args:
            username: User's username
            password: User's password (plain text)
            ip_address: Client IP address
            user_agent: Client user agent string
            request: FastAPI request object
            response: FastAPI response object

        Returns:
            Tuple of (success, user, access_token_or_error_message)
        """
        auth_success, user, error_message = await authenticate_user(
            db=self.db,
            username=username,
            password=password,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if not auth_success or not user:
            return False, user, error_message

        # Create session for the authenticated user
        session = await SessionManager.create_session(
            db=self.db, user_id=user.id, request=request, login_method="password"
        )

        # Create access token with session reference
        access_token = TokenManager.create_access_token(
            data={"sub": str(user.id)}, session_id=session.id
        )

        # Create refresh token
        refresh_token = TokenManager.create_refresh_token(user.id)

        # Store refresh token in database
        await TokenManager.create_refresh_token_record(
            db=self.db,
            user_id=user.id,
            token=refresh_token,
            device_info=user_agent,
            ip_address=ip_address,
        )

        # Set refresh token as HTTP-only cookie
        if response:
            set_refresh_token_cookie(
                response=response,
                refresh_token=refresh_token,
                request=request,
            )

        return True, user, access_token

    async def update_user_account(self, user_id: uuid.UUID, user_data: UserUpdateSchema):

        user = await self.repo.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User with the given id not found"
            )
        update_data = user_data.model_dump(exclude_unset=True)

        # Apply updates to the existing user
        for field, value in update_data.items():
            setattr(user, field, value)

        updated_user = await self.repo.update_user(user)

        return updated_user

    async def delete_account(self, user_id: uuid.UUID):
        user = await self.repo.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User with the given id not found"
            )

        await self.repo.delete_user(user)

        return True

    async def suspend_staff(self, user_id: uuid.UUID):

        staff = await self.repo.get_user_by_id(user_id)

        if staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User with the given id not found"
            ) 
        await self.repo.suspend_staff(staff)

    async def list_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """
        Get paginated list of users.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of User models
        """
        return await self.repo.get_users(skip=skip, limit=limit)
