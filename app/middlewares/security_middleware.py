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
        """
        Generate a device fingerprint from stable request headers.

        NOTE: This fingerprint is based on User-Agent, Accept-Language, and
        Accept-Encoding — all of which are HTTP headers the client controls.
        A sophisticated attacker can spoof them to match a trusted device.
        For higher-assurance environments consider supplementing with a
        client-side fingerprinting library (e.g. FingerprintJS) that captures
        hardware-level signals (screen resolution, canvas, WebGL) and sends a
        signed token the server validates. What we have here is a reasonable
        first layer, not a cryptographic guarantee.
        """
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
        Check device trust status after authentication.

        Returns:
            Tuple of (is_allowed, message, is_new_device)

        Raises:
            HTTPException 403: if device is new, blocked, suspicious,
                               pending approval, or trust has expired.
        """
        device_fingerprint = DeviceTrustService._generate_device_fingerprint(request)
        repo = SecurityRepository(db)

        device = await repo.get_device_by_fingerprint(device_fingerprint)

        if not device:
            # New device — register as PENDING and block login immediately.
            device = await repo.create_pending_device(
                user_id=user_id,
                device_fingerprint=device_fingerprint,
                request=request,
            )
            # FIX: repo.create_pending_device now flushes, not commits.
            # Commit here so the new device row is durable before we raise
            # the 403 — otherwise the pending device record could be lost
            # if the surrounding request context is rolled back.
            await db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "new_device_detected",
                    "message": (
                        "New device detected. An administrator must approve "
                        "this device before you can continue."
                    ),
                    "device_id": str(device.id),
                    "requires_approval": True,
                },
            )

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

        # Check if trusted device has expired.
        if device.is_expired():
            device.status = DeviceStatus.PENDING
            await repo.update_device(device)
            # FIX: repo.update_device now flushes. Commit so the status
            # revert to PENDING is durable before raising the 403.
            await db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "device_expired",
                    "message": (
                        "Device trust has expired. Re-approval is required. "
                        "Please contact your administrator."
                    ),
                    "device_id": str(device.id),
                    "requires_approval": True,
                },
            )

        # Device is TRUSTED — update activity metadata.
        device.last_seen = datetime.now(timezone.utc)
        device.last_ip_address = DeviceTrustService._get_client_ip(request)
        await repo.update_device(device)
        # FIX: commit the last_seen / last_ip_address update.
        await db.commit()

        return True, "Device trusted", False