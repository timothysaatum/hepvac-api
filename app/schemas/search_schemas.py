from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
import uuid
from pydantic import BaseModel, field_validator, Field

from app.schemas.patient_schemas import PatientStatus, Sex, DoseType


# ============= Patient Search Schemas =============
class PatientSearchFilters(BaseModel):
    """Schema for patient search filters with security constraints."""
    
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    facility_id: Optional[uuid.UUID] = None
    patient_type: Optional[str] = None  # 'pregnant' or 'regular'
    status: Optional[PatientStatus] = None
    sex: Optional[Sex] = None
    age_min: Optional[int] = Field(None, ge=0, le=150)
    age_max: Optional[int] = Field(None, ge=0, le=150)
    created_from: Optional[date] = None
    created_to: Optional[date] = None
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize name for search - SECURITY."""
        if v:
            v = v.strip()
            # Minimum length to prevent abuse
            if len(v) < 2:
                raise ValueError("Name search must be at least 2 characters")
            # Maximum length already enforced by Field
            # Remove special SQL characters for safety
            dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "\\"]
            for char in dangerous_chars:
                if char in v:
                    raise ValueError(f"Invalid character in search term: {char}")
        return v
    
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize phone for search - SECURITY."""
        if v:
            v = v.strip()
            # Only allow digits, +, and spaces
            allowed_chars = set("0123456789+ ")
            if not all(c in allowed_chars for c in v):
                raise ValueError("Phone number can only contain digits, +, and spaces")
        return v
    
    @field_validator("patient_type")
    @classmethod
    def validate_patient_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate patient type - SECURITY."""
        if v and v not in ["pregnant", "regular"]:
            raise ValueError("patient_type must be 'pregnant' or 'regular'")
        return v
    
    @field_validator("age_min", "age_max")
    @classmethod
    def validate_age(cls, v: Optional[int]) -> Optional[int]:
        """Validate age range - already handled by Field constraints."""
        return v
    
    @field_validator("created_from", "created_to")
    @classmethod
    def validate_date_range(cls, v: Optional[date]) -> Optional[date]:
        """Validate date range - SECURITY."""
        if v:
            # Prevent queries too far in the past (performance)
            from datetime import datetime, timedelta
            min_date = datetime.now().date() - timedelta(days=3650)  # 10 years
            if v < min_date:
                raise ValueError("Date range cannot exceed 10 years in the past")
        return v

    model_config = {"from_attributes": True}


class PatientSearchResult(BaseModel):
    """Schema for patient search result."""
    
    id: uuid.UUID
    name: str
    phone: str
    age: int
    sex: Sex
    patient_type: str
    status: PatientStatus
    facility_id: uuid.UUID
    created_at: datetime
    
    # Additional info for pregnant patients
    expected_delivery_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None
    
    # Additional info for regular patients
    diagnosis_date: Optional[date] = None
    treatment_start_date: Optional[date] = None
    viral_load: Optional[str] = None

    model_config = {"from_attributes": True}


class PatientSearchResponse(BaseModel):
    """Schema for paginated patient search response."""
    
    items: List[PatientSearchResult]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
    query_time_ms: Optional[float] = None  # For monitoring

    model_config = {"from_attributes": True}


# ============= Vaccination Search Schemas =============
class VaccinationSearchFilters(BaseModel):
    """Schema for vaccination search filters with security constraints."""
    
    patient_id: Optional[uuid.UUID] = None
    patient_name: Optional[str] = Field(None, max_length=100)
    patient_phone: Optional[str] = Field(None, max_length=20)
    vaccine_name: Optional[str] = Field(None, max_length=100)
    batch_number: Optional[str] = Field(None, max_length=100)
    dose_number: Optional[DoseType] = None
    dose_date_from: Optional[date] = None
    dose_date_to: Optional[date] = None
    administered_by_id: Optional[uuid.UUID] = None
    facility_id: Optional[uuid.UUID] = None
    
    @field_validator("patient_name", "vaccine_name")
    @classmethod
    def validate_search_term(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize search terms - SECURITY."""
        if v:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Search term must be at least 2 characters")
            # Remove dangerous SQL characters
            dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "\\"]
            for char in dangerous_chars:
                if char in v:
                    raise ValueError(f"Invalid character in search term: {char}")
        return v
    
    @field_validator("patient_phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone - SECURITY."""
        if v:
            v = v.strip()
            allowed_chars = set("0123456789+ ")
            if not all(c in allowed_chars for c in v):
                raise ValueError("Phone number can only contain digits, +, and spaces")
        return v
    
    @field_validator("batch_number")
    @classmethod
    def validate_batch(cls, v: Optional[str]) -> Optional[str]:
        """Validate batch number - SECURITY."""
        if v:
            v = v.strip()
            # Only allow alphanumeric and common batch characters
            allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
            if not all(c in allowed_chars for c in v):
                raise ValueError("Batch number contains invalid characters")
        return v
    
    @field_validator("dose_date_from", "dose_date_to")
    @classmethod
    def validate_date_range(cls, v: Optional[date]) -> Optional[date]:
        """Validate date range - SECURITY."""
        if v:
            from datetime import datetime, timedelta
            min_date = datetime.now().date() - timedelta(days=3650)
            if v < min_date:
                raise ValueError("Date range cannot exceed 10 years in the past")
        return v

    model_config = {"from_attributes": True}


class VaccinationSearchResult(BaseModel):
    """Schema for vaccination search result."""
    
    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    patient_phone: str
    vaccine_purchase_id: uuid.UUID
    vaccine_name: str
    dose_number: DoseType
    dose_date: date
    batch_number: str
    vaccine_price: Decimal
    administered_by_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VaccinationSearchResponse(BaseModel):
    """Schema for paginated vaccination search response."""
    
    items: List[VaccinationSearchResult]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
    query_time_ms: Optional[float] = None

    model_config = {"from_attributes": True}


# ============= Payment Search Schemas =============
class PaymentSearchFilters(BaseModel):
    """Schema for payment search filters with security constraints."""
    
    patient_id: Optional[uuid.UUID] = None
    patient_name: Optional[str] = Field(None, max_length=100)
    patient_phone: Optional[str] = Field(None, max_length=20)
    vaccine_purchase_id: Optional[uuid.UUID] = None
    payment_method: Optional[str] = Field(None, max_length=50)
    payment_date_from: Optional[date] = None
    payment_date_to: Optional[date] = None
    amount_min: Optional[Decimal] = Field(None, ge=0)
    amount_max: Optional[Decimal] = Field(None, ge=0)
    received_by_id: Optional[uuid.UUID] = None
    facility_id: Optional[uuid.UUID] = None
    reference_number: Optional[str] = Field(None, max_length=100)
    
    @field_validator("patient_name")
    @classmethod
    def validate_search_term(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize search terms - SECURITY."""
        if v:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Search term must be at least 2 characters")
            dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "\\"]
            for char in dangerous_chars:
                if char in v:
                    raise ValueError(f"Invalid character in search term: {char}")
        return v
    
    @field_validator("patient_phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone - SECURITY."""
        if v:
            v = v.strip()
            allowed_chars = set("0123456789+ ")
            if not all(c in allowed_chars for c in v):
                raise ValueError("Phone number can only contain digits, +, and spaces")
        return v
    
    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: Optional[str]) -> Optional[str]:
        """Validate payment method - SECURITY."""
        if v:
            valid_methods = ["cash", "mobile_money", "bank_transfer", "card", "cheque"]
            if v.lower() not in valid_methods:
                raise ValueError(f"Invalid payment method. Must be one of: {', '.join(valid_methods)}")
        return v
    
    @field_validator("reference_number")
    @classmethod
    def validate_reference(cls, v: Optional[str]) -> Optional[str]:
        """Validate reference number - SECURITY."""
        if v:
            v = v.strip()
            # Only allow alphanumeric and common reference characters
            allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
            if not all(c.upper() in allowed_chars for c in v):
                raise ValueError("Reference number contains invalid characters")
        return v
    
    @field_validator("payment_date_from", "payment_date_to")
    @classmethod
    def validate_date_range(cls, v: Optional[date]) -> Optional[date]:
        """Validate date range - SECURITY."""
        if v:
            from datetime import datetime, timedelta
            min_date = datetime.now().date() - timedelta(days=3650)
            if v < min_date:
                raise ValueError("Date range cannot exceed 10 years in the past")
        return v

    model_config = {"from_attributes": True}


class PaymentSearchResult(BaseModel):
    """Schema for payment search result."""
    
    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    patient_phone: str
    vaccine_purchase_id: uuid.UUID
    vaccine_name: str
    amount: Decimal
    payment_date: date
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    received_by_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentSearchResponse(BaseModel):
    """Schema for paginated payment search response."""
    
    items: List[PaymentSearchResult]
    total_count: int
    total_amount: Decimal
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
    query_time_ms: Optional[float] = None

    model_config = {"from_attributes": True}