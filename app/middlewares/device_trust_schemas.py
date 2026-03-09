# ============= SCHEMAS =============
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
import uuid

# FIX: was re-defining DeviceStatus as a separate enum in this file.
# That creates two independent enums with identical values — any code
# comparing device.status (model enum) to DeviceStatus from this module
# would always be False because they are different Python types.
# Import the single source-of-truth enum from the model.
from app.middlewares.device_trust import DeviceStatus


class TrustedDeviceResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    # FIX: Optional fields without defaults cause Pydantic v2 to require them
    # as input when constructing the schema manually. Add `= None` defaults.
    device_name: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    device_type: Optional[str] = None
    last_ip_address: Optional[str] = None
    status: DeviceStatus
    first_seen: datetime
    last_seen: datetime
    approved_by_id: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DeviceApprovalSchema(BaseModel):
    status: DeviceStatus
    notes: Optional[str] = None
    expires_in_days: Optional[int] = None  # Auto-expire after N days

    @field_validator("expires_in_days")
    @classmethod
    def validate_expires_in_days(cls, v: Optional[int]) -> Optional[int]:
        # FIX: added validation — an unbounded or negative expiry is a
        # security risk (negative would set expires_at in the past, immediately
        # expiring the device; very large values could effectively be permanent).
        if v is not None:
            if v < 1:
                raise ValueError("expires_in_days must be at least 1.")
            if v > 365:
                raise ValueError("expires_in_days cannot exceed 365 days.")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: DeviceStatus) -> DeviceStatus:
        # FIX: prevent approving a device directly to SUSPICIOUS via the
        # approval endpoint — that status is set by the security review flow,
        # not by an admin manually approving a device.
        if v == DeviceStatus.SUSPICIOUS:
            raise ValueError(
                "Cannot set status to SUSPICIOUS via the approval endpoint. "
                "Use the flag-suspicious endpoint instead."
            )
        return v


class LoginAttemptResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    username: str
    ip_address: str
    success: bool
    failure_reason: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    attempted_at: datetime

    model_config = {"from_attributes": True}