# ============= REPOSITORY =============
from typing import List, Optional
import uuid
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

        user_agent = request.headers.get("user-agent", "")
        ua = parse(user_agent)

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
        await self.db.commit()
        await self.db.refresh(device)
        return device

    async def update_device(self, device: "TrustedDevice"):
        self.db.add(device)
        await self.db.commit()
        await self.db.refresh(device)
        return device

    async def get_pending_devices(
        self, facility_id: Optional[uuid.UUID] = None
    ) -> List["TrustedDevice"]:
        query = select(TrustedDevice).where(
            TrustedDevice.status == DeviceStatus.PENDING
        )

        if facility_id:
            query = query.join(User).where(User.facility_id == facility_id)

        query = query.order_by(TrustedDevice.first_seen.desc())

        result = await self.db.execute(query)
        return result.scalars().all()

    async def log_login_attempt(
        self,
        username: str,
        ip_address: str,
        success: bool,
        user_id: Optional[uuid.UUID] = None,
        device_fingerprint: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ):
        attempt = LoginAttempt(
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            success=success,
            failure_reason=failure_reason,
        )

        self.db.add(attempt)
        await self.db.commit()
        return attempt

    async def get_failed_attempts_count(
        self, identifier: str, identifier_type: str = "ip", minutes: int = 15
    ) -> int:
        """Count failed login attempts for IP or username in last N minutes"""
        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        query = select(func.count(LoginAttempt.id)).where(
            LoginAttempt.success == False,
            LoginAttempt.attempted_at >= time_threshold,
        )

        if identifier_type == "ip":
            query = query.where(LoginAttempt.ip_address == identifier)
        else:
            query = query.where(LoginAttempt.username == identifier)

        result = await self.db.execute(query)
        return result.scalar() or 0

    def _get_client_ip(self, request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host
