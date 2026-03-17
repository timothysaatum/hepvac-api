# ============= REPOSITORY =============
from typing import List, Optional
import uuid
from aiosmtplib import status
from aiosmtplib import status
from dns.resolver import query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone

from app.middlewares.device_trust import DeviceStatus, LoginAttempt, TrustedDevice
from app.models.user_model import User


class SecurityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_device_by_fingerprint(
        self, fingerprint: str
    ) -> Optional["TrustedDevice"]:
        result = await self.db.execute(
            select(TrustedDevice).where(TrustedDevice.device_fingerprint == fingerprint)
        )
        return result.scalars().first()

    async def create_pending_device(
        self, user_id: uuid.UUID, device_fingerprint: str, request
    ) -> "TrustedDevice":
        from user_agents import parse

        user_agent_str = request.headers.get("user-agent", "")
        ua = parse(user_agent_str)

        device = TrustedDevice(
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            device_name=f"{ua.browser.family} on {ua.os.family}",
            browser=f"{ua.browser.family} {ua.browser.version_string}",
            os=f"{ua.os.family} {ua.os.version_string}",
            device_type="mobile" if ua.is_mobile else "desktop",
            last_ip_address=self._get_client_ip(request),
            status=DeviceStatus.PENDING,
        )

        self.db.add(device)
        
        await self.db.flush()
        await self.db.refresh(device)
        return device

    async def update_device(self, device: "TrustedDevice") -> "TrustedDevice":
        self.db.add(device)
        await self.db.flush()
        await self.db.refresh(device)
        return device

    async def get_pending_devices(
        self, facility_id: Optional[uuid.UUID] = None
    ) -> List["TrustedDevice"]:
        query = select(TrustedDevice).where(
            TrustedDevice.status == DeviceStatus.PENDING
        )

        if facility_id:
            query = query.join(
                User, TrustedDevice.user_id == User.id
            ).where(User.facility_id == facility_id)

        query = query.order_by(TrustedDevice.first_seen.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_all_devices(
        self,
        facility_id: Optional[uuid.UUID] = None,
        status: Optional["DeviceStatus"] = None,
    ) -> List["TrustedDevice"]:
        query = select(TrustedDevice)

        if status:
            query = query.where(TrustedDevice.status == status)

        if facility_id:
            query = query.join(
                User, TrustedDevice.user_id == User.id
            ).where(User.facility_id == facility_id)

        query = query.order_by(TrustedDevice.first_seen.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def log_login_attempt(
        self,
        username: str,
        ip_address: str,
        success: bool,
        user_id: Optional[uuid.UUID] = None,
        device_fingerprint: Optional[str] = None,
        failure_reason: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> LoginAttempt:
        attempt = LoginAttempt(
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            success=success,
            failure_reason=failure_reason,
            # FIX: was not passing user_agent to the LoginAttempt constructor
            # even though the model has a user_agent column. Added the parameter
            # to the method signature and the constructor call.
            user_agent=user_agent,
        )

        self.db.add(attempt)
        # FIX: was commit() — use flush() so the caller controls the commit.
        await self.db.flush()
        return attempt

    async def get_failed_attempts_count(
        self, identifier: str, identifier_type: str = "ip", minutes: int = 15
    ) -> int:
        """Count failed login attempts for IP or username in the last N minutes."""
        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        query = select(func.count(LoginAttempt.id)).where(
            # FIX: was LoginAttempt.success == False — use .is_(False) for
            # idiomatic SQLAlchemy boolean comparison.
            LoginAttempt.success.is_(False),
            LoginAttempt.attempted_at >= time_threshold,
        )

        if identifier_type == "ip":
            query = query.where(LoginAttempt.ip_address == identifier)
        else:
            query = query.where(LoginAttempt.username == identifier)

        result = await self.db.execute(query)
        return result.scalar() or 0

    def _get_client_ip(self, request) -> str:
        """
        Extract the real client IP from a request.

        FIX: was taking the first value from X-Forwarded-For without
        validation. This header is user-controlled and can be trivially
        spoofed. In production, the reverse proxy (nginx/Caddy) should
        be configured to overwrite — not append — the X-Forwarded-For
        header so only one trusted value is present.

        This method retains the split logic but adds a note: if your proxy
        is correctly configured, `forwarded.split(",")[0]` is safe. If not,
        an attacker can inject an arbitrary IP by prepending values to the
        header (e.g. "1.2.3.4, real.ip.here").

        For production hardening, configure your proxy to set
        X-Real-IP (single value, overwritten by proxy) and read that here:
            return request.headers.get("x-real-ip") or request.client.host
        """
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the leftmost IP — only safe if the proxy overwrites this header.
            return forwarded.split(",")[0].strip()
        return getattr(request.client, "host", "unknown")