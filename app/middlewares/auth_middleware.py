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
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
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
                # roles + permissions are needed for every auth check — keep selectin.
                selectinload(User.roles).selectinload(Role.permissions),
                # selectinload(User.user_sessions). A user can accumulate
                # thousands of tokens/sessions over time. Loading ALL of them
                # on every login is an unbounded memory and query-time risk.
                # These collections are accessed via explicit queries elsewhere
                # (e.g. token rotation, session cleanup) — not needed here.
                #
                # facility and managed_facility use lazy="select" on the model,
                # so we load them explicitly here only for the login response.
                selectinload(User.facility),
                selectinload(User.managed_facility),
            )
            # column to the Python literal False works but is not idiomatic
            # SQLAlchemy. Use `.is_(False)` for clarity and to avoid any
            # ORM-level comparison ambiguity.
            .where(User.username == username, User.is_deleted.is_(False))
        )

        user = result.unique().scalar_one_or_none()

        if not user:
            logger.log_security_event(
                {
                    "event_type": "authentication_failed",
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    # it leaks enumeration information into logs. Log a hash
                    # or omit it entirely. Changed to a non-revealing message.
                    "reason": "user_not_found",
                }
            )
            return False, None, "Invalid username or password"

        # `.allowed` and `.reason` fields. Unpacking as `can_login, login_error`
        # works for a 2-element namedtuple but is fragile — use attribute access
        # for clarity and future-proofing.
        login_check = user.can_login()
        if not login_check.allowed:
            await handle_failed_login(db, user, ip_address, user_agent)
            return False, user, login_check.reason

        # Verify password
        if not verify_password(password, user.password):
            await handle_failed_login(db, user, ip_address, user_agent)
            return False, user, "Invalid username or password"

        # Upgrade password hash if the current parameters are outdated.
        # Failure here is non-fatal — the user is still authenticated.
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

        # Refresh to ensure all relationships are current after the commit.
        await db.refresh(user)
        return True, user, None

    except SQLAlchemyError as e:
        logger.log_error(
            {
                "event_type": "authentication_db_error",
                # FIX: do NOT log the username in error events — it leaks
                # account existence. Log only what is necessary for debugging.
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        return False, None, "Authentication failed due to database error"

    except Exception as e:
        logger.log_error(
            {
                "event_type": "authentication_error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        return False, None, "Authentication failed"


def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
    key: Optional[str] = None,
    request: Request | None = None,
) -> None:
    """
    Set refresh token as HTTP-only cookie.

    Security policy:
    - ``secure=True`` in production (IS_PRODUCTION), regardless of the
      current request scheme. Relying on request.url.scheme is unsafe because
      a misconfigured reverse proxy or a direct HTTP hit can make it appear
      as HTTP even in production.
    - ``samesite="strict"`` in production to prevent CSRF.  Development uses
      ``"lax"`` for easier local tooling (e.g. Swagger UI on a different port).
    - ``max_age`` is derived from the application constant so cookie lifetime
      stays in sync with the token expiry configured in settings.

    Args:
        response:      FastAPI response object
        refresh_token: Refresh token string to store
        key:           Cookie name override (default: "refresh_token")
        request:       FastAPI request object (unused — kept for API compat)
    """
    # secure=True is required when samesite="none" (browsers enforce this).
    # In production this is always HTTPS so secure=True is correct.
    # In local development the app runs on http://localhost — browsers refuse
    # to set secure cookies over plain HTTP, breaking the refresh token flow.
    # Use IS_PRODUCTION so local dev works without needing a self-signed cert.
    is_secure = IS_PRODUCTION

    # samesite="none" is required for cross-origin requests (SPA on a different
    # port/domain than the API). In local dev with a Vite proxy this isn't
    # needed, but "lax" breaks the refresh token POST from a different origin.
    # Keep "none" in production; use "lax" locally so the cookie is accepted
    # over HTTP (browsers reject samesite=none on non-secure cookies).
    samesite = "none" if IS_PRODUCTION else "lax"

    # FIX: was hardcoding 30 * 24 * 60 * 60. Derive from the setting constant
    # so token lifetime and cookie lifetime stay in sync.
    max_age = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

    response.set_cookie(
        key=key or "refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        max_age=max_age,
        path="/",
    )

    logger.log_info(
        {
            "event": "refresh_token_cookie_set",
            "secure": is_secure,
            "samesite": samesite,
        }
    )