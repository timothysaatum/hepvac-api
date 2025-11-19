import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, Request, status
from app.api.dependencies import get_db
from app.core.security import get_current_user
from app.core.sessions import SessionManager, TokenManager
from app.models.user_model import User
from app.core.utils import logger


def require_permission(*perms: str, validate_session: bool = True):
    """
    Enhanced dependency factory to enforce permissions with optional session validation.

    Args:
        *perms: Required permissions (user needs at least one)
        validate_session: Whether to validate the user's session (default: True)

    Usage:
        current_user: User = Depends(require_permission("perm1", "perm2"))
        current_user: User = Depends(require_permission("admin", validate_session=False))
    """

    async def checker(
        current_user: User = Depends(get_current_user),
        request: Request = None,
        db: AsyncSession = Depends(get_db),
    ):
        # Enhanced logging
        logger.debug(
            "Permission check initiated",
            extra={
                "event_type": "permission_check_started",
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "required_permissions": list(perms),
                "validate_session": validate_session,
            },
        )

        # Get user's actual permissions
        user_permissions = [
            perm.name for role in current_user.roles for perm in role.permissions
        ]

        logger.debug(
            "User permissions retrieved",
            extra={
                "event_type": "user_permissions_retrieved",
                "user_id": str(current_user.id),
                "user_permissions": user_permissions,
            },
        )

        # Check if user has any of the required permissions
        has_permission = any(current_user.has_permission(perm) for perm in perms)

        if not has_permission:
            # Log security event for unauthorized access attempt
            logger.log_security_event(
                {
                    "event_type":"unauthorized_access_attempt",
                    "user_id":str(current_user.id),
                    "ip_address":(
                    getattr(request.client, "host", "unknown")
                    if request and request.client
                    else "unknown"
                    ),
                    "user_agent":(
                    request.headers.get("user-agent", "unknown")
                    if request
                    else "unknown"
                    ),
                }
            )

            logger.log_warning(
                {
                    "event_type": "access_denied_permissions",
                    "user_id": str(current_user.id),
                    "required_permissions": list(perms),
                    "user_permissions": user_permissions,
                },
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires at least one of these permissions: {', '.join(perms)}",
            )

        # Optional session validation for high-security operations
        if validate_session and request:
            session_valid = await validate_user_session(
                db=db, current_user=current_user, request=request
            )

            if not session_valid:
                logger.log_security_event(
                    {
                        "required_permissions": list(perms),
                        "session_validation_failed": True,
                        "event_type":"invalid_session_access_attempt",
                        "user_id":str(current_user.id),
                        "ip_address":(
                            getattr(request.client, "host", "unknown")
                            if request.client
                            else "unknown"
                        ),
                    },
                )

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session validation failed. Please login again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        logger.info(
            "Access granted - permission check passed",
            extra={
                "event_type": "access_granted",
                "user_id": str(current_user.id),
                "granted_permissions": [
                    perm for perm in perms if current_user.has_permission(perm)
                ],
                "session_validated": validate_session,
            },
        )

        return current_user

    return checker


def require_role(*roles: str, validate_session: bool = True):
    """
    Enhanced dependency factory to enforce roles with optional session validation.

    Args:
        *roles: Required roles (user needs at least one)
        validate_session: Whether to validate the user's session (default: True)

    Usage:
        current_user: User = Depends(require_role("admin", "manager"))
        current_user: User = Depends(require_role("staff", validate_session=False))
    """

    async def checker(
        current_user: User = Depends(get_current_user),
        request: Request = None,
        db: AsyncSession = Depends(get_db),
    ):
        logger.debug(
            "Role check initiated",
            extra={
                "event_type": "role_check_started",
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "required_roles": list(roles),
                "validate_session": validate_session,
            },
        )

        # Get user's actual roles
        user_roles = [role.name for role in current_user.roles]

        logger.debug(
            "User roles retrieved",
            extra={
                "event_type": "user_roles_retrieved",
                "user_id": str(current_user.id),
                "user_roles": user_roles,
            },
        )

        # Check if user has any of the required roles
        has_role = any(current_user.has_role(role) for role in roles)

        if not has_role:
            # Log security event for unauthorized access attempt
            logger.log_security_event(
                {
                    "required_roles": list(roles),
                    "user_roles": user_roles,
                    "user_email": current_user.email,
                    "event_type":"unauthorized_role_access_attempt",
                    "user_id":str(current_user.id),
                    "ip_address":(
                        getattr(request.client, "host", "unknown")
                        if request and request.client
                        else "unknown"
                    ),
                    "user_agent":(
                        request.headers.get("user-agent", "unknown")
                        if request
                        else "unknown"
                    )
                }
            )

            logger.warning(
                "Access denied - insufficient roles",
                extra={
                    "event_type": "access_denied_roles",
                    "user_id": str(current_user.id),
                    "required_roles": list(roles),
                    "user_roles": user_roles,
                },
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires at least one of these roles: {', '.join(roles)}",
            )

        # Optional session validation for high-security operations
        if validate_session and request:
            session_valid = await validate_user_session(
                db=db, current_user=current_user, request=request
            )

            if not session_valid:
                logger.log_security_event(
                    {
                        "required_roles": list(roles),
                        "session_validation_failed": True,
                        "event_type":"invalid_session_access_attempt",
                        "user_id":str(current_user.id),
                        "ip_address":(
                            getattr(request.client, "host", "unknown")
                            if request.client
                            else "unknown"
                        )
                    }
                )

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session validation failed. Please login again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        logger.log_info(
            {
                "event_type": "access_granted_role",
                "user_id": str(current_user.id),
                "granted_roles": [
                    role for role in roles if current_user.has_role(role)
                ],
                "session_validated": validate_session,
            }
        )

        return current_user

    return checker


async def validate_user_session(
    db: AsyncSession, current_user: User, request: Request
) -> bool:
    """
    Validate user session for high-security operations.

    Args:
        db: Database session
        current_user: Current authenticated user
        request: FastAPI request object

    Returns:
        bool: True if session is valid, False otherwise
    """
    try:
        # Extract session information from request

        authorization_header = request.headers.get("authorization")
        if not authorization_header or not authorization_header.startswith("Bearer "):
            logger.log_warning(
                {
                    "event_type": "session_validation_failed",
                    "user_id": str(current_user.id),
                    "reason": "missing_auth_header",
                },
            )
            return False
        token = authorization_header.split(" ")[1]

        payload = TokenManager.decode_token(token)

        if not payload:
            logger.warning(
                "Session validation failed - invalid token",
                extra={
                    "event_type": "session_validation_failed",
                    "user_id": str(current_user.id),
                    "reason": "invalid_token",
                },
            )
            return False

        # Use SessionManager to validate the session
        session_manager = SessionManager()
        session_uuid = uuid.UUID(payload.get("sid"))
        is_valid = await session_manager.validate_session(
            db=db, session_id=session_uuid, request=request
        )

        if not is_valid:
            logger.log_warning(
                {
                    "event_type": "session_validation_failed",
                    "user_id": str(current_user.id),
                    "reason": "invalid_session",
                }
            )
            return False

        logger.log_debug(
            {
                "event_type": "session_validation_success",
                "user_id": str(current_user.id),
            },
        )

        return True

    except Exception as e:
        logger.log_error(
            {
                "event_type": "session_validation_error",
                "user_id": str(current_user.id),
                "error": str(e),
            },
        )
        return False


def require_admin(validate_session: bool = True):
    """
    Dependency to require admin role with optional session validation.

    Args:
        validate_session: Whether to validate the user's session (default: True)

    Usage:
        current_user: User = Depends(require_admin())
        current_user: User = Depends(require_admin(validate_session=False))
    """

    async def admin_checker(
        current_user: User = Depends(get_current_user),
        request: Request = None,
        db: AsyncSession = Depends(get_db),
    ):
        logger.log_debug(
            {
                "event_type": "admin_check_started",
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "validate_session": validate_session,
            },
        )

        # Check if user has admin or superadmin role
        if not current_user.has_role("admin") and not current_user.has_role(
            "superadmin"
        ):
            logger.log_security_event(
                {
                    "event_type": "unauthorized_admin_access_attempt",
                    "user_id": str(current_user.id),
                    "user_email": current_user.email,
                    "user_roles": [role.name for role in current_user.roles],
                    "ip_address": (
                        getattr(request.client, "host", "unknown")
                        if request and request.client
                        else "unknown"
                    ),
                    "user_agent": (
                        request.headers.get("user-agent", "unknown")
                        if request
                        else "unknown"
                    ),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
            )

        # Optional session validation for high-security operations
        if validate_session and request:
            session_valid = await validate_user_session(
                db=db, current_user=current_user, request=request
            )
            if not session_valid:
                logger.log_security_event(
                    {
                        "event_type": "invalid_session_admin_access_attempt",
                        "user_id": str(current_user.id),
                        "session_validation_failed": True,
                        "ip_address": (
                            getattr(request.client, "host", "unknown")
                            if request.client
                            else "unknown"
                        ),
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session validation failed. Please login again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        logger.log_info(
            {
                "event_type": "admin_access_granted",
                "user_id": str(current_user.id),
                "session_validated": validate_session,
            },
        )
        return current_user

    return admin_checker


def require_superadmin(validate_session: bool = True):
    """
    Dependency to require superadmin role with optional session validation.

    Args:
        validate_session: Whether to validate the user's session (default: True)

    Usage:
        current_user: User = Depends(require_superadmin())
        current_user: User = Depends(require_superadmin(validate_session=False))
    """

    async def superadmin_checker(
        current_user: User = Depends(get_current_user),
        request: Request = None,
        db: AsyncSession = Depends(get_db),
    ):
        logger.log_debug(
            {
                "event_type": "superadmin_check_started",
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "validate_session": validate_session,
            },
        )

        # Check if user has superadmin role
        if not current_user.has_role("superadmin"):
            logger.log_security_event(
                {
                    "event_type": "unauthorized_superadmin_access_attempt",
                    "user_id": str(current_user.id),
                    "user_email": current_user.email,
                    "user_roles": [role.name for role in current_user.roles],
                    "ip_address": (
                        getattr(request.client, "host", "unknown")
                        if request and request.client
                        else "unknown"
                    ),
                    "user_agent": (
                        request.headers.get("user-agent", "unknown")
                        if request
                        else "unknown"
                    ),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superadmin privileges required",
            )

        # Optional session validation for high-security operations
        if validate_session and request:
            session_valid = await validate_user_session(
                db=db, current_user=current_user, request=request
            )
            if not session_valid:
                logger.log_security_event(
                    {
                        "event_type": "invalid_session_superadmin_access_attempt",
                        "user_id": str(current_user.id),
                        "session_validation_failed": True,
                        "ip_address": (
                            getattr(request.client, "host", "unknown")
                            if request.client
                            else "unknown"
                        ),
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session validation failed. Please login again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        logger.log_info(
            {
                "event_type": "superadmin_access_granted",
                "user_id": str(current_user.id),
                "session_validated": validate_session,
            },
        )
        return current_user

    return superadmin_checker


def require_staff(validate_session: bool = True):
    """
    Dependency to require staff-level access with optional session validation.

    Args:
        validate_session: Whether to validate the user's session (default: True)

    Usage:
        current_user: User = Depends(require_staff())
        current_user: User = Depends(require_staff(validate_session=False))
    """

    async def staff_checker(
        current_user: User = Depends(get_current_user),
        request: Request = None,
        db: AsyncSession = Depends(get_db),
    ):
        logger.log_debug(
            {
                "event_type": "staff_check_started",
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "validate_session": validate_session,
            },
        )

        # Check if user has any staff-level role
        staff_roles = ["admin", "staff"]
        has_staff_role = any(current_user.has_role(role) for role in staff_roles)

        if not has_staff_role:
            logger.log_security_event(
                {
                    "event_type": "unauthorized_staff_access_attempt",
                    "user_id": str(current_user.id),
                    "user_email": current_user.email,
                    "user_roles": [role.name for role in current_user.roles],
                    "required_roles": staff_roles,
                    "ip_address": (
                        getattr(request.client, "host", "unknown")
                        if request and request.client
                        else "unknown"
                    ),
                    "user_agent": (
                        request.headers.get("user-agent", "unknown")
                        if request
                        else "unknown"
                    ),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff privileges required",
            )

        # Optional session validation for high-security operations
        if validate_session and request:
            session_valid = await validate_user_session(
                db=db, current_user=current_user, request=request
            )
            if not session_valid:
                logger.log_security_event(
                    {
                        "event_type": "invalid_session_staff_access_attempt",
                        "user_id": str(current_user.id),
                        "session_validation_failed": True,
                        "ip_address": (
                            getattr(request.client, "host", "unknown")
                            if request.client
                            else "unknown"
                        ),
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session validation failed. Please login again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        logger.log_info(
            {
                "event_type": "staff_access_granted",
                "user_id": str(current_user.id),
                "session_validated": validate_session,
            },
        )
        return current_user

    return staff_checker


def require_authenticated(validate_session: bool = False):
    """
    Basic authentication requirement without specific permissions or roles.

    Args:
        validate_session: Whether to validate the user's session (default: False)

    Usage:
        current_user: User = Depends(require_authenticated())
        current_user: User = Depends(require_authenticated(validate_session=True))
    """

    async def checker(
        current_user: User = Depends(get_current_user),
        request: Request = None,
        db: AsyncSession = Depends(get_db),
    ):
        logger.log_debug(
            {
                "event_type": "auth_check_started",
                "user_id": str(current_user.id),
                "user_email": current_user.email,
                "validate_session": validate_session,
            },
        )

        # Optional session validation
        if validate_session and request:
            session_valid = await validate_user_session(
                db=db, current_user=current_user, request=request
            )

            if not session_valid:
                logger.log_security_event(
                    {
                        "session_validation_failed": True,
                        "event_type": "invalid_session_auth_attempt",
                        "user_id": str(current_user.id),
                        "ip_address": (
                            getattr(request.client, "host", "unknown")
                            if request.client
                            else "unknown"
                        ),
                    }
                )

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session validation failed. Please login again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        logger.log_debug(
            {
                "event_type": "auth_check_passed",
                "user_id": str(current_user.id),
                "session_validated": validate_session,
            },
        )

        return current_user

    return checker


def require_staff_or_admin():
    async def checker(user=Depends(get_current_user)):
        role_names = {role.name.lower() for role in user.roles}

        if "staff" not in role_names and "admin" not in role_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or staff access required",
            )

        return user

    return checker
