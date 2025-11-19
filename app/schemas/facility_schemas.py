from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
import uuid
from datetime import datetime
import re


class FacilityBaseSchema(BaseModel):
    """Base schema for facility with common fields."""

    facility_name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None

    @field_validator("facility_name")
    @classmethod
    def validate_facility_name(cls, v: str) -> str:
        """Validate facility_name format and constraints."""
        if not v or not v.strip():
            raise ValueError("facility_name cannot be empty")

        v = v.strip()

        if len(v) < 3 or len(v) > 50:
            raise ValueError("facility_name must be between 3 and 50 characters long")

        if not re.match(r"^[a-zA-Z0-9 _-]+$", v):
            raise ValueError(
                "facility_name can only contain alphanumeric characters, spaces, underscores, and hyphens"
            )


        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Remove common separators
        digits = "".join(filter(str.isdigit, v))

        if len(digits) < 10 or len(digits) > 15:
            raise ValueError("Phone number must be between 10 and 15 digits")

        return v

    model_config = {"from_attributes": True}


class FacilityCreateSchema(FacilityBaseSchema):
    """Schema for creating a new facility."""

    pass


class FacilityUpdateSchema(BaseModel):
    """Schema for updating a facility. All fields are optional."""

    facility_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None

    @field_validator("facility_name")
    @classmethod
    def validate_facility_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate facility_name format and constraints."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("facility_name cannot be empty")

        v = v.strip()

        if len(v) < 3 or len(v) > 50:
            raise ValueError("facility_name must be between 3 and 50 characters long")

        if not re.match(r"^[a-zA-Z0-9 _-]+$", v):
            raise ValueError(
                "facility_name can only contain alphanumeric characters, underscores, and hyphens"
            )

        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Remove common separators
        digits = "".join(filter(str.isdigit, v))

        if len(digits) < 10 or len(digits) > 15:
            raise ValueError("Phone number must be between 10 and 15 digits")

        return v

    model_config = {"from_attributes": True}


class FacilityManagerSchema(BaseModel):
    """Simplified schema for facility manager information."""

    id: uuid.UUID
    username: str
    full_name: Optional[str] = None
    email: str

    model_config = {"from_attributes": True}


class FacilityResponseSchema(FacilityBaseSchema):
    """Schema for facility response with full details."""

    id: uuid.UUID
    facility_manager_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FacilityDetailSchema(FacilityResponseSchema):
    """Schema for detailed facility response including manager and staff info."""

    facility_manager: Optional[FacilityManagerSchema] = None
    staff_count: Optional[int] = None

    model_config = {"from_attributes": True}


class StaffAssignmentSchema(BaseModel):
    """Schema for staff assignment operations."""

    user_id: uuid.UUID
    facility_id: uuid.UUID

    model_config = {"from_attributes": True}
