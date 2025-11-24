import uuid
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, HashingError, VerificationError
from jose import ExpiredSignatureError, JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, Request, status, Security
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db
from app.core.sessions import SessionManager, TokenManager
from app.core.utils import logger
from app.models.rbac import Role
from app.models.user_model import User
from app.config.config import settings
from sqlalchemy.orm import selectinload

from app.schemas.user_schemas import UserLoginSchema


MAX_LOGIN_ATTEMPTS = settings.MAX_LOGIN_ATTEMPTS
LOCKOUT_DURATION_MINUTES = settings.LOGIN_ATTEMPT_WINDOW_MINUTES
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM


ph = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16
)

security = HTTPBearer(
    scheme_name="Bearer Token", description="Enter your JWT token", auto_error=True
)


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using Argon2"""
    try:
        return ph.hash(password)
    except HashingError as e:
        logger.log_error({"event_type": "password_hashing_failed", "error": str(e)})
        raise HTTPException(status_code=500, detail="Password hashing failed") from e


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 hashed password"""
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False
    except VerificationError as e:
        logger.log_error(
            {
                "event_type": "password_verification_error",
                "error": str(e),
            }
        )
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Check if password hash needs to be updated with current parameters"""
    try:
        return ph.check_needs_rehash(hashed_password)
    except Exception:
        return True


async def handle_failed_login(
    db: AsyncSession, user: User, ip_address: str = None, user_agent: str = None
) -> None:
    """Handle failed login attempt with account locking"""
    try:
        user.update_login_attempts()

        if user.has_exhausted_max_login_attempts:
            user.suspend_user()
            
        await db.commit()

        logger.log_security_event(
            {
                "event_type": "failed_login_attempt",
                "user_id": str(user.id),
                "ip_address": ip_address,
                "user_agent": user_agent,
                "failed_attempts": user.login_attempts,
                "account_locked": user.is_suspended,
            }
        )

        logger.log_warning(
            {
                "event_type": "failed_login_recorded",
                "user_id": str(user.id),
                "failed_attempts": user.login_attempts,
                "account_locked": user.is_suspended,
            }
        )

    except Exception as e:
        logger.log_error(
            {
                "event_type": "failed_login_handling_error",
                "user_id": str(user.id),
                "error": str(e),
            }
        )
        await db.rollback()


async def handle_successful_login(
    db: AsyncSession, user: User, ip_address: str = None, user_agent: str = None
) -> None:
    """Handle successful login with security logging"""
    try:
        user.reset_login_attempts()
        await db.commit()

        logger.log_security_event(
            {
                "event_type": "successful_login",
                "user_id": str(user.id),
                "ip_address": ip_address,
                "user_agent": user_agent,
                "last_login": (
                    user.last_login_at.isoformat() if user.last_login_at else None
                ),
                "failed_attempts_reset": True,
            }
        )

        logger.log_info(
            {
                "event_type": "successful_login_recorded",
                "user_id": str(user.id),
                "last_login": (
                    user.last_login_at.isoformat() if user.last_login_at else None
                ),
            }
        )

    except Exception as e:
        logger.log_error(
            {
                "event_type": "successful_login_handling_error",
                "user_id": str(user.id),
                "error": str(e),
            }
        )
        await db.rollback()


def verify_token_and_extract_data(token: str) -> dict:
    """Verify token and extract user data safely"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "email_verification":
            raise ValueError("Invalid token type")

        return {
            "email": payload.get("sub"),
            "role": payload.get("role"),
        }
    except ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Token has expired")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> User:
    """
    Get current user with enhanced session validation.

    Args:
        credentials: HTTP Authorization credentials containing the Bearer token
        db: Database session
        request: FastAPI request object

    Returns:
        User: Authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials  # Extract token from credentials

    try:
        payload = TokenManager.decode_token(token)
        user_id = uuid.UUID(payload.get("sub"))
        session_id = payload.get("sid")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token does not contain user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        result = await db.execute(
            select(User)
            .options(
                selectinload(User.roles).selectinload(Role.permissions),
                selectinload(User.facility),
                selectinload(User.managed_facility),
            )
            .where(User.id == user_id, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user.is_suspended:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is temporarily locked",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate session if session ID is in token and request is available
        if session_id and request:
            session = await SessionManager.validate_session(
                db, uuid.UUID(session_id), request
            )
            if not session:
                logger.log_warning(
                    {
                        "event_type": "invalid_session",
                        "user_id": str(user.id),
                        "session_id": session_id,
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid session",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return user

    except (JWTError, ValueError) as e:
        logger.log_warning({"event_type": "invalid_auth_credentials", "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def super_admin_login(login_data: UserLoginSchema, request: Request):
    """Log super admin login attempts for security auditing."""
    user_name = settings.SUPER_ADMIN_USER_NAME
    password_hash = get_password_hash(settings.SUPER_ADMIN_PASSWORD_HASH)
    
    login_password = login_data.password

    if login_data.username != user_name or not verify_password(login_password, password_hash):
        logger.log_security_event(
            {
                "event_type": "super_admin_failed_login",
                "username_attempted": login_data.username,
                "ip_address": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent") if request else None,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid super admin credentials",
        )
    logger.log_security_event(
        {
            "event_type": "super_admin_successful_login",
            "username": login_data.username,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent") if request else None,
        }
    )
    return True


def require_super_admin(
    credentials: HTTPAuthorizationCredentials = Security(security),
    request: Request = None,
) -> None:
    """
    Dependency to require super admin access.

    Args:
        credentials: HTTP Authorization credentials containing the Bearer token
        request: FastAPI request object

    Raises:
        HTTPException: If the user is not a super admin
    """
    token = credentials.credentials  # Extract token from credentials

    try:
        payload = TokenManager.decode_token(token)

        if payload.get("type") != "superadmin":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid super admin token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    except (JWTError, ValueError) as e:
        logger.log_warning({"event_type": "invalid_super_admin_credentials", "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )