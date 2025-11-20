# ============= ROUTES =============
from typing import List
import uuid
from fastapi import APIRouter, Depends
from app.api.dependencies import get_db
from app.core.permission_checker import require_admin, require_staff_or_admin
from app.middlewares.device_trust_schemas import DeviceApprovalSchema, TrustedDeviceResponse
from app.middlewares.device_trust_service import SecurityService
from app.models.user_model import User
from app.core.utils import logger

from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/devices/pending", response_model=List[TrustedDeviceResponse])
async def get_pending_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Get all devices pending approval (Admin only).
    """
    service = SecurityService(db)
    devices = await service.get_pending_devices(current_user.facility_id)
    return [
        TrustedDeviceResponse.model_validate(d, from_attributes=True) for d in devices
    ]


@router.post("/devices/{device_id}/approve", response_model=TrustedDeviceResponse)
async def approve_device(
    device_id: uuid.UUID,
    approval_data: DeviceApprovalSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Approve, block, or mark device as suspicious (Admin only).
    """
    service = SecurityService(db)
    device = await service.approve_device(device_id, approval_data, current_user.id)

    logger.log_security_event(
        {
            "event_type": "device_status_changed",
            "device_id": str(device_id),
            "new_status": approval_data.status.value,
            "admin_id": str(current_user.id),
        }
    )

    return TrustedDeviceResponse.model_validate(device, from_attributes=True)


@router.get("/devices/my", response_model=List[TrustedDeviceResponse])
async def get_my_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get current user's devices.
    """
    service = SecurityService(db)
    devices = await service.get_user_devices(current_user.id)
    return [
        TrustedDeviceResponse.model_validate(d, from_attributes=True) for d in devices
    ]


@router.delete("/devices/{device_id}")
async def revoke_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Revoke/block a device (Admin only).
    """
    service = SecurityService(db)
    await service.revoke_device(device_id)

    logger.log_security_event(
        {
            "event_type": "device_revoked",
            "device_id": str(device_id),
            "admin_id": str(current_user.id),
        }
    )

    return {"message": "Device revoked successfully"}
