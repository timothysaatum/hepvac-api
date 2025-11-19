from datetime import datetime, timezone
from typing import Optional, Tuple
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.rbac import Role
from app.models.user_model import User
from app.core.security import (
    handle_failed_login,
    handle_successful_login,
    verify_password,
    needs_rehash,
    get_password_hash,
)
from app.config.config import settings
from app.core.utils import logger

ENVIRONMENT = settings.ENVIRONMENT
IS_PRODUCTION = ENVIRONMENT.lower() in ["production", "prod"]
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS


async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
    ip_address: str = None,
    user_agent: str = None,
) -> Tuple[bool, Optional[User], Optional[str]]:
    """
    Authenticate user with enhanced security features.

    Args:
        db: Database session
        username: User's username
        password: User's password (plain text)
        ip_address: Client IP address
        user_agent: Client user agent string

    Returns:
        Tuple of (success, user, error_message)
    """
    try:
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.roles).selectinload(Role.permissions),
                selectinload(User.refresh_tokens),
                selectinload(User.user_sessions),
                selectinload(User.facility),
                selectinload(User.managed_facility),
            )
            .where(User.username == username, User.is_deleted == False)
        )

        user = result.unique().scalar_one_or_none()

        if not user:
            logger.log_security_event(
                {
                    "event_type": "authentication_failed",
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "reason": f"user_not_found => {username}",
                }
            )
            return False, None, "Invalid username or password"

        # Check if user can login
        can_login, login_error = user.can_login()
        if not can_login:
            await handle_failed_login(db, user, ip_address, user_agent)
            return False, user, login_error

        # Verify password (note: using 'password' not 'password_hash')
        if not verify_password(password, user.password):
            await handle_failed_login(db, user, ip_address, user_agent)
            return False, user, "Invalid username or password"

        # Check if password hash needs updating
        if needs_rehash(user.password):
            try:
                user.password = get_password_hash(password)
                logger.log_info(
                    {
                        "event_type": "password_rehashed",
                        "user_id": str(user.id),
                        "reason": "using_updated_parameters",
                    }
                )
            except Exception as e:
                logger.log_warning(
                    {
                        "event_type": "password_rehash_failed",
                        "user_id": str(user.id),
                        "error": str(e),
                    }
                )

        # Handle successful login
        await handle_successful_login(db, user, ip_address, user_agent)
        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()

        # Refresh to ensure all relationships are loaded
        await db.refresh(user)
        return True, user, None

    except SQLAlchemyError as e:
        logger.log_error(
            {
                "event_type": "authentication_db_error",
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        return False, None, "Authentication failed due to database error"

    except Exception as e:
        logger.log_error(
            {
                "event_type": "authentication_error",
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        return False, None, "Authentication failed"


# def set_refresh_token_cookie(
#     response: Response, refresh_token: str, request: Request = None
# ):
#     """
#     Set refresh token cookie with proper security settings.

#     Args:
#         response: FastAPI response object
#         refresh_token: The refresh token to set
#         request: FastAPI request object (optional, for scheme detection)
#     """
#     logger.log_debug("Setting refresh token cookie")

#     # Determine if we should use secure cookies
#     is_secure = IS_PRODUCTION
#     if request:
#         is_secure = request.url.scheme == "https" or IS_PRODUCTION

#     # Set the cookie with appropriate security settings
#     response.set_cookie(
#         key="refresh_token",
#         value=refresh_token,
#         httponly=True,
#         secure=is_secure,
#         samesite="none" if is_secure else "lax",
#         max_age=60 * 60 * 24 * REFRESH_TOKEN_EXPIRE_DAYS,
#         domain=None,
#     )


#     logger.log_info(
#         {
#             "event_type": "refresh_token_cookie_set",
#             "secure": is_secure,
#             "samesite": "none" if is_secure else "lax",
#         }
#     )
def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
    request: Request = None,
) -> None:
    """
    Set refresh token as HTTP-only cookie.

    Args:
        response: FastAPI response object
        refresh_token: Refresh token to store
        request: FastAPI request object (optional)
    """
    # Determine if we're in a secure context
    is_secure = False
    if request:
        # Check if request came over HTTPS
        is_secure = request.url.scheme == "https"
        # Also check X-Forwarded-Proto header (for proxies)
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto == "https":
            is_secure = True

    # Set cookie with appropriate security settings
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_secure,  # Use secure flag if HTTPS
        samesite="lax" if is_secure else "lax",  # Use 'lax' for better compatibility
        max_age=30 * 24 * 60 * 60,  # 30 days
        path="/",
    )

    logger.log_info(
        {
            "event": "refresh_token_cookie_set",
            "secure": is_secure,
            "samesite": "lax",
        }
    )
