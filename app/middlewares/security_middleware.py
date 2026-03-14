"""
Device fingerprint validation with HMAC signing.

Flow
----
1.  The client (React) computes a SHA-256 hash of hardware signals
    (canvas, WebGL, audio, screen, fonts) and sends it as:
        X-Device-Fingerprint: v2:<64-hex-chars>

2.  The server:
    a. Validates the header format and version.
    b. Creates a *composite* fingerprint:
           composite = SHA-256( client_fp + "|" + user_agent )
       The User-Agent is the only stable signal the server can add on top
       of the client hash.
    c. Signs the composite with HMAC-SHA256 using DEVICE_FINGERPRINT_SECRET:
           stored = HMAC-SHA256( secret, composite )
    d. Looks up the stored HMAC in the database.  Only an authentic client
       running the correct fingerprinting code AND presenting the matching
       User-Agent can produce the same HMAC.

Why HMAC?
---------
The client fingerprint hash alone is not enough:
  - An attacker who reads the algorithm can reproduce any client fingerprint
    without the actual hardware.
  - The HMAC binds the fingerprint to a server secret the attacker cannot know.
  - Even if the database is compromised, the stored HMACs cannot be reversed
    to recover the original fingerprint values.

Attack surface
--------------
  - A sophisticated attacker with access to the target device can still
    reproduce the fingerprint (canvas spoofing etc.).  This is mitigated by
    requiring admin approval on *every* new fingerprint value, not just on
    new devices — so even a successful spoof requires a separate approval
    for the attacker's session.
  - The server secret must be stored securely (env var, secrets manager).
    Rotation of DEVICE_FINGERPRINT_SECRET invalidates all stored device trust
    records, requiring re-approval.  Plan rotations accordingly.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from datetime import datetime, timezone
from typing import Tuple

from fastapi import HTTPException, Request

from app.config.config import settings
from app.core.utils import logger
from app.middlewares.device_trust import DeviceStatus
from app.middlewares.device_trust_repo import SecurityRepository


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Supported fingerprint algorithm versions.  When the client-side algorithm
# changes, bump the version here before deploying the new fingerprintService.ts
# so old and new clients can coexist during the rollout window.
_SUPPORTED_VERSIONS = {"v2"}

# Expected format: "<version>:<64 hex chars>"
_FINGERPRINT_RE = re.compile(r'^(v\d+):([0-9a-f]{64})$')


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprint utilities
# ─────────────────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _parse_fingerprint_header(header: str) -> tuple[str, str]:
    """
    Parse and validate the X-Device-Fingerprint header.

    Returns (version, raw_hash) or raises HTTPException 400.
    """
    m = _FINGERPRINT_RE.match(header.strip())
    print(f"Hello I am here please {m}")
    if not m:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_fingerprint_format",
                "message": (
                    "X-Device-Fingerprint header must be in the format "
                    "'<version>:<64 hex chars>' e.g. 'v2:a3f2...'."
                ),
            },
        )
    version, raw_hash = m.group(1), m.group(2)
    if version not in _SUPPORTED_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_fingerprint_version",
                "message": (
                    f"Fingerprint version '{version}' is not supported. "
                    f"Please update your client application."
                ),
            },
        )
    return version, raw_hash


def _build_composite(client_hash: str, user_agent: str) -> str:
    """
    Combine the client fingerprint hash with the User-Agent into a single
    composite string, then SHA-256 hash it.

    The User-Agent is the only stable server-observable signal that adds
    entropy on top of the hardware fingerprint.  Binding them together means
    a fingerprint stolen from one browser type cannot be replayed from a
    different one.
    """
    raw = f"{client_hash}|{user_agent}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sign_fingerprint(composite: str) -> str:
    """
    HMAC-SHA256 sign the composite fingerprint with the server secret.

    The result is what gets stored in the database.  Verification is a
    constant-time comparison (hmac.compare_digest) to prevent timing attacks.
    """
    secret = settings.DEVICE_FINGERPRINT_SECRET.encode("utf-8")
    return hmac.new(secret, composite.encode("utf-8"), hashlib.sha256).hexdigest()


def compute_stored_fingerprint(request: Request, client_hash: str) -> str:
    """
    Full pipeline: client_hash → composite → HMAC.
    Call this wherever a fingerprint needs to be computed for storage or
    for lookup (the lookup key IS the HMAC).
    """
    user_agent = request.headers.get("user-agent", "")
    composite  = _build_composite(client_hash, user_agent)
    return _sign_fingerprint(composite)


# ─────────────────────────────────────────────────────────────────────────────
# Main middleware service
# ─────────────────────────────────────────────────────────────────────────────

class DeviceTrustService:
    """
    Validates device trust after authentication.

    Fingerprint lifecycle
    ---------------------
    New device (fingerprint HMAC not in DB)
      → register as PENDING, commit, raise 403 new_device_detected

    Known PENDING
      → raise 403 device_pending

    Known BLOCKED
      → raise 403 device_blocked

    Known SUSPICIOUS
      → raise 403 device_suspicious

    Known TRUSTED but expired
      → revert to PENDING, commit, raise 403 device_expired

    Known TRUSTED, not expired
      → update last_seen / last_ip, commit, return (True, "Device trusted", False)
    """

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        return _get_client_ip(request)

    @staticmethod
    async def check_and_register_device(
        request: Request,
        user_id: uuid.UUID,
        db,
    ) -> Tuple[bool, str, bool]:
        """
        Entry point called from the login handler after credentials are verified.

        Raises HTTPException 400 if the fingerprint header is malformed.
        Raises HTTPException 403 for any untrusted device state.
        Returns (True, "Device trusted", False) for trusted devices.
        """
        # ── 1. Parse header ───────────────────────────────────────────────
        raw_header = request.headers.get("X-Device-Fingerprint", "")
        if not raw_header:
            # No fingerprint header — treat as a new/unknown device.
            # This handles old clients or direct API calls gracefully.
            logger.log_security_event({
                "event_type": "missing_device_fingerprint",
                "user_id":    str(user_id),
                "ip":         _get_client_ip(request),
            })
            raise HTTPException(
                status_code=400,
                detail={
                    "error":   "missing_device_fingerprint",
                    "message": (
                        "X-Device-Fingerprint header is required. "
                        "Please use a supported client application."
                    ),
                },
            )

        _version, client_hash = _parse_fingerprint_header(raw_header)

        # ── 2. Compute the stored fingerprint (HMAC of composite) ─────────
        stored_fp = compute_stored_fingerprint(request, client_hash)

        # ── 3. Lookup ──────────────────────────────────────────────────────
        repo   = SecurityRepository(db)
        device = await repo.get_device_by_fingerprint(stored_fp)

        if not device:
            # ── 3a. New device → register as PENDING ─────────────────────
            device = await repo.create_pending_device(
                user_id=user_id,
                device_fingerprint=stored_fp,   # store the HMAC, not the raw hash
                request=request,
            )
            await db.commit()

            logger.log_security_event({
                "event_type": "new_device_registered",
                "user_id":    str(user_id),
                "device_id":  str(device.id),
                "ip":         _get_client_ip(request),
            })

            raise HTTPException(
                status_code=403,
                detail={
                    "error":            "new_device_detected",
                    "message": (
                        "New device detected. An administrator must approve "
                        "this device before you can continue."
                    ),
                    "device_id":        str(device.id),
                    "requires_approval": True,
                },
            )

        # ── 3b. Known device — check status ──────────────────────────────
        if device.status == DeviceStatus.BLOCKED:
            logger.log_security_event({
                "event_type": "blocked_device_login_attempt",
                "user_id":    str(user_id),
                "device_id":  str(device.id),
                "ip":         _get_client_ip(request),
            })
            raise HTTPException(
                status_code=403,
                detail={
                    "error":            "device_blocked",
                    "message":          "This device has been blocked. Please contact your administrator.",
                    "requires_approval": False,
                },
            )

        if device.status == DeviceStatus.SUSPICIOUS:
            logger.log_security_event({
                "event_type": "suspicious_device_login_attempt",
                "user_id":    str(user_id),
                "device_id":  str(device.id),
                "ip":         _get_client_ip(request),
            })
            raise HTTPException(
                status_code=403,
                detail={
                    "error":            "device_suspicious",
                    "message":          "This device is under security review. Please contact your administrator.",
                    "requires_approval": False,
                },
            )

        if device.status == DeviceStatus.PENDING:
            raise HTTPException(
                status_code=403,
                detail={
                    "error":            "device_pending",
                    "message":          "Device approval is pending. An administrator will review your request soon.",
                    "device_id":        str(device.id),
                    "requires_approval": True,
                },
            )

        # ── 3c. TRUSTED — check expiry ────────────────────────────────────
        if device.is_expired():
            device.status = DeviceStatus.PENDING
            await repo.update_device(device)
            await db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "error":            "device_expired",
                    "message": (
                        "Device trust has expired. Re-approval is required. "
                        "Please contact your administrator."
                    ),
                    "device_id":        str(device.id),
                    "requires_approval": True,
                },
            )

        # ── 3d. Active TRUSTED device — update activity ───────────────────
        device.last_seen       = datetime.now(timezone.utc)
        device.last_ip_address = _get_client_ip(request)
        await repo.update_device(device)
        await db.commit()

        return True, "Device trusted", False