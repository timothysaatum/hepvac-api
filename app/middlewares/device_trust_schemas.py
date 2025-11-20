# ============= SCHEMAS =============
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid
from enum import Enum


class DeviceStatus(str, Enum):
    PENDING = "pending"
    TRUSTED = "trusted"
    BLOCKED = "blocked"
    SUSPICIOUS = "suspicious"


class TrustedDeviceResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    device_name: Optional[str]
    browser: Optional[str]
    os: Optional[str]
    device_type: Optional[str]
    last_ip_address: Optional[str]
    status: DeviceStatus
    first_seen: datetime
    last_seen: datetime
    approved_by_id: Optional[uuid.UUID]
    approved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DeviceApprovalSchema(BaseModel):
    status: DeviceStatus
    notes: Optional[str] = None
    expires_in_days: Optional[int] = None  # Auto-expire after N days


class LoginAttemptResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    username: str
    ip_address: str
    success: bool
    failure_reason: Optional[str]
    country: Optional[str]
    city: Optional[str]
    attempted_at: datetime

    model_config = {"from_attributes": True}