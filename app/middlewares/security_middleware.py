from fastapi import HTTPException, Request
from datetime import datetime, timezone
import hashlib
import uuid
from typing import Tuple

from app.middlewares.device_trust import DeviceStatus
from app.middlewares.device_trust_repo import SecurityRepository


class DeviceTrustService:
    """
    Service to check and manage device trust after authentication.
    """

    @staticmethod
    def _generate_device_fingerprint(request: Request) -> str:
        """Generate unique device fingerprint from request headers."""
        user_agent = request.headers.get("user-agent", "")
        accept_language = request.headers.get("accept-language", "")
        accept_encoding = request.headers.get("accept-encoding", "")

        fingerprint_data = f"{user_agent}|{accept_language}|{accept_encoding}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Get real client IP, accounting for proxies."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    @staticmethod
    async def check_and_register_device(
        request: Request, user_id: uuid.UUID, db
    ) -> Tuple[bool, str, bool]:
        """
        Check device trust status after login.

        Returns:
            Tuple of (is_allowed, message, is_new_device)

        Raises:
            HTTPException: If device is blocked or pending approval
        """
        device_fingerprint = DeviceTrustService._generate_device_fingerprint(request)
        repo = SecurityRepository(db)

        device = await repo.get_device_by_fingerprint(device_fingerprint)

        # New device detected - create and block login
        if not device:
            device = await repo.create_pending_device(
                user_id=user_id,
                device_fingerprint=device_fingerprint,
                request=request,
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "new_device_detected",
                    "message": "New device detected. An administrator must approve this device before you can continue.",
                    "device_id": str(device.id),
                    "requires_approval": True,
                },
            )

        # Check device status
        if device.status == DeviceStatus.BLOCKED:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "device_blocked",
                    "message": "This device has been blocked. Please contact your administrator.",
                    "requires_approval": False,
                },
            )

        if device.status == DeviceStatus.SUSPICIOUS:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "device_suspicious",
                    "message": "This device is under security review. Please contact your administrator.",
                    "requires_approval": False,
                },
            )

        if device.status == DeviceStatus.PENDING:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "device_pending",
                    "message": "Device approval is pending. An administrator will review your request soon.",
                    "device_id": str(device.id),
                    "requires_approval": True,
                },
            )

        # Check if device trust expired
        if device.is_expired():
            device.status = DeviceStatus.PENDING
            await repo.update_device(device)
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "device_expired",
                    "message": "Device trust has expired. Re-approval is required. Please contact your administrator.",
                    "device_id": str(device.id),
                    "requires_approval": True,
                },
            )

        # Device is trusted - update last seen
        device.last_seen = datetime.now(timezone.utc)
        device.last_ip_address = DeviceTrustService._get_client_ip(request)
        await repo.update_device(device)

        return True, "Device trusted", False
