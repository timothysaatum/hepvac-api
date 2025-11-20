# ============= SERVICE =============
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import uuid
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.middlewares.device_trust import DeviceStatus, TrustedDevice
from app.middlewares.device_trust_repo import SecurityRepository
from app.middlewares.device_trust_schemas import DeviceApprovalSchema


class SecurityService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SecurityRepository(db)

    async def approve_device(
        self,
        device_id: uuid.UUID,
        approval_data: DeviceApprovalSchema,
        approved_by_id: uuid.UUID,
    ):
        device = await self._get_device(device_id)

        device.status = approval_data.status
        device.notes = approval_data.notes
        device.approved_by_id = approved_by_id
        device.approved_at = datetime.now(timezone.utc)

        if approval_data.expires_in_days:
            device.expires_at = datetime.now(timezone.utc) + timedelta(
                days=approval_data.expires_in_days
            )

        return await self.repo.update_device(device)

    async def get_pending_devices(
        self, facility_id: Optional[uuid.UUID] = None
    ) -> List["TrustedDevice"]:
        return await self.repo.get_pending_devices(facility_id)

    async def get_user_devices(self, user_id: uuid.UUID) -> List["TrustedDevice"]:
        result = await self.db.execute(
            select(TrustedDevice)
            .where(TrustedDevice.user_id == user_id)
            .order_by(TrustedDevice.last_seen.desc())
        )
        return result.scalars().all()

    async def revoke_device(self, device_id: uuid.UUID):
        device = await self._get_device(device_id)
        device.status = DeviceStatus.BLOCKED
        return await self.repo.update_device(device)

    async def _get_device(self, device_id: uuid.UUID):
        result = await self.db.execute(
            select(TrustedDevice).where(TrustedDevice.id == device_id)
        )
        device = result.scalars().first()
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Device not found"
            )
        return device
