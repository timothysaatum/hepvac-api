from enum import Enum
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional, List
import uuid
from datetime import datetime
import re


class RoleSchema(BaseModel):
    """Schema for user roles."""

    id: int
    name: str

    model_config = {"from_attributes": True}


class PermissionSchema(BaseModel):
    """Schema for permission information."""

    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class FacilitySchema(BaseModel):
    """Schema for facility information."""

    id: uuid.UUID
    facility_name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    model_config = {"from_attributes": True}


class UserBaseSchema(BaseModel):
    """Base schema for user with common fields."""

    username: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: EmailStr

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format and constraints."""
        if not v or not v.strip():
            raise ValueError("Username cannot be empty")

        v = v.strip()

        if len(v) < 3 or len(v) > 50:
            raise ValueError("Username must be between 3 and 50 characters long")

        if " " in v:
            raise ValueError("Username must not contain spaces")

        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Username can only contain alphanumeric characters, underscores, and hyphens"
            )

        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        if " " in v:
            raise ValueError("Email must not contain spaces")

        if v.count("@") != 1:
            raise ValueError('Email must contain exactly one "@" symbol')

        return v.lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format."""
        if v is None:
            return v

        v = v.strip()

        # Check for letters
        if any(c.isalpha() for c in v):
            raise ValueError("Phone number must not contain letters")

        # Validate format
        if not re.match(r"^\+?\d{10,15}$", v):
            raise ValueError(
                "Phone number must be 10-15 digits, optionally starting with '+'"
            )

        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate full name format."""
        if v is None:
            return v

        v = v.strip()

        if not v:
            raise ValueError("Full name cannot be empty or whitespace only")

        if len(v) > 100:
            raise ValueError("Full name must not exceed 100 characters")

        if any(char.isdigit() for char in v):
            raise ValueError("Full name must not contain numbers")

        if re.search(r"[!@#$%^&*()_+=\[\]{}|;:,.<>?/\\]", v):
            raise ValueError("Full name must not contain special characters")

        # Check for at least two words (first and last name)
        if len(v.split()) < 2:
            raise ValueError(
                "Full name must contain at least a first name and a last name"
            )

        return v

    model_config = {"from_attributes": True}


class UserRole(str, Enum):
    admin = "admin"
    staff = "staff"


class UserCreateSchema(UserBaseSchema):
    """Schema for creating a new user."""

    password: str
    password_confirm: str
    roles: Optional[List[str]] = []

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        if len(v) > 128:
            raise ValueError("Password must not exceed 128 characters")

        if " " in v:
            raise ValueError("Password must not contain spaces")

        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")

        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(char.islower() for char in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if not re.search(r"[!@#$%^&*()_+=\[\]{}|;:,.<>?/\\-]", v):
            raise ValueError("Password must contain at least one special character")

        return v

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "UserCreateSchema":
        """Validate that password and password_confirm match."""
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self


class UserUpdateSchema(UserBaseSchema):
    """Schema for updating an existing user."""

    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    roles: Optional[List[str]] = []

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password strength requirements if provided."""
        if v is None:
            return v

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        if len(v) > 128:
            raise ValueError("Password must not exceed 128 characters")

        if " " in v:
            raise ValueError("Password must not contain spaces")

        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")

        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(char.islower() for char in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if not re.search(r"[!@#$%^&*()_+=\[\]{}|;:,.<>?/\\-]", v):
            raise ValueError("Password must contain at least one special character")

        return v


class UserSchema(UserBaseSchema):
    """Schema for returning user data."""

    id: uuid.UUID
    is_active: bool
    is_suspended: bool
    roles: List[RoleSchema]
    facility: Optional[FacilitySchema] = None
    created_at: datetime
    updated_at: datetime


class UserLoginSchema(BaseModel):
    """Schema for user login credentials."""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not v or not v.strip():
            raise ValueError("Username cannot be empty")

        v = v.strip()

        if " " in v:
            raise ValueError("Username must not contain spaces")

        if len(v) < 3 or len(v) > 50:
            raise ValueError("Username must be between 3 and 50 characters long")

        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password is not empty."""
        if not v or not v.strip():
            raise ValueError("Password cannot be empty")

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        if len(v) > 128:
            raise ValueError("Password must not exceed 128 characters")

        return v

    model_config = {"from_attributes": True}


class AuthResponse(UserSchema):
    access_token: str
