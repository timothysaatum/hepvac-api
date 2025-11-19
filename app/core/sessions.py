import hashlib
import ipaddress
import json
from typing import Dict, Optional, Union
import uuid
from fastapi import Request
from jose import JWTError, jwt
from app.models.user_model import UserSession
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta, timezone
from uuid import UUID
from uuid import uuid4
from sqlalchemy.orm import selectinload
from app.core.utils import logger
from app.config.config import settings

ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
MAX_ACTIVE_SESSIONS = settings.MAX_ACTIVE_SESSIONS
MAX_LOGIN_ATTEMPTS = settings.MAX_LOGIN_ATTEMPTS
LOGIN_ATTEMPT_WINDOW_MINUTES = settings.LOGIN_ATTEMPT_WINDOW_MINUTES
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM


class SessionManager:

    @staticmethod
    def normalize_header(header_value: str) -> str:
        """Normalize header values by removing extra whitespace and converting to lowercase"""
        if not header_value:
            return ""
        return " ".join(header_value.strip().lower().split())

    @staticmethod
    def extract_client_ip(request: Request) -> str:
        """Extract client IP with comprehensive proxy support"""
        # Check for various proxy headers in order of preference
        ip_headers = [
            "cf-connecting-ip",  # Cloudflare
            "x-real-ip",  # Nginx
            "x-forwarded-for",  # Standard proxy header
            "x-client-ip",  # Alternative
            "x-cluster-client-ip",  # Kubernetes
        ]

        for header in ip_headers:
            ip_value = request.headers.get(header)
            if ip_value:
                # Handle comma-separated IPs (take the first one)
                first_ip = ip_value.split(",")[0].strip()
                # Validate IP format
                try:
                    ipaddress.ip_address(first_ip)
                    return first_ip
                except ValueError:
                    continue

        # Fallback to request client
        return str(request.client.host) if request.client else "unknown"

    @staticmethod
    def parse_user_agent(user_agent: str) -> dict:
        """Simple user agent parsing without external dependencies"""
        if not user_agent:
            return {
                "browser": "unknown",
                "os": "unknown",
                "device_type": "unknown",
                "is_mobile": False,
                "is_bot": True,
            }

        ua_lower = user_agent.lower()

        # Browser detection
        browsers = {
            "chrome": ["chrome", "crios"],
            "firefox": ["firefox", "fxios"],
            "safari": ["safari"],
            "edge": ["edge", "edg"],
            "opera": ["opera", "opr"],
            "internet_explorer": ["trident", "msie"],
        }

        browser = "unknown"
        for browser_name, patterns in browsers.items():
            if any(pattern in ua_lower for pattern in patterns):
                browser = browser_name
                break

        # OS detection
        operating_systems = {
            "windows": ["windows", "win32", "win64"],
            "macos": ["mac os", "darwin"],
            "linux": ["linux", "ubuntu", "debian"],
            "android": ["android"],
            "ios": ["iphone", "ipad", "ipod"],
        }

        os = "unknown"
        for os_name, patterns in operating_systems.items():
            if any(pattern in ua_lower for pattern in patterns):
                os = os_name
                break

        # Device type detection
        is_mobile = any(term in ua_lower for term in ["mobile", "android", "iphone"])
        is_tablet = any(term in ua_lower for term in ["tablet", "ipad"])

        if is_tablet:
            device_type = "tablet"
        elif is_mobile:
            device_type = "mobile"
        else:
            device_type = "desktop"

        # Bot detection
        bot_indicators = [
            "bot",
            "crawler",
            "spider",
            "scraper",
            "curl",
            "wget",
            "python",
            "java",
            "axios",
            "node",
            "phantom",
            "selenium",
            "headless",
            "automated",
            "monitor",
            "test",
        ]
        is_bot = any(indicator in ua_lower for indicator in bot_indicators)

        return {
            "browser": browser,
            "os": os,
            "device_type": device_type,
            "is_mobile": is_mobile,
            "is_tablet": is_tablet,
            "is_bot": is_bot,
        }

    @staticmethod
    def calculate_device_risk_score(device_data: dict) -> tuple[int, list]:
        """Calculate risk score based on device characteristics"""
        risk_score = 0
        risk_factors = []

        # Missing or suspicious user agent
        if not device_data.get("user_agent") or device_data.get("parsed_ua", {}).get(
            "is_bot"
        ):
            risk_score += 40
            risk_factors.append("suspicious_user_agent")

        # Missing standard browser headers
        if not device_data.get("accept_language"):
            risk_score += 25
            risk_factors.append("missing_accept_language")

        if not device_data.get("accept_encoding"):
            risk_score += 20
            risk_factors.append("missing_accept_encoding")

        # Check for automation tools in user agent
        user_agent = device_data.get("user_agent", "").lower()
        automation_indicators = [
            "selenium",
            "webdriver",
            "phantom",
            "headless",
            "automated",
        ]
        if any(indicator in user_agent for indicator in automation_indicators):
            risk_score += 50
            risk_factors.append("automation_detected")

        # Suspicious IP patterns
        client_ip = device_data.get("client_ip", "")
        if client_ip in ["unknown", "127.0.0.1", "localhost"] or not client_ip:
            risk_score += 15
            risk_factors.append("suspicious_ip")

        # Check for common VPN/proxy patterns
        vpn_indicators = ["vpn", "proxy", "tor"]
        headers_str = " ".join(
            [
                device_data.get("user_agent", ""),
                device_data.get("accept_language", ""),
                device_data.get("accept_encoding", ""),
            ]
        ).lower()

        if any(indicator in headers_str for indicator in vpn_indicators):
            risk_score += 30
            risk_factors.append("proxy_detected")

        return min(risk_score, 100), risk_factors

    @staticmethod
    async def create_session(
        db: AsyncSession,
        user_id: UUID,
        request: Request,
        login_method: str = "password",
    ) -> UserSession:
        """Create a new user session with enhanced tracking"""

        # Extract device information
        device_info = SessionManager.extract_device_info(request)

        # Create session record
        session = UserSession(
            user_id=user_id,
            session_token=str(uuid4()),
            device_fingerprint=device_info.get("fingerprint"),
            user_agent=device_info.get("user_agent"),
            user_agent_hash=hashlib.sha256(
                device_info.get("user_agent", "").encode()
            ).hexdigest()[:16],
            ip_address=device_info.get("client_ip"),
            login_method=login_method,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        db.add(session)
        await db.commit()
        await db.refresh(session)

        logger.log_info(
            {
                "event_type": "session_created",
                "user_id": str(user_id),
                "session_id": str(session.id),
                "ip_address": device_info.get("client_ip"),
            }
        )

        return session

    @staticmethod
    async def validate_session(
        db: AsyncSession, session_id: UUID, request: Request
    ) -> Optional[UserSession]:
        """Validate session and update activity"""

        result = await db.execute(
            select(UserSession)
            .options(selectinload(UserSession.user))
            .where(UserSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        print(session.is_valid)
        if not session or not session.is_valid:
            return None

        # Update activity and perform security checks
        current_ip = (
            getattr(request.client, "host", "unknown") if request.client else "unknown"
        )

        session.update_activity(current_ip)
        # Security monitoring
        if session.ip_address != current_ip:
            logger.log_security_event(
                {
                    "event_type": "ip_change_detected",
                    "user_id": str(session.user_id),
                    "ip_address": current_ip,
                    "session_id": str(session.id),
                    "previous_ip": session.ip_address,
                    "new_ip": current_ip,
                }
            )
            session.mark_suspicious("ip_change")

        await db.commit()
        return session

    @staticmethod
    async def terminate_session(
        db: AsyncSession, session_id: UUID, reason: str = "logout"
    ) -> bool:
        """Terminate a specific session"""

        result = await db.execute(
            select(UserSession).where(UserSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if session:
            session.terminate_session(reason)
            await db.commit()

            logger.log_info(
                {
                    "event_type": "session_terminated",
                    "session_id": str(session_id),
                    "user_id": str(session.user_id),
                    "reason": reason,
                }
            )
            return True

        return False

    @staticmethod
    def extract_device_info(request: Request) -> dict:
        """
        Extract comprehensive device fingerprinting information for robust authentication

        Enhanced version of your original method that maintains compatibility
        while adding security features and better error handling.
        """
        # Extract basic headers (same as original)
        user_agent = request.headers.get("user-agent", "").strip()
        accept_language = request.headers.get("accept-language", "").strip()
        accept_encoding = request.headers.get("accept-encoding", "").strip()

        # Get client IP with enhanced proxy support
        client_ip = SessionManager.extract_client_ip(request)

        # Parse user agent for additional insights
        parsed_ua = SessionManager.parse_user_agent(user_agent)

        # Extract additional security-relevant headers
        security_headers = {
            "connection": request.headers.get("connection", ""),
            "cache_control": request.headers.get("cache-control", ""),
            "sec_ch_ua": request.headers.get("sec-ch-ua", ""),
            "sec_ch_ua_platform": request.headers.get("sec-ch-ua-platform", ""),
            "sec_ch_ua_mobile": request.headers.get("sec-ch-ua-mobile", ""),
            "sec_fetch_site": request.headers.get("sec-fetch-site", ""),
            "sec_fetch_mode": request.headers.get("sec-fetch-mode", ""),
            "dnt": request.headers.get("dnt", ""),
        }

        # Normalize language for consistency (take primary language only)
        normalized_language = (
            accept_language.split(",")[0].split(";")[0].lower()
            if accept_language
            else ""
        )
        normalized_encoding = SessionManager.normalize_header(accept_encoding)

        # Fingerprint device (more stable components)
        components = [
            parsed_ua.get("browser", ""),
            parsed_ua.get("os", ""),
            normalized_language,
            normalized_encoding,
            (
                client_ip
                if not client_ip.startswith(("127.", "192.168.", "10.", "172."))
                else ""
            ),
        ]

        fingerprint_data = "|".join(filter(None, components))
        fingerprint = hashlib.sha256(fingerprint_data.encode("utf-8")).hexdigest()[:32]

        # 3. Security fingerprint (includes security headers)
        security_components = components + [
            security_headers.get("sec_ch_ua", ""),
            security_headers.get("sec_ch_ua_platform", ""),
            security_headers.get("connection", ""),
        ]

        security_fingerprint_data = "|".join(filter(None, security_components))
        security_fingerprint = hashlib.sha256(
            security_fingerprint_data.encode("utf-8")
        ).hexdigest()[:32]

        # Compile device information
        device_data = {
            # Original fields for backward compatibility
            "user_agent": user_agent,
            "accept_language": accept_language,
            "accept_encoding": accept_encoding,
            # Enhanced fields
            "client_ip": client_ip,
            "fingerprint": fingerprint,
            "security_fingerprint": security_fingerprint,
            "parsed_ua": parsed_ua,
            "normalized_language": normalized_language,
            "normalized_encoding": normalized_encoding,
            "security_headers": security_headers,
            "timestamp": datetime.now(timezone.utc).timestamp(),
            # Fingerprint metadata
            "fingerprint_components": len([c for c in components if c]),
            "has_security_headers": bool(any(security_headers.values())),
        }

        # Calculate risk assessment
        risk_score, risk_factors = SessionManager.calculate_device_risk_score(
            device_data
        )
        device_data.update(
            {
                "risk_score": risk_score,
                "risk_factors": risk_factors,
                "risk_level": (
                    "high"
                    if risk_score >= 70
                    else "medium" if risk_score >= 30 else "low"
                ),
            }
        )

        return device_data


class TokenManager:
    """Enhanced token management with session integration"""

    @staticmethod
    def create_access_token(
        data: dict,
        expires_delta: Optional[timedelta] = None,
        session_id: Optional[UUID] = None,
    ) -> str:
        """Create a JWT access token with optional session reference"""

        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire, "type": "access"})

        # Include session ID if provided
        if session_id:
            to_encode["sid"] = str(session_id)

        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token(
        user_id: UUID, device_info: str = None, ip_address: str = None
    ) -> str:
        """Create a refresh token with enhanced tracking"""

        jti = str(uuid4())
        expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        to_encode = {"sub": str(user_id), "exp": expires, "type": "refresh", "jti": jti}

        token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return token

    @staticmethod
    def decode_token(token: str) -> dict:
        """Decode and verify a JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError as e:
            raise ValueError("Invalid or expired token") from e

    @staticmethod
    async def create_refresh_token_record(
        db: AsyncSession,
        user_id: uuid.UUID,
        token: str,
        device_info: Union[str, Dict],
        ip_address: str,
    ):
        """Create refresh token record with absolute expiration"""
        from app.models.user_model import RefreshToken

        current_time = datetime.now(timezone.utc)
        absolute_expiry = current_time + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        regular_expiry = current_time + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Serialize device_info if it's a dict
        if isinstance(device_info, dict):
            device_info_str = json.dumps(device_info)
        else:
            device_info_str = device_info if device_info else ""

        refresh_token_record = RefreshToken(
            user_id=user_id,
            token=token_hash,
            device_info=device_info_str,
            ip_address=ip_address,
            expires_at=regular_expiry,
            absolute_expiry=absolute_expiry,
            last_used_at=current_time,
            usage_count=1,
            is_revoked=False,
        )

        db.add(refresh_token_record)
        await db.commit()
        await db.refresh(refresh_token_record)

        return refresh_token_record

    @staticmethod
    async def validate_refresh_token(db: AsyncSession, token: str):
        """Validate refresh token with absolute expiration check"""
        from app.models.user_model import RefreshToken
        from sqlalchemy.orm import selectinload

        token_hash = hashlib.sha256(token.encode()).hexdigest()

        result = await db.execute(
            select(RefreshToken)
            .options(selectinload(RefreshToken.user))
            .where(RefreshToken.token == token_hash, RefreshToken.is_revoked == False)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def revoke_refresh_token(db: AsyncSession, token_id: uuid.UUID):
        """Revoke a refresh token by ID"""
        from app.models.user_model import RefreshToken

        result = await db.execute(
            select(RefreshToken).where(RefreshToken.id == token_id)
        )

        token_record = result.scalar_one_or_none()
        if token_record:
            token_record.revoke()
            await db.commit()
            return True
        return False
