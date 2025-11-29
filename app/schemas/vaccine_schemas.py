from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import uuid
from pydantic import BaseModel, field_validator

from app.schemas.patient_schemas import DoseType, PaymentStatus


# ============= Vaccine Schemas =============
class VaccineBaseSchema(BaseModel):
    """Base schema for vaccine."""

    vaccine_name: str
    price_per_dose: Decimal
    quantity: int
    batch_number: str

    @field_validator("vaccine_name")
    @classmethod
    def validate_vaccine_name(cls, v: str) -> str:
        """Validate vaccine name."""
        if not v or not v.strip():
            raise ValueError("Vaccine name cannot be empty")

        v = v.strip()

        if len(v) < 2 or len(v) > 100:
            raise ValueError("Vaccine name must be between 2 and 100 characters")

        return v

    @field_validator("price_per_dose")
    @classmethod
    def validate_price_per_dose(cls, v: Decimal) -> Decimal:
        """Validate price per dose."""
        if v <= 0:
            raise ValueError("Price per dose must be greater than zero")
        if v > 10000:
            raise ValueError("Price per dose cannot exceed GHS 10,000")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        """Validate quantity."""
        if v < 0:
            raise ValueError("Quantity cannot be negative")
        if v > 100000:
            raise ValueError("Quantity cannot exceed 100,000")
        return v

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, v: str) -> str:
        """Validate batch number."""
        if not v or not v.strip():
            raise ValueError("Batch number cannot be empty")

        v = v.strip()

        if len(v) < 3 or len(v) > 100:
            raise ValueError("Batch number must be between 3 and 100 characters")

        return v

    model_config = {"from_attributes": True}


class VaccineCreateSchema(VaccineBaseSchema):
    """
    Schema for creating a new vaccine.

    Note: added_by_id is automatically populated from authenticated user.
    Do not include this field in the request body.
    """

    # This will be set from authenticated user
    added_by_id: Optional[uuid.UUID] = None
    is_published: bool = False


class VaccineUpdateSchema(BaseModel):
    """Schema for updating a vaccine. All fields are optional."""

    vaccine_name: Optional[str] = None
    price_per_dose: Optional[Decimal] = None
    quantity: Optional[int] = None
    batch_number: Optional[str] = None
    is_published: Optional[bool] = None

    @field_validator("vaccine_name")
    @classmethod
    def validate_vaccine_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate vaccine name."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Vaccine name cannot be empty")

        v = v.strip()

        if len(v) < 2 or len(v) > 100:
            raise ValueError("Vaccine name must be between 2 and 100 characters")

        return v

    @field_validator("price_per_dose")
    @classmethod
    def validate_price_per_dose(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate price per dose."""
        if v is not None:
            if v <= 0:
                raise ValueError("Price per dose must be greater than zero")
            if v > 10000:
                raise ValueError("Price per dose cannot exceed GHS 10,000")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: Optional[int]) -> Optional[int]:
        """Validate quantity."""
        if v is not None:
            if v < 0:
                raise ValueError("Quantity cannot be negative")
            if v > 100000:
                raise ValueError("Quantity cannot exceed 100,000")
        return v

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, v: Optional[str]) -> Optional[str]:
        """Validate batch number."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Batch number cannot be empty")

        v = v.strip()

        if len(v) < 3 or len(v) > 100:
            raise ValueError("Batch number must be between 3 and 100 characters")

        return v

    model_config = {"from_attributes": True}


class VaccineResponseSchema(VaccineBaseSchema):
    """Schema for vaccine response."""

    id: uuid.UUID
    is_published: bool
    added_by_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VaccineStockUpdateSchema(BaseModel):
    """Schema for updating vaccine stock quantity."""

    quantity_to_add: int

    @field_validator("quantity_to_add")
    @classmethod
    def validate_quantity_to_add(cls, v: int) -> int:
        """Validate quantity to add."""
        if v <= 0:
            raise ValueError("Quantity to add must be greater than zero")
        if v > 10000:
            raise ValueError("Cannot add more than 10,000 units at once")
        return v

    model_config = {"from_attributes": True}


class VaccineStockInfoSchema(BaseModel):
    """Schema for vaccine stock information."""

    id: uuid.UUID
    vaccine_name: str
    quantity: int
    is_low_stock: bool
    reserved_quantity: int
    available_quantity: int
    batch_number: str

    model_config = {"from_attributes": True}


class VaccinePublishSchema(BaseModel):
    """Schema for publishing/unpublishing a vaccine."""

    is_published: bool

    model_config = {"from_attributes": True}


# ============= Vaccination Schemas =============
class VaccinationBaseSchema(BaseModel):
    """Base schema for vaccination."""

    vaccine_purchase_id: Optional[uuid.UUID] = None
    dose_number: DoseType = DoseType.FIRST_DOSE
    dose_date: date
    batch_number: Optional[str] = None
    vaccine_name: Optional[str] = None
    vaccine_price: Optional[Decimal] = None
    # Auto-populated from authenticated user
    administered_by_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None

    @field_validator("dose_number")
    @classmethod
    def validate_dose_number(cls, v: str) -> str:
        """Validate dose number."""
        if v not in ["1st dose", "2nd dose", "3rd dose"]:
            raise ValueError("Dose number must be 1st dose, 2nd dose, or 3rd dose")
        return v

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, v: str) -> str:
        """Validate batch number."""
        if not v or not v.strip():
            raise ValueError("Batch number cannot be empty")

        v = v.strip()

        if len(v) < 3 or len(v) > 100:
            raise ValueError("Batch number must be between 3 and 100 characters")

        return v

    @field_validator("vaccine_price")
    @classmethod
    def validate_vaccine_price(cls, v: Decimal) -> Decimal:
        """Validate vaccine price."""
        if v <= 0:
            raise ValueError("Vaccine price must be greater than zero")
        return v

    model_config = {"from_attributes": True}


class VaccinationCreateSchema(VaccinationBaseSchema):
    """
    Schema for creating a new vaccination record.

    Note: patient_id and administered_by_id are auto-populated.
    Do not include patient_id in request body (comes from URL path).
    """

    # This will be set from URL path parameter
    patient_id: Optional[uuid.UUID] = None


class VaccinationUpdateSchema(BaseModel):
    """Schema for updating a vaccination record."""

    dose_date: Optional[date] = None
    batch_number: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class VaccinationResponseSchema(BaseModel):
    """Schema for vaccination response."""

    id: uuid.UUID
    patient_id: uuid.UUID
    vaccine_purchase_id: uuid.UUID
    dose_number: DoseType
    dose_date: date
    batch_number: str
    vaccine_name: str
    vaccine_price: Decimal
    administered_by_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============= Vaccine Purchase Schemas =============
class PatientVaccinePurchaseBaseSchema(BaseModel):
    """Base schema for patient vaccine purchase."""

    vaccine_id: uuid.UUID
    vaccine_name: str
    price_per_dose: Decimal
    total_doses: int = 3
    notes: Optional[str] = None

    @field_validator("price_per_dose")
    @classmethod
    def validate_price_per_dose(cls, v: Decimal) -> Decimal:
        """Validate price per dose."""
        if v <= 0:
            raise ValueError("Price per dose must be greater than zero")
        return v

    @field_validator("total_doses")
    @classmethod
    def validate_total_doses(cls, v: int) -> int:
        """Validate total doses."""
        if v < 1 or v > 10:
            raise ValueError("Total doses must be between 1 and 10")
        return v

    model_config = {"from_attributes": True}


class PatientVaccinePurchaseCreateSchema(BaseModel):
    """
    Schema for creating a patient vaccine purchase.

    Note: patient_id and created_by_id are auto-populated from URL path and authenticated user.
    """

    vaccine_id: uuid.UUID
    patient_id: Optional[uuid.UUID] = None
    total_doses: int
    created_by_id: Optional[uuid.UUID] = None


class PatientVaccinePurchaseUpdateSchema(BaseModel):
    """Schema for updating a patient vaccine purchase."""

    model_config = {"from_attributes": True}


class PatientVaccinePurchaseResponseSchema(BaseModel):
    """Schema for patient vaccine purchase response."""

    id: uuid.UUID
    patient_id: uuid.UUID
    vaccine_id: uuid.UUID
    vaccine_name: str
    price_per_dose: Decimal
    total_doses: int
    total_package_price: Decimal
    amount_paid: Decimal
    balance: Decimal
    payment_status: PaymentStatus
    doses_administered: int
    batch_number: str
    purchase_date: datetime
    is_active: bool
    notes: Optional[str] = None
    created_by_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientVaccinePurchaseProgressSchema(BaseModel):
    """Schema for vaccine purchase progress summary."""

    total_price: float
    amount_paid: float
    balance: float
    payment_status: str
    total_doses: int
    doses_paid_for: int
    doses_administered: int
    eligible_doses: int
    is_completed: bool

    model_config = {"from_attributes": True}


# ============= Payment Schemas =============
class PaymentBaseSchema(BaseModel):
    """Base schema for payment."""

    amount: Decimal
    payment_date: date
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Validate payment amount."""
        if v <= 0:
            raise ValueError("Payment amount must be greater than zero")
        return v

    model_config = {"from_attributes": True}


class PaymentCreateSchema(PaymentBaseSchema):
    """
    Schema for creating a payment.

    Note: vaccine_purchase_id and received_by_id are auto-populated.
    """

    # These will be set from URL path parameter and authenticated user
    vaccine_purchase_id: Optional[uuid.UUID] = None
    received_by_id: Optional[uuid.UUID] = None


class PaymentResponseSchema(PaymentBaseSchema):
    """Schema for payment response."""

    id: uuid.UUID
    vaccine_purchase_id: uuid.UUID
    received_by_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}
