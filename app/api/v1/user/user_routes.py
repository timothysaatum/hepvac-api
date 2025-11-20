from datetime import datetime, timezone
import traceback
import uuid
from app.core.pagination import PaginatedResponse, PaginationParams, Paginator, get_pagination_params
from app.core.permission_checker import require_admin
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from app.core.security import get_current_user
from app.core.sessions import SessionManager, TokenManager
from app.middlewares.security_middleware import DeviceTrustService
from app.models.rbac import Role
from app.models.user_model import User
from app.schemas.user_schemas import (
    UserCreateSchema, 
    UserLoginSchema, 
    UserSchema,
    AuthResponse,
    UserUpdateSchema
    )
from app.services.user_service import UserService
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db
from app.core.utils import logger


router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreateSchema,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new user account.

    Args:
        user_data: User creation data including credentials
        db: Database session

    Returns:
        UserSchema: Created user information

    Raises:
        HTTPException: If user creation fails
    """
    user_service = UserService(db)
    try:
        user = await user_service.create_user(user_data)
        return UserSchema.model_validate(user, from_attributes=True)

    except ValueError as e:
        # Handle validation errors
        logger.log_warning(
            {
                "event": "user_creation_failed",
                "reason": "validation_error",
                "error": str(e),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except Exception as e:
        # Log unexpected errors
        logger.log_error(
            {
                "event": "user_creation_error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the user",
        )


# @router.post("/login", response_model=AuthResponse)
# async def login_user(
#     login_data: UserLoginSchema,
#     request: Request,
#     response: Response,
#     db: AsyncSession = Depends(get_db),
# ):
#     """
#     Authenticate user and create session.

#     Args:
#         login_data: Login credentials
#         request: FastAPI request object
#         response: FastAPI response object
#         db: Database session

#     Returns:
#         AuthResponse: Authenticated user information with access token

#     Raises:
#         HTTPException: If authentication fails
#     """
#     user_service = UserService(db)
#     device_data = SessionManager.extract_device_info(request)
#     user_agent = device_data["user_agent"]
#     ip_address = device_data["client_ip"]
#     try:
#         success, user, token_or_error = await user_service.login_user(
#             username=login_data.username,
#             password=login_data.password,
#             ip_address=ip_address,
#             request=request,
#             response=response,
#             user_agent=user_agent
#         )

#         if not success or not user:
#             logger.log_warning(
#                 {
#                     "event": "login_failed",
#                     "username": login_data.username,
#                     "ip_address": ip_address,
#                     "reason": token_or_error,
#                 }
#             )
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail=token_or_error or "Invalid credentials",
#             )

#         logger.log_info(
#             {
#                 "event": "login_success",
#                 "username": login_data.username,
#                 "ip_address": ip_address,
#                 "user_id": str(user.id),
#             }
#         )

#         # Validate user to UserSchema
#         user_data = UserSchema.model_validate(user, from_attributes=True)

#         # Create AuthResponse by adding access_token
#         return AuthResponse(
#             **user_data.model_dump(),
#             access_token=token_or_error
#         )

#     except HTTPException:
#         # Re-raise HTTP exceptions as-is
#         raise

#     except Exception as e:
#         # Log unexpected errors
#         logger.log_error(
#             {
#                 "event": "login_error",
#                 "username": login_data.username,
#                 "ip_address": ip_address,
#                 "error": str(e),
#                 "error_type": type(e).__name__,
#             }
#         )
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="An unexpected error occurred during login",
#         )
@router.post("/login", response_model=AuthResponse)
async def login_user(
    login_data: UserLoginSchema,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and create session.

    Args:
        login_data: Login credentials
        request: FastAPI request object
        response: FastAPI response object
        db: Database session

    Returns:
        AuthResponse: Authenticated user information with access token

    Raises:
        HTTPException: If authentication fails or device is not trusted
    """
    user_service = UserService(db)
    device_data = SessionManager.extract_device_info(request)
    user_agent = device_data["user_agent"]
    ip_address = device_data["client_ip"]

    try:
        # Step 1: Authenticate user credentials
        success, user, token_or_error = await user_service.login_user(
            username=login_data.username,
            password=login_data.password,
            ip_address=ip_address,
            request=request,
            response=response,
            user_agent=user_agent,
        )

        if not success or not user:
            logger.log_warning(
                {
                    "event": "login_failed",
                    "username": login_data.username,
                    "ip_address": ip_address,
                    "reason": token_or_error,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=token_or_error or "Invalid credentials",
            )

        # Step 2: Check device trust AFTER successful authentication
        try:
            is_trusted, message, is_new = (
                await DeviceTrustService.check_and_register_device(
                    request=request, user_id=user.id, db=db
                )
            )
        except HTTPException as device_error:
            # Device not trusted - log the blocked attempt
            logger.log_warning(
                {
                    "event": "device_trust_blocked",
                    "username": login_data.username,
                    "user_id": str(user.id),
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "reason": device_error.detail,
                }
            )
            # Re-raise the device trust error to block login
            raise device_error

        # Step 3: Device is trusted, proceed with login
        logger.log_info(
            {
                "event": "login_success",
                "username": login_data.username,
                "ip_address": ip_address,
                "user_id": str(user.id),
                "device_trusted": True,
                "new_device": is_new,
            }
        )

        # Validate user to UserSchema
        user_data = UserSchema.model_validate(user, from_attributes=True)

        # Create AuthResponse by adding access_token
        return AuthResponse(**user_data.model_dump(), access_token=token_or_error)

    except HTTPException:
        # Re-raise HTTP exceptions as-is (including device trust errors)
        raise

    except Exception as e:
        # Log unexpected errors
        logger.log_error(
            {
                "event": "login_error",
                "username": login_data.username,
                "ip_address": ip_address,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during login",
        )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token from HTTP-only cookie.

    The refresh token maintains its original absolute expiration time and is reused.
    Only the access token is regenerated with a new session.

    Returns:
        AuthResponse: User data with new access token

    Raises:
        HTTPException: If refresh token is invalid, expired, or user is inactive
    """
    session_data = SessionManager.extract_device_info(request)
    client_ip = session_data.get("client_ip")

    logger.log_info(
        {
            "event_type": "token_refresh_attempt",
            "client_ip": client_ip,
            "user_agent": session_data.get("parsed_ua", {}).get("browser"),
        }
    )

    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        logger.log_security_event(
            {
                "event_type": "token_refresh_failed",
                "reason": "no_refresh_token",
                "ip_address": client_ip,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided"
        )

    try:
        # Validate refresh token
        refresh_token_record = await TokenManager.validate_refresh_token(
            db, refresh_token
        )

        if not refresh_token_record:
            logger.log_security_event(
                {
                    "event_type": "token_refresh_failed",
                    "reason": "invalid_refresh_token",
                    "ip_address": client_ip,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        # Check absolute expiration
        current_time = datetime.now(timezone.utc)
        absolute_expiry = refresh_token_record.absolute_expiry
        if absolute_expiry.tzinfo is None:
            absolute_expiry = absolute_expiry.replace(tzinfo=timezone.utc)

        if current_time > absolute_expiry:
            # Revoke expired token
            await TokenManager.revoke_refresh_token(db, refresh_token_record.id)

            logger.log_security_event(
                {
                    "event_type": "token_refresh_failed",
                    "reason": "refresh_token_absolutely_expired",
                    "absolute_expiry": absolute_expiry.isoformat(),
                    "current_time": current_time.isoformat(),
                    "ip_address": client_ip,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired. Please log in again.",
            )

        # Get user with relationships
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.id == refresh_token_record.user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
            )

        # Validate user status
        if not user.is_active or user.is_suspended:
            logger.log_security_event(
                {
                    "event_type": "token_refresh_failed",
                    "reason": "user_account_inactive",
                    "user_id": str(user.id),
                    "is_active": user.is_active,
                    "is_suspended": user.is_suspended,
                    "ip_address": client_ip,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive or suspended",
            )

        # Create new session for token refresh
        session = await SessionManager.create_session(
            db=db, user_id=user.id, request=request, login_method="refresh_token"
        )

        # Create new access token with session reference
        new_access_token = TokenManager.create_access_token(
            data={"sub": str(user.id)}, session_id=session.id
        )

        # Update refresh token usage stats (reuse existing token)
        refresh_token_record.mark_as_used()

        # Update IP and device info if changed
        if refresh_token_record.ip_address != client_ip:
            refresh_token_record.ip_address = client_ip

        import json

        device_info_str = json.dumps(session_data.get("parsed_ua", {}))
        if refresh_token_record.device_info != device_info_str:
            refresh_token_record.device_info = device_info_str

        await db.commit()


        logger.log_security_event(
            {
                "event_type": "token_refresh_success",
                "user_id": str(user.id),
                "session_id": str(session.id),
                "refresh_token_usage_count": refresh_token_record.usage_count,
                "refresh_token_absolute_expiry": absolute_expiry.isoformat(),
                "ip_address": client_ip,
            }
        )

        logger.log_info(
            {
                "event_type": "token_refresh_success",
                "user_id": str(user.id),
                "session_id": str(session.id),
            }
        )

        # Create response
        user_data = UserSchema.model_validate(user, from_attributes=True)
        return AuthResponse(**user_data.model_dump(), access_token=new_access_token)

    except HTTPException:
        raise
    except Exception as e:

        logger.log_error(
            {
                "event_type": "token_refresh_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "ip_address": client_ip,
            },
            exc_info=True,
        )

        logger.log_security_event(
            {
                "event_type": "token_refresh_error",
                "reason": "unexpected_error",
                "error": str(e),
                "ip_address": client_ip,
            }
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {type(e).__name__}",
        )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Logout user by terminating session and revoking refresh token.

    This endpoint:
    - Terminates the current session
    - Revokes the refresh token
    - Clears the refresh token cookie

    Args:
        request: FastAPI request object
        response: FastAPI response object
        db: Database session
        current_user: Authenticated user from token

    Returns:
        Success message

    Raises:
        HTTPException: If logout fails
    """
    client_ip = SessionManager.extract_client_ip(request)
    user_id = str(current_user.id)

    logger.log_info(
        {
            "event_type": "logout_attempt",
            "user_id": user_id,
            "client_ip": client_ip,
        }
    )

    try:
        # Get current session ID from token
        auth_header = request.headers.get("authorization")
        session_id = None

        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                payload = TokenManager.decode_token(token)
                session_id = payload.get("sid")
            except Exception as e:
                logger.log_warning(
                    {
                        "event_type": "logout_token_parse_failed",
                        "user_id": user_id,
                        "error": str(e),
                    }
                )

        # Terminate current session if identified
        if session_id:
            terminated = await SessionManager.terminate_session(
                db=db, session_id=uuid.UUID(session_id), reason="user_logout"
            )
            if terminated:
                logger.log_info(
                    {
                        "event_type": "session_terminated",
                        "user_id": user_id,
                        "session_id": session_id,
                    }
                )

        # Get and revoke refresh token
        refresh_token = request.cookies.get("refresh_token")
        refresh_token_revoked = False

        if refresh_token:
            refresh_token_record = await TokenManager.validate_refresh_token(
                db, refresh_token
            )
            if refresh_token_record:
                await TokenManager.revoke_refresh_token(db, refresh_token_record.id)
                refresh_token_revoked = True
                logger.log_info(
                    {
                        "event_type": "refresh_token_revoked",
                        "user_id": user_id,
                        "token_id": str(refresh_token_record.id),
                    }
                )

        # Clear refresh token cookie
        response.delete_cookie(
            key="refresh_token",
            httponly=True,
            secure=True,
            samesite="none",
        )


        logger.log_security_event(
            {
                "event_type": "logout_success",
                "user_id": user_id,
                "session_terminated": bool(session_id),
                "refresh_token_revoked": refresh_token_revoked,
                "cookie_cleared": True,
                "ip_address": client_ip,
            }
        )

        logger.log_info(
            {
                "event_type": "logout_success",
                "user_id": user_id,
                "session_id": session_id,
            }
        )

        return {
            "message": "Logged out successfully",
            "session_terminated": bool(session_id),
            "refresh_token_revoked": refresh_token_revoked,
        }

    except HTTPException:
        raise
    except Exception as e:

        logger.log_error(
            {
                "event_type": "logout_error",
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "ip_address": client_ip,
            }
        )

        logger.log_security_event(
            {
                "event_type": "logout_error",
                "reason": "unexpected_error",
                "error": str(e),
                "user_id": user_id,
                "ip_address": client_ip,
            }
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed due to internal error",
        )


@router.post("/create-staff")
async def create_staff_user(
    user_data: UserCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    user_service = UserService(db)
    try:

        user_data.roles = ["staff"]
        user = await user_service.create_user(user_data)
        return UserSchema.model_validate(user, from_attributes=True)

    except ValueError as e:
        # Handle validation errors
        logger.log_warning(
            {
                "event": "user_creation_failed",
                "reason": "validation_error",
                "error": str(e),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except Exception as e:
        # Log unexpected errors
        logger.log_error(
            {
                "event": "user_creation_error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the user",
        )


@router.patch("/{user_id}", response_model=UserSchema)
async def update_user(
    user_id: uuid.UUID,
    update_data: UserUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Update user account (Admin only).

    Args:
        user_id: User UUID to update
        update_data: User update data
        db: Database session
        current_user: Current authenticated admin user

    Returns:
        UserSchema: Updated user information

    Raises:
        HTTPException: If update fails or user not found
    """
    user_service = UserService(db)
    try:
        user = await user_service.update_user_account(user_id, update_data)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        logger.log_info(
            {
                "event": "user_updated",
                "user_id": str(user_id),
                "admin_id": str(current_user.id),
            }
        )

        return UserSchema.model_validate(user, from_attributes=True)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.log_error(
            {
                "event": "update_user_error",
                "user_id": str(user_id),
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating user",
        )


@router.get("", response_model=PaginatedResponse[UserSchema])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
    pagination: PaginationParams = Depends(get_pagination_params),
    is_active: bool = None,
    search: str = None,
):
    """
    Get paginated list of users (Admin only).

    Args:
        db: Database session
        current_user: Current authenticated admin user
        pagination: Pagination parameters (page, page_size)
        is_active: Filter by active status (optional)
        search: Search in username, email, or full_name (optional)

    Returns:
        PaginatedResponse: Paginated list of users with metadata
    """
    try:
        # Build query with filters
        query = select(User).where(User.is_deleted == False)

        if is_active is not None:
            query = query.where(User.is_active == is_active)

        if search:
            search_term = f"%{search}%"
            query = query.where(
                (User.username.ilike(search_term))
                | (User.email.ilike(search_term))
                | (User.full_name.ilike(search_term))
            )

        query = query.order_by(User.created_at.desc())

        # Paginate
        result = await Paginator.paginate(
            db=db, query=query, params=pagination, schema=UserSchema
        )

        logger.log_info(
            {
                "event": "users_listed",
                "admin_id": str(current_user.id),
                "page": pagination.page,
                "total_items": result.page_info.total_items,
            }
        )

        return result

    except Exception as e:
        logger.log_error(
            {
                "event": "list_users_error",
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving users",
        )


@router.get("/{user_id}", response_model=UserSchema)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get user by ID.

    Args:
        user_id: User UUID
        db: Database session
        current_user: Current authenticated user

    Returns:
        UserSchema: User information

    Raises:
        HTTPException: If user not found or no permission
    """
    # Users can only view their own profile unless they're admin
    if current_user.id != user_id:
        if not current_user.has_role("admin") and not current_user.has_role(
            "superadmin"
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this user",
            )

    user_service = UserService(db)
    try:
        user = await user_service.get_user_by_id(user_id)
        print(f"User Found {user}")
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        return UserSchema.model_validate(user, from_attributes=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error(
            {
                "event": "get_user_error",
                "user_id": str(user_id),
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving user",
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Soft delete user (Admin only).

    Args:
        user_id: User UUID to delete
        db: Database session
        current_user: Current authenticated admin user

    Raises:
        HTTPException: If delete fails or user not found
    """
    # Prevent deleting yourself
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    user_service = UserService(db)
    try:
        await user_service.delete_user(user_id)

        logger.log_security_event(
            {
                "event_type": "user_deleted",
                "user_id": str(user_id),
                "admin_id": str(current_user.id),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error(
            {
                "event": "delete_user_error",
                "user_id": str(user_id),
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting user",
        )
