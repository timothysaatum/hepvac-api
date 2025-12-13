from datetime import date, datetime
from enum import Enum
import re
from typing import Dict, Optional
import uuid
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from pydantic import BaseModel, field_validator


class PatientType(str, Enum):
    """Patient type enumeration"""

    REGULAR = "regular"
    PREGNANT = "pregnant"


class PatientStatus(str, Enum):
    """Patient status enumeration"""

    ACTIVE = "active"
    POSTPARTUM = "postpartum"
    COMPLETED = "completed"
    INACTIVE = "inactive"


class Sex(str, Enum):
    """Sex enumeration"""

    MALE = "male"
    FEMALE = "female"


class PaymentStatus(str, Enum):
    """Payment status enumeration"""

    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class DoseType(str, Enum):
    FIRST_DOSE = "1st dose"
    SECOND_DOSE = "2nd dose"
    THIRD_DOSE = "3rd dose"


class ReminderType(str, Enum):
    """Reminder type enumeration"""

    DELIVERY_WEEK = "delivery_week"
    CHILD_6MONTH_CHECKUP = "child_6month_checkup"
    MEDICATION_DUE = "medication_due"
    PAYMENT_DUE = "payment_due"
    VACCINATION_DUE = "vaccination_due"


class ReminderStatus(str, Enum):
    """Reminder status enumeration"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============= PostgreSQL ENUM Types (Reusable) =============
sex_enum_type = PGENUM(
    Sex,
    name='sex',
    create_type=False
)

patient_type_enum = PGENUM(
    PatientType,
    name='patienttype',
    create_type=False
)

patient_status_enum = PGENUM(
    PatientStatus,
    name='patientstatus',
    create_type=False
)

dose_type_enum = PGENUM(
    DoseType,
    name='dosetype',
    create_type=False
)

reminder_type_enum = PGENUM(
    ReminderType,
    name='remindertype',
    create_type=False
)

reminder_status_enum = PGENUM(
    ReminderStatus,
    name='reminderstatus',
    create_type=False
)


# ============= Helper Schemas for Names =============
class FacilityInfoSchema(BaseModel):
    """Schema for facility information"""
    id: uuid.UUID
    name: str
    model_config = {"from_attributes": True}


class UserInfoSchema(BaseModel):
    """Schema for user information"""
    id: uuid.UUID
    name: str
    model_config = {"from_attributes": True}


# ============= Base Patient Schemas =============
class PatientBaseSchema(BaseModel):
    """Base schema for patient with common fields."""

    name: str
    phone: str
    sex: Sex
    age: int
    date_of_birth: Optional[date] = None
    facility_id: Optional[uuid.UUID] = None
    created_by_id: Optional[uuid.UUID] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name format."""
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")

        v = v.strip()

        if len(v) < 2 or len(v) > 255:
            raise ValueError("Name must be between 2 and 255 characters long")

        if any(char.isdigit() for char in v):
            raise ValueError("Name must not contain numbers")

        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate phone number format."""
        if not v or not v.strip():
            raise ValueError("Phone number is required")

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

    @field_validator("age")
    @classmethod
    def validate_age(cls, v: int) -> int:
        """Validate age."""
        if v < 0 or v > 150:
            raise ValueError("Age must be between 0 and 150")

        return v

    model_config = {"from_attributes": True}


# ============= Pregnant Patient Schemas =============
class PregnantPatientBaseSchema(PatientBaseSchema):
    """Base schema for pregnant patient."""

    sex: Sex = Sex.FEMALE
    expected_delivery_date: Optional[date] = None

    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        if v < 10:
            raise ValueError("Pregant woman age must not below 10")
        return v


class PregnantPatientCreateSchema(PregnantPatientBaseSchema):
    """
    Schema for creating a new pregnant patient.

    Note: facility_id and created_by_id are automatically populated from authenticated user.
    Do not include these fields in the request body.
    """

    pass


class PregnantPatientUpdateSchema(BaseModel):
    """Schema for updating a pregnant patient. All fields are optional."""

    name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    expected_delivery_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None
    status: Optional[PatientStatus] = None
    updated_by_id: Optional[uuid.UUID] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate name format."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Name cannot be empty")

        v = v.strip()

        if len(v) < 2 or len(v) > 255:
            raise ValueError("Name must be between 2 and 255 characters long")

        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format."""
        if v is None:
            return v

        v = v.strip()

        if not re.match(r"^\+?\d{10,15}$", v):
            raise ValueError(
                "Phone number must be 10-15 digits, optionally starting with '+'"
            )

        return v

    model_config = {"from_attributes": True}


class PregnantPatientResponseSchema(BaseModel):
    """Schema for pregnant patient response."""

    id: uuid.UUID
    name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    sex: Sex
    patient_type: str
    status: PatientStatus
    expected_delivery_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None
    
    # Nested objects with id and name
    facility: Optional[FacilityInfoSchema] = None
    created_by: Optional[UserInfoSchema] = None
    updated_by: Optional[UserInfoSchema] = None
    
    created_at: datetime
    updated_at: datetime
    links: Dict[str, str]
    
    model_config = {"from_attributes": True}

    @classmethod
    def from_patient(cls, patient):
        """Create schema including HATEOAS links."""
        base_id = str(patient.id)
        
        # Extract facility and user information
        facility_info = None
        if patient.facility:
            facility_info = FacilityInfoSchema(
                id=patient.facility.id,
                name=patient.facility.facility_name
            )
        
        created_by_info = None
        if patient.created_by:
            created_by_info = UserInfoSchema(
                id=patient.created_by.id,
                name=patient.created_by.full_name or patient.created_by.username
            )
        
        updated_by_info = None
        if patient.updated_by:
            updated_by_info = UserInfoSchema(
                id=patient.updated_by.id,
                name=patient.updated_by.full_name or patient.updated_by.username
            )
        
        return cls(
            id=patient.id,
            name=patient.name,
            phone=patient.phone,
            age=patient.age,
            sex=patient.sex,
            patient_type=patient.patient_type,
            status=patient.status,
            expected_delivery_date=getattr(patient, 'expected_delivery_date', None),
            actual_delivery_date=getattr(patient, 'actual_delivery_date', None),
            facility=facility_info,
            created_by=created_by_info,
            updated_by=updated_by_info,
            created_at=patient.created_at,
            updated_at=patient.updated_at,
            links={
                "purchase_vaccine": f"/api/v1/purchase-vaccine/{base_id}",
                "update_patient": (
                    f"/api/v1/patients/pregnant/{base_id}"
                    if patient.patient_type == PatientType.PREGNANT.value
                    else f"/api/v1/patients/regular/{base_id}"
                ),
                "convert_to_regular": f"/api/v1/patients/pregnant/{base_id}/convert",
                "create_regular_patient": "/api/v1/patients/regular",
                "get_patient": (
                    f"/api/v1/patients/regular/{base_id}"
                    if patient.patient_type == PatientType.REGULAR.value
                    else f"/api/v1/patients/pregnant/{base_id}"
                ),
                "delete_patient": f"/api/v1/patients/{base_id}",
            },
        )


# ============= Regular Patient Schemas =============
class RegularPatientBaseSchema(PatientBaseSchema):
    """Base schema for regular patient."""

    diagnosis_date: Optional[date] = None
    viral_load: Optional[str] = None
    last_viral_load_date: Optional[date] = None
    treatment_start_date: Optional[date] = None
    treatment_regimen: Optional[str] = None
    medical_history: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None


class RegularPatientCreateSchema(RegularPatientBaseSchema):
    """
    Schema for creating a new regular patient.

    Note: facility_id and created_by_id are automatically populated from authenticated user.
    Do not include these fields in the request body.
    """

    pass


class RegularPatientUpdateSchema(BaseModel):
    """Schema for updating a regular patient. All fields are optional."""

    name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    date_of_birth: Optional[date] = None
    diagnosis_date: Optional[date] = None
    viral_load: Optional[str] = None
    last_viral_load_date: Optional[date] = None
    treatment_start_date: Optional[date] = None
    treatment_regimen: Optional[str] = None
    medical_history: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[PatientStatus] = None
    updated_by_id: Optional[uuid.UUID] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate name format."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Name cannot be empty")

        v = v.strip()

        if len(v) < 2 or len(v) > 255:
            raise ValueError("Name must be between 2 and 255 characters long")

        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format."""
        if v is None:
            return v

        v = v.strip()

        if not re.match(r"^\+?\d{10,15}$", v):
            raise ValueError(
                "Phone number must be 10-15 digits, optionally starting with '+'"
            )

        return v

    model_config = {"from_attributes": True}


class RegularPatientResponseSchema(BaseModel):
    """Schema for regular patient response."""

    id: uuid.UUID
    name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    sex: Sex
    date_of_birth: Optional[date] = None
    patient_type: str
    status: PatientStatus
    
    # Regular patient specific fields
    diagnosis_date: Optional[date] = None
    viral_load: Optional[str] = None
    last_viral_load_date: Optional[date] = None
    treatment_start_date: Optional[date] = None
    treatment_regimen: Optional[str] = None
    medical_history: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None
    
    # Nested objects with id and name
    facility: Optional[FacilityInfoSchema] = None
    created_by: Optional[UserInfoSchema] = None
    updated_by: Optional[UserInfoSchema] = None
    
    created_at: datetime
    updated_at: datetime
    links: Dict[str, str]

    model_config = {"from_attributes": True}

    @classmethod
    def from_patient(cls, patient):
        """Create schema including HATEOAS links."""
        base_id = str(patient.id)
        
        # Extract facility and user information
        facility_info = None
        if patient.facility:
            facility_info = FacilityInfoSchema(
                id=patient.facility.id,
                name=patient.facility.facility_name
            )
        
        created_by_info = None
        if patient.created_by:
            created_by_info = UserInfoSchema(
                id=patient.created_by.id,
                name=patient.created_by.full_name or patient.created_by.username
            )
        
        updated_by_info = None
        if patient.updated_by:
            updated_by_info = UserInfoSchema(
                id=patient.updated_by.id,
                name=patient.updated_by.full_name or patient.updated_by.username
            )
        
        return cls(
            id=patient.id,
            name=patient.name,
            phone=patient.phone,
            age=patient.age,
            sex=patient.sex,
            date_of_birth=getattr(patient, 'date_of_birth', None),
            patient_type=patient.patient_type,
            status=patient.status,
            diagnosis_date=getattr(patient, 'diagnosis_date', None),
            viral_load=getattr(patient, 'viral_load', None),
            last_viral_load_date=getattr(patient, 'last_viral_load_date', None),
            treatment_start_date=getattr(patient, 'treatment_start_date', None),
            treatment_regimen=getattr(patient, 'treatment_regimen', None),
            medical_history=getattr(patient, 'medical_history', None),
            allergies=getattr(patient, 'allergies', None),
            notes=getattr(patient, 'notes', None),
            facility=facility_info,
            created_by=created_by_info,
            updated_by=updated_by_info,
            created_at=patient.created_at,
            updated_at=patient.updated_at,
            links={
                "purchase_vaccine": f"/api/v1/purchase-vaccine/{base_id}",
                "update_patient": (
                    f"/api/v1/patients/pregnant/{base_id}"
                    if patient.patient_type == PatientType.PREGNANT.value
                    else f"/api/v1/patients/regular/{base_id}"
                ),
                "get_patient": (
                    f"/api/v1/patients/regular/{base_id}"
                    if patient.patient_type == PatientType.REGULAR.value
                    else f"/api/v1/patients/pregnant/{base_id}"
                ),
                "delete_patient": f"/api/v1/patients/{base_id}",
            },
        )


# ============= Child Schemas =============
class ChildBaseSchema(BaseModel):
    """Base schema for child."""

    name: Optional[str] = None
    date_of_birth: date
    sex: Optional[Sex] = None
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate child name."""
        if v is not None:
            v = v.strip()
            if v and (len(v) < 2 or len(v) > 255):
                raise ValueError("Name must be between 2 and 255 characters long")
        return v

    model_config = {"from_attributes": True}


class ChildCreateSchema(ChildBaseSchema):
    """
    Schema for creating a new child record.

    Note: mother_id is auto-populated from URL path parameter.
    """

    mother_id: Optional[uuid.UUID] = None


class ChildUpdateSchema(BaseModel):
    """Schema for updating a child record."""

    name: Optional[str] = None
    sex: Optional[Sex] = None
    six_month_checkup_date: Optional[date] = None
    six_month_checkup_completed: Optional[bool] = None
    hep_b_antibody_test_result: Optional[str] = None
    test_date: Optional[date] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ChildResponseSchema(ChildBaseSchema):
    """Schema for child response."""

    id: uuid.UUID
    mother_id: uuid.UUID
    six_month_checkup_date: Optional[date] = None
    six_month_checkup_completed: bool
    hep_b_antibody_test_result: Optional[str] = None
    test_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============= Prescription Schemas =============
class PrescriptionBaseSchema(BaseModel):
    """Base schema for prescription."""

    medication_name: str
    dosage: str
    frequency: str
    duration_months: int = 6
    prescription_date: date
    start_date: date
    end_date: Optional[date] = None
    instructions: Optional[str] = None

    @field_validator("medication_name")
    @classmethod
    def validate_medication_name(cls, v: str) -> str:
        """Validate medication name."""
        if not v or not v.strip():
            raise ValueError("Medication name cannot be empty")

        v = v.strip()

        if len(v) < 2 or len(v) > 255:
            raise ValueError("Medication name must be between 2 and 255 characters")

        return v

    @field_validator("duration_months")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        """Validate duration."""
        if v < 1 or v > 24:
            raise ValueError("Duration must be between 1 and 24 months")
        return v

    model_config = {"from_attributes": True}


class PrescriptionCreateSchema(PrescriptionBaseSchema):
    """
    Schema for creating a prescription.

    Note: patient_id and prescribed_by_id are auto-populated.
    """

    patient_id: Optional[uuid.UUID] = None
    prescribed_by_id: Optional[uuid.UUID] = None


class PrescriptionUpdateSchema(BaseModel):
    """Schema for updating a prescription."""

    medication_name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration_months: Optional[int] = None
    end_date: Optional[date] = None
    instructions: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = {"from_attributes": True}


class PrescriptionResponseSchema(PrescriptionBaseSchema):
    """Schema for prescription response."""

    id: uuid.UUID
    patient_id: uuid.UUID
    
    # Nested object with id and name
    prescribed_by: Optional[UserInfoSchema] = None
    
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
    
    @classmethod
    def from_prescription(cls, prescription):
        """Create schema with user info."""
        prescribed_by_info = None
        if prescription.prescribed_by:
            prescribed_by_info = UserInfoSchema(
                id=prescription.prescribed_by.id,
                name=prescription.prescribed_by.full_name or prescription.prescribed_by.username
            )
        
        return cls(
            id=prescription.id,
            patient_id=prescription.patient_id,
            prescribed_by=prescribed_by_info,
            medication_name=prescription.medication_name,
            dosage=prescription.dosage,
            frequency=prescription.frequency,
            duration_months=prescription.duration_months,
            prescription_date=prescription.prescription_date,
            start_date=prescription.start_date,
            end_date=prescription.end_date,
            instructions=prescription.instructions,
            is_active=prescription.is_active,
            created_at=prescription.created_at,
            updated_at=prescription.updated_at
        )


# ============= Medication Schedule Schemas =============
class MedicationScheduleBaseSchema(BaseModel):
    """Base schema for medication schedule."""

    medication_name: str
    scheduled_date: date
    quantity_purchased: Optional[int] = None
    months_supply: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("quantity_purchased", "months_supply")
    @classmethod
    def validate_positive_integer(cls, v: Optional[int]) -> Optional[int]:
        """Validate positive integers."""
        if v is not None and v < 1:
            raise ValueError("Value must be at least 1")
        return v

    model_config = {"from_attributes": True}


class MedicationScheduleCreateSchema(MedicationScheduleBaseSchema):
    """
    Schema for creating a medication schedule.

    Note: patient_id is auto-populated from URL path parameter.
    """

    patient_id: Optional[uuid.UUID] = None


class MedicationScheduleUpdateSchema(BaseModel):
    """Schema for updating a medication schedule."""

    quantity_purchased: Optional[int] = None
    months_supply: Optional[int] = None
    next_dose_due_date: Optional[date] = None
    is_completed: Optional[bool] = None
    completed_date: Optional[date] = None
    lab_review_scheduled: Optional[bool] = None
    lab_review_date: Optional[date] = None
    lab_review_completed: Optional[bool] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class MedicationScheduleResponseSchema(MedicationScheduleBaseSchema):
    """Schema for medication schedule response."""

    id: uuid.UUID
    patient_id: uuid.UUID
    next_dose_due_date: Optional[date] = None
    is_completed: bool
    completed_date: Optional[date] = None
    lab_review_scheduled: bool
    lab_review_date: Optional[date] = None
    lab_review_completed: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============= Reminder Schemas =============
class PatientReminderBaseSchema(BaseModel):
    """Base schema for patient reminder."""

    reminder_type: ReminderType
    scheduled_date: date
    message: str
    child_id: Optional[uuid.UUID] = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate reminder message."""
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")

        v = v.strip()

        if len(v) < 10:
            raise ValueError("Message must be at least 10 characters long")

        return v

    model_config = {"from_attributes": True}


class PatientReminderCreateSchema(PatientReminderBaseSchema):
    """
    Schema for creating a patient reminder.

    Note: patient_id is auto-populated from URL path parameter.
    """

    patient_id: Optional[uuid.UUID] = None


class PatientReminderUpdateSchema(BaseModel):
    """Schema for updating a patient reminder."""

    scheduled_date: Optional[date] = None
    message: Optional[str] = None
    status: Optional[ReminderStatus] = None

    model_config = {"from_attributes": True}


class PatientReminderResponseSchema(PatientReminderBaseSchema):
    """Schema for patient reminder response."""

    id: uuid.UUID
    patient_id: uuid.UUID
    status: ReminderStatus
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============= Conversion Schema =============
class ConvertToRegularPatientSchema(BaseModel):
    """Schema for converting pregnant patient to regular patient."""

    actual_delivery_date: date
    treatment_regimen: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


# =============== Diagnosis Schema =============
class DiagnosisBaseSchema(BaseModel):
    patient_id: uuid.UUID
    diagnose_by_id: uuid.UUID
    history: Optional[str] = None
    preliminary_diagnosis: Optional[str] = None
    model_config = {"from_attributes": True}


class DiagnosisCreateSchema(DiagnosisBaseSchema):
    pass


class DiagnosisResponseSchema(BaseModel):
    """Schema for diagnosis response."""
    
    id: uuid.UUID
    patient_id: uuid.UUID
    
    # Nested object with id and name
    diagnose_by: Optional[UserInfoSchema] = None
    
    history: Optional[str] = None
    preliminary_diagnosis: Optional[str] = None
    actual_diagnosis: Optional[str] = None
    diagnosed_on: datetime
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None
    updated_at: datetime
    
    model_config = {"from_attributes": True}
    
    @classmethod
    def from_diagnosis(cls, diagnosis):
        """Create schema with user info."""
        diagnose_by_info = None
        if diagnosis.diagnose_by:
            diagnose_by_info = UserInfoSchema(
                id=diagnosis.diagnose_by.id,
                name=diagnosis.diagnose_by.full_name or diagnosis.diagnose_by.username
            )
        
        return cls(
            id=diagnosis.id,
            patient_id=diagnosis.patient_id,
            diagnose_by=diagnose_by_info,
            history=diagnosis.history,
            preliminary_diagnosis=diagnosis.preliminary_diagnosis,
            actual_diagnosis=diagnosis.actual_diagnosis,
            diagnosed_on=diagnosis.diagnosed_on,
            is_deleted=diagnosis.is_deleted,
            deleted_at=diagnosis.deleted_at,
            updated_at=diagnosis.updated_at
        )


class DiagnosisUpdateSchema(DiagnosisBaseSchema):
    actual_diagnosis: Optional[str] = None
    model_config = {"from_attributes": True}