"""
Search schemas — filters, result shapes, and paginated responses for
patient, vaccination, and payment search endpoints.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List
import uuid

from pydantic import BaseModel, field_validator, Field

from app.schemas.patient_schemas import (
    DoseType,
    PatientStatus,
    PregnancySummarySchema,
    Sex,
)


# ============================================================================
# Patient Search
# ============================================================================


class PatientSearchFilters(BaseModel):
    """Validated filter parameters for the patient search endpoint."""

    name:         Optional[str]           = Field(None, max_length=100)
    phone:        Optional[str]           = Field(None, max_length=20)
    facility_id:  Optional[uuid.UUID]     = None
    patient_type: Optional[str]           = None   # "pregnant" | "regular"
    status:       Optional[PatientStatus] = None
    sex:          Optional[Sex]           = None
    age_min:      Optional[int]           = Field(None, ge=0, le=150)
    age_max:      Optional[int]           = Field(None, ge=0, le=150)
    created_from: Optional[date]          = None
    created_to:   Optional[date]          = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Name search must be at least 2 characters.")
            dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "\\"]
            for char in dangerous_chars:
                if char in v:
                    raise ValueError(f"Invalid character in search term: {char!r}")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            allowed = set("0123456789+ ")
            if not all(c in allowed for c in v):
                raise ValueError("Phone can only contain digits, +, and spaces.")
        return v

    @field_validator("patient_type")
    @classmethod
    def validate_patient_type(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in ("pregnant", "regular"):
            raise ValueError("patient_type must be 'pregnant' or 'regular'.")
        return v

    @field_validator("created_from", "created_to")
    @classmethod
    def validate_date_range(cls, v: Optional[date]) -> Optional[date]:
        if v:
            # FIX: removed redundant `from datetime import datetime, timedelta`
            # inside the function body — these are now imported at the module level.
            min_date = datetime.now().date() - timedelta(days=3650)
            if v < min_date:
                raise ValueError("Date range cannot exceed 10 years in the past.")
        return v

    model_config = {"from_attributes": True}


class PatientSearchResult(BaseModel):
    """Single patient row in a search response."""

    id:           uuid.UUID
    name:         str
    phone:        str
    # FIX: Optional — age is a computed property; None when date_of_birth absent.
    age:          Optional[int] = None
    sex:          Sex
    patient_type: str
    status:       PatientStatus
    facility_id:  uuid.UUID
    created_at:   datetime

    # FIX: replaced flat expected_delivery_date / actual_delivery_date fields.
    # Those fields now live on the Pregnancy episode, not on PregnantPatient.
    # The service layer populates this via a LEFT JOIN on pregnancies WHERE is_active=TRUE.
    # None for regular patients or pregnant patients with no active pregnancy.
    active_pregnancy: Optional[PregnancySummarySchema] = None

    # Regular-patient fields — None for pregnant patients.
    diagnosis_date:      Optional[date] = None
    treatment_start_date: Optional[date] = None
    viral_load:          Optional[str]  = None

    model_config = {"from_attributes": True}


class PatientSearchResponse(BaseModel):
    """Paginated patient search response."""

    items:        List[PatientSearchResult]
    total_count:  int
    page:         int
    page_size:    int
    total_pages:  int
    has_next:     bool
    has_previous: bool
    query_time_ms: Optional[float] = None

    model_config = {"from_attributes": True}


# ============================================================================
# Vaccination Search
# ============================================================================


class VaccinationSearchFilters(BaseModel):
    """Validated filter parameters for the vaccination search endpoint."""

    patient_id:       Optional[uuid.UUID] = None
    patient_name:     Optional[str]       = Field(None, max_length=100)
    patient_phone:    Optional[str]       = Field(None, max_length=20)
    vaccine_name:     Optional[str]       = Field(None, max_length=100)
    batch_number:     Optional[str]       = Field(None, max_length=100)
    dose_number:      Optional[DoseType]  = None
    dose_date_from:   Optional[date]      = None
    dose_date_to:     Optional[date]      = None
    administered_by_id: Optional[uuid.UUID] = None
    facility_id:      Optional[uuid.UUID] = None

    @field_validator("patient_name", "vaccine_name")
    @classmethod
    def validate_search_term(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Search term must be at least 2 characters.")
            dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "\\"]
            for char in dangerous_chars:
                if char in v:
                    raise ValueError(f"Invalid character in search term: {char!r}")
        return v

    @field_validator("patient_phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            allowed = set("0123456789+ ")
            if not all(c in allowed for c in v):
                raise ValueError("Phone can only contain digits, +, and spaces.")
        return v

    @field_validator("batch_number")
    @classmethod
    def validate_batch(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
            if not all(c in allowed for c in v):
                raise ValueError("Batch number contains invalid characters.")
        return v

    @field_validator("dose_date_from", "dose_date_to")
    @classmethod
    def validate_date_range(cls, v: Optional[date]) -> Optional[date]:
        if v:
            min_date = datetime.now().date() - timedelta(days=3650)
            if v < min_date:
                raise ValueError("Date range cannot exceed 10 years in the past.")
        return v

    model_config = {"from_attributes": True}


class VaccinationSearchResult(BaseModel):
    """Single vaccination row in a search response."""

    id:                  uuid.UUID
    patient_id:          uuid.UUID
    patient_name:        str
    patient_phone:       str
    vaccine_purchase_id: uuid.UUID
    vaccine_name:        str
    dose_number:         DoseType
    dose_date:           date
    batch_number:        str
    vaccine_price:       Decimal
    administered_by_id:  Optional[uuid.UUID] = None
    notes:               Optional[str]       = None
    created_at:          datetime

    model_config = {"from_attributes": True}


class VaccinationSearchResponse(BaseModel):
    """Paginated vaccination search response."""

    items:        List[VaccinationSearchResult]
    total_count:  int
    page:         int
    page_size:    int
    total_pages:  int
    has_next:     bool
    has_previous: bool
    query_time_ms: Optional[float] = None

    model_config = {"from_attributes": True}


# ============================================================================
# Payment Search
# ============================================================================


class PaymentSearchFilters(BaseModel):
    """Validated filter parameters for the payment search endpoint."""

    patient_id:          Optional[uuid.UUID] = None
    patient_name:        Optional[str]       = Field(None, max_length=100)
    patient_phone:       Optional[str]       = Field(None, max_length=20)
    vaccine_purchase_id: Optional[uuid.UUID] = None
    payment_method:      Optional[str]       = Field(None, max_length=50)
    payment_date_from:   Optional[date]      = None
    payment_date_to:     Optional[date]      = None
    amount_min:          Optional[Decimal]   = Field(None, ge=0)
    amount_max:          Optional[Decimal]   = Field(None, ge=0)
    received_by_id:      Optional[uuid.UUID] = None
    facility_id:         Optional[uuid.UUID] = None
    reference_number:    Optional[str]       = Field(None, max_length=100)

    @field_validator("patient_name")
    @classmethod
    def validate_search_term(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Search term must be at least 2 characters.")
            dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "\\"]
            for char in dangerous_chars:
                if char in v:
                    raise ValueError(f"Invalid character in search term: {char!r}")
        return v

    @field_validator("patient_phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            allowed = set("0123456789+ ")
            if not all(c in allowed for c in v):
                raise ValueError("Phone can only contain digits, +, and spaces.")
        return v

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: Optional[str]) -> Optional[str]:
        if v:
            valid = {"cash", "mobile_money", "bank_transfer", "card", "cheque"}
            if v.lower() not in valid:
                raise ValueError(
                    f"Invalid payment method. Must be one of: {', '.join(sorted(valid))}."
                )
        return v

    @field_validator("reference_number")
    @classmethod
    def validate_reference(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
            if not all(c.upper() in allowed for c in v):
                raise ValueError("Reference number contains invalid characters.")
        return v

    @field_validator("payment_date_from", "payment_date_to")
    @classmethod
    def validate_date_range(cls, v: Optional[date]) -> Optional[date]:
        if v:
            min_date = datetime.now().date() - timedelta(days=3650)
            if v < min_date:
                raise ValueError("Date range cannot exceed 10 years in the past.")
        return v

    model_config = {"from_attributes": True}


class PaymentSearchResult(BaseModel):
    """Single payment row in a search response."""

    id:                  uuid.UUID
    patient_id:          uuid.UUID
    patient_name:        str
    patient_phone:       str
    vaccine_purchase_id: uuid.UUID
    vaccine_name:        str
    amount:              Decimal
    payment_date:        date
    payment_method:      Optional[str] = None
    reference_number:    Optional[str] = None
    received_by_id:      Optional[uuid.UUID] = None
    notes:               Optional[str] = None
    created_at:          datetime

    model_config = {"from_attributes": True}


class PaymentSearchResponse(BaseModel):
    """Paginated payment search response."""

    items:        List[PaymentSearchResult]
    total_count:  int
    total_amount: Decimal
    page:         int
    page_size:    int
    total_pages:  int
    has_next:     bool
    has_previous: bool
    query_time_ms: Optional[float] = None

    model_config = {"from_attributes": True}