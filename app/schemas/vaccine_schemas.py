"""
Vaccine and vaccination schemas — request validation and response serialisation
for Vaccine, Vaccination, PatientVaccinePurchase, and Payment.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel, field_validator

from app.schemas.patient_schemas import DoseType, PaymentStatus


# ============================================================================
# Vaccine
# ============================================================================


class VaccineBaseSchema(BaseModel):
    """Base fields for a vaccine master record."""

    vaccine_name:   str
    price_per_dose: Decimal
    quantity:       int
    batch_number:   str

    @field_validator("vaccine_name")
    @classmethod
    def validate_vaccine_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Vaccine name cannot be empty.")
        v = v.strip()
        if len(v) < 2 or len(v) > 100:
            raise ValueError("Vaccine name must be between 2 and 100 characters.")
        return v

    @field_validator("price_per_dose")
    @classmethod
    def validate_price_per_dose(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Price per dose must be greater than zero.")
        if v > 10_000:
            raise ValueError("Price per dose cannot exceed GHS 10,000.")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Quantity cannot be negative.")
        if v > 100_000:
            raise ValueError("Quantity cannot exceed 100,000.")
        return v

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Batch number cannot be empty.")
        v = v.strip()
        if len(v) < 3 or len(v) > 100:
            raise ValueError("Batch number must be between 3 and 100 characters.")
        return v

    model_config = {"from_attributes": True}


class VaccineCreateSchema(VaccineBaseSchema):
    """
    Create a new vaccine master record.

    `added_by_id` is populated from the authenticated user — do not include
    in the request body.
    """
    added_by_id:  Optional[uuid.UUID] = None  # set from auth context
    is_published: bool = False


class VaccineUpdateSchema(BaseModel):
    """Update a vaccine master record. All fields optional."""

    vaccine_name:   Optional[str]     = None
    price_per_dose: Optional[Decimal] = None
    quantity:       Optional[int]     = None
    batch_number:   Optional[str]     = None
    is_published:   Optional[bool]    = None

    @field_validator("vaccine_name")
    @classmethod
    def validate_vaccine_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Vaccine name cannot be empty.")
        if len(v) < 2 or len(v) > 100:
            raise ValueError("Vaccine name must be between 2 and 100 characters.")
        return v

    @field_validator("price_per_dose")
    @classmethod
    def validate_price_per_dose(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if v <= 0:
                raise ValueError("Price per dose must be greater than zero.")
            if v > 10_000:
                raise ValueError("Price per dose cannot exceed GHS 10,000.")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if v < 0:
                raise ValueError("Quantity cannot be negative.")
            if v > 100_000:
                raise ValueError("Quantity cannot exceed 100,000.")
        return v

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Batch number cannot be empty.")
        if len(v) < 3 or len(v) > 100:
            raise ValueError("Batch number must be between 3 and 100 characters.")
        return v

    model_config = {"from_attributes": True}


class VaccineResponseSchema(VaccineBaseSchema):
    """Vaccine master record response."""

    id:           uuid.UUID
    is_published: bool
    added_by_id:  Optional[uuid.UUID] = None
    created_at:   datetime

    model_config = {"from_attributes": True}


class VaccineStockUpdateSchema(BaseModel):
    """Add stock to a vaccine."""

    quantity_to_add: int

    @field_validator("quantity_to_add")
    @classmethod
    def validate_quantity_to_add(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Quantity to add must be greater than zero.")
        if v > 10_000:
            raise ValueError("Cannot add more than 10,000 units at once.")
        return v

    model_config = {"from_attributes": True}


class VaccineStockInfoSchema(BaseModel):
    """Stock-level summary for a vaccine."""

    id:                 uuid.UUID
    vaccine_name:       str
    quantity:           int
    is_low_stock:       bool
    reserved_quantity:  int
    available_quantity: int
    batch_number:       str

    model_config = {"from_attributes": True}


class VaccinePublishSchema(BaseModel):
    """Publish or u>npublish a vaccine."""

    is_published: bool

    model_config = {"from_attributes": True}


# ============================================================================
# Vaccination
# ============================================================================


class VaccinationBaseSchema(BaseModel):
    """Base fields for a vaccination (dose administration) record."""

    vaccine_purchase_id: Optional[uuid.UUID] = None
    dose_number:         DoseType            = DoseType.FIRST_DOSE
    dose_date:           date
    batch_number:        Optional[str]       = None
    vaccine_name:        Optional[str]       = None
    vaccine_price:       Optional[Decimal]   = None
    administered_by_id:  Optional[uuid.UUID] = None   # set from auth context
    notes:               Optional[str]       = None

    @field_validator("dose_number")
    @classmethod
    def validate_dose_number(cls, v: DoseType) -> DoseType:
        # FIX: was comparing a DoseType enum value to raw strings using `not in
        # ("1st dose", ...)`. Pydantic coerces the input to DoseType before
        # the validator runs, so `v` is already a DoseType instance — the
        # string comparison would always fail for valid enum members because
        # DoseType("1st dose") != "1st dose". The correct check is against
        # enum members.
        valid = {DoseType.FIRST_DOSE, DoseType.SECOND_DOSE, DoseType.THIRD_DOSE}
        if v not in valid:
            raise ValueError(
                f"Dose number must be one of: "
                f"{', '.join(d.value for d in valid)}."
            )
        return v

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Batch number cannot be empty.")
        if len(v) < 3 or len(v) > 100:
            raise ValueError("Batch number must be between 3 and 100 characters.")
        return v

    @field_validator("vaccine_price")
    @classmethod
    def validate_vaccine_price(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Vaccine price must be greater than zero.")
        return v

    model_config = {"from_attributes": True}


class VaccinationCreateSchema(VaccinationBaseSchema):
    """
    Create a vaccination record.

    `patient_id` is populated from the URL path parameter.
    `administered_by_id` is populated from the authenticated user.
    Do not include these in the request body.
    """
    patient_id: Optional[uuid.UUID] = None   # set from URL path


class VaccinationUpdateSchema(BaseModel):
    """Update a vaccination record."""

    dose_date:    Optional[date] = None
    batch_number: Optional[str] = None
    notes:        Optional[str] = None

    model_config = {"from_attributes": True}


class VaccinationResponseSchema(BaseModel):
    """Vaccination record response."""

    id:                  uuid.UUID
    patient_id:          uuid.UUID
    vaccine_purchase_id: uuid.UUID
    dose_number:         DoseType
    dose_date:           date
    batch_number:        str
    vaccine_name:        str
    vaccine_price:       Decimal
    administered_by_id:  Optional[uuid.UUID] = None
    notes:               Optional[str]       = None
    created_at:          datetime

    model_config = {"from_attributes": True}


# ============================================================================
# Patient Vaccine Purchase
# ============================================================================


class PatientVaccinePurchaseBaseSchema(BaseModel):
    """Base fields for a vaccine purchase."""

    vaccine_id:     uuid.UUID
    vaccine_name:   str
    price_per_dose: Decimal
    total_doses:    int = 3
    notes:          Optional[str] = None

    @field_validator("price_per_dose")
    @classmethod
    def validate_price_per_dose(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Price per dose must be greater than zero.")
        return v

    @field_validator("total_doses")
    @classmethod
    def validate_total_doses(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("Total doses must be between 1 and 10.")
        return v

    model_config = {"from_attributes": True}


class PatientVaccinePurchaseCreateSchema(BaseModel):
    """
    Create a vaccine purchase for a patient.

    `patient_id` and `created_by_id` are auto-populated from the URL path
    and authenticated user respectively — do not include in the request body.
    """
    vaccine_id:    uuid.UUID
    patient_id:    Optional[uuid.UUID] = None   # set from URL path
    total_doses:   int
    created_by_id: Optional[uuid.UUID] = None   # set from auth context


class PatientVaccinePurchaseUpdateSchema(BaseModel):
    """Update a vaccine purchase (currently no editable fields via API)."""
    model_config = {"from_attributes": True}


class PatientVaccinePurchaseResponseSchema(BaseModel):
    """Vaccine purchase response."""

    id:                  uuid.UUID
    patient_id:          uuid.UUID
    vaccine_id:          uuid.UUID
    vaccine_name:        str
    price_per_dose:      Decimal
    total_doses:         int
    total_package_price: Decimal
    amount_paid:         Decimal
    balance:             Decimal
    payment_status:      PaymentStatus
    doses_administered:  int
    batch_number:        str
    purchase_date:       datetime
    is_active:           bool
    notes:               Optional[str]       = None
    created_by_id:       Optional[uuid.UUID] = None
    created_at:          datetime
    updated_at:          datetime

    model_config = {"from_attributes": True}


class PatientVaccinePurchaseProgressSchema(BaseModel):
    """
    Payment and dose progress summary for a vaccine purchase.

    FIX: monetary fields changed from `float` to `Decimal`.
    The model's get_payment_progress() returns str representations of Decimal
    values to avoid IEEE 754 precision loss. Pydantic correctly coerces
    those str values to Decimal here.
    """

    total_price:        Decimal   # was float — precision loss on monetary values
    amount_paid:        Decimal   # was float
    balance:            Decimal   # was float
    payment_status:     str
    total_doses:        int
    doses_paid_for:     int
    doses_administered: int
    eligible_doses:     int
    is_completed:       bool

    model_config = {"from_attributes": True}


# ============================================================================
# Payment
# ============================================================================


class PaymentBaseSchema(BaseModel):
    """Base fields for a payment transaction."""

    amount:           Decimal
    payment_date:     date
    payment_method:   Optional[str] = None
    reference_number: Optional[str] = None
    notes:            Optional[str] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Payment amount must be greater than zero.")
        return v

    model_config = {"from_attributes": True}


class PaymentCreateSchema(PaymentBaseSchema):
    """
    Create a payment against a vaccine purchase.

    `vaccine_purchase_id` and `received_by_id` are populated from the URL path
    and authenticated user — do not include in the request body.
    `patient_id` is also populated from the URL path (or resolved from the
    purchase) — do not include in the request body.
    """
    vaccine_purchase_id: Optional[uuid.UUID] = None   # set from URL path
    # FIX: added patient_id — Payment model now has a direct patient_id FK
    # for efficient billing queries and row-level security.
    patient_id:          Optional[uuid.UUID] = None   # set from URL path / service
    received_by_id:      Optional[uuid.UUID] = None   # set from auth context


class PaymentResponseSchema(PaymentBaseSchema):
    """Payment transaction response."""

    id:                  uuid.UUID
    vaccine_purchase_id: uuid.UUID
    # FIX: added patient_id — Payment model now carries a direct patient_id FK.
    # Exposing it in the response allows API consumers to navigate directly to
    # the patient without an extra round-trip through the purchase.
    patient_id:          uuid.UUID
    received_by_id:      Optional[uuid.UUID] = None
    created_at:          datetime

    model_config = {"from_attributes": True}