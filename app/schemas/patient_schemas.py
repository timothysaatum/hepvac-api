"""
Patient schemas — Pydantic models for request validation and response serialisation.

Covers: Patient (base), PregnantPatient, RegularPatient, Pregnancy,
        Child, Diagnosis, Prescription, MedicationSchedule, PatientReminder.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import re
from typing import TYPE_CHECKING, Dict, List, Optional
import uuid

from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy.dialects.postgresql import ENUM as PGENUM

if TYPE_CHECKING:
    from app.models.patient_model import Child, Diagnosis, PatientLabResult, PatientLabTest, PregnantPatient, Prescription, RegularPatient

# ============================================================================
# Enumerations
# ============================================================================


class PatientType(str, Enum):
    REGULAR  = "regular"
    PREGNANT = "pregnant"


class PatientStatus(str, Enum):
    ACTIVE     = "active"
    POSTPARTUM = "postpartum"
    COMPLETED  = "completed"
    INACTIVE   = "inactive"
    CONVERTED  = "converted"


class Sex(str, Enum):
    MALE   = "male"
    FEMALE = "female"


class PaymentStatus(str, Enum):
    PENDING   = "pending"
    PARTIAL   = "partial"
    COMPLETED = "completed"
    OVERDUE   = "overdue"


class DoseType(str, Enum):
    FIRST_DOSE  = "1st dose"
    SECOND_DOSE = "2nd dose"
    THIRD_DOSE  = "3rd dose"


class ReminderType(str, Enum):
    DELIVERY_WEEK        = "delivery_week"
    CHILD_6MONTH_CHECKUP = "child_6month_checkup"
    MEDICATION_DUE       = "medication_due"
    PAYMENT_DUE          = "payment_due"
    VACCINATION_DUE      = "vaccination_due"


class ReminderStatus(str, Enum):
    PENDING   = "pending"
    SENT      = "sent"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class PregnancyOutcome(str, Enum):
    """Clinical outcome of a pregnancy episode."""
    LIVE_BIRTH  = "live_birth"
    STILLBIRTH  = "stillbirth"
    MISCARRIAGE = "miscarriage"
    ABORTION    = "abortion"
    ECTOPIC     = "ectopic"


class HepBTestResult(str, Enum):
    """
    Allowable values for a child's Hep-B antibody test result.

    Constrained to prevent free-text variants ("pos", "Positive", "reactive")
    from entering the column and breaking downstream reporting.
    """
    POSITIVE      = "positive"
    NEGATIVE      = "negative"
    INDETERMINATE = "indeterminate"
    PENDING       = "pending"


class LabTestType(str, Enum):
    HEP_B = "hep_b"
    RFT   = "rft"
    LFT   = "lft"


class LabTestStatus(str, Enum):
    ORDERED    = "ordered"
    IN_PROGRESS = "in_progress"
    COMPLETED  = "completed"
    CANCELLED  = "cancelled"


class LabResultFlag(str, Enum):
    NORMAL        = "normal"
    LOW           = "low"
    HIGH          = "high"
    CRITICAL_LOW  = "critical_low"
    CRITICAL_HIGH = "critical_high"
    ABNORMAL      = "abnormal"


# ============================================================================
# PostgreSQL ENUM column types (reused in ORM model definitions)
# ============================================================================

sex_enum_type = PGENUM(
    Sex, name="sex", create_type=False
)
patient_type_enum = PGENUM(
    PatientType, name="patienttype", create_type=False
)
patient_status_enum = PGENUM(
    PatientStatus, name="patientstatus", create_type=False
)
dose_type_enum = PGENUM(
    DoseType, name="dosetype", create_type=False
)
reminder_type_enum = PGENUM(
    ReminderType, name="remindertype", create_type=False
)
reminder_status_enum = PGENUM(
    ReminderStatus, name="reminderstatus", create_type=False
)
pregnancy_outcome_enum = PGENUM(
    PregnancyOutcome,
    name="pregnancy_outcome",
    create_type=False,
)
hep_b_test_result_enum = PGENUM(
    HepBTestResult,
    name="hep_b_test_result",
    create_type=False,
)
lab_test_type_enum = PGENUM(
    LabTestType,
    name="lab_test_type",
    create_type=False,
)
lab_test_status_enum = PGENUM(
    LabTestStatus,
    name="lab_test_status",
    create_type=False,
)
lab_result_flag_enum = PGENUM(
    LabResultFlag,
    name="lab_result_flag",
    create_type=False,
)


# ============================================================================
# Shared sub-schemas (used as nested objects in responses)
# ============================================================================


class FacilityInfoSchema(BaseModel):
    """Compact facility reference used inside patient responses."""
    id:   uuid.UUID
    name: str          # maps from Facility.facility_name in from_* methods
    model_config = {"from_attributes": True}


class UserInfoSchema(BaseModel):
    """Compact user reference used inside patient responses."""
    id:   uuid.UUID
    name: str          # maps from User.full_name or User.username
    model_config = {"from_attributes": True}


class PatientIdentifierSchema(BaseModel):
    id: Optional[uuid.UUID] = None
    identifier_type: str
    identifier_value: str
    issuer: Optional[str] = None
    is_primary: bool = False

    @field_validator("identifier_type", "identifier_value")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Identifier type and value are required.")
        return v.strip().upper()

    model_config = {"from_attributes": True}


class PatientAllergySchema(BaseModel):
    id: Optional[uuid.UUID] = None
    allergen: str
    reaction: Optional[str] = None
    severity: Optional[str] = "unknown"
    notes: Optional[str] = None
    is_active: bool = True

    @field_validator("allergen")
    @classmethod
    def validate_allergen(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Allergen is required.")
        return v.strip()

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in {"mild", "moderate", "severe", "life_threatening", "unknown"}:
            raise ValueError("Invalid allergy severity.")
        return v

    model_config = {"from_attributes": True}


class PatientAllergyUpdateSchema(BaseModel):
    allergen: Optional[str] = None
    reaction: Optional[str] = None
    severity: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("allergen")
    @classmethod
    def validate_allergen(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("Allergen is required.")
        return v.strip()

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in {"mild", "moderate", "severe", "life_threatening", "unknown"}:
            raise ValueError("Invalid allergy severity.")
        return v

    model_config = {"from_attributes": True}


# ============================================================================
# Base Patient
# ============================================================================


class PatientBaseSchema(BaseModel):
    """
    Base input fields shared by all patient types.

    NOTE: `age` is intentionally absent. Age is a computed @property on the
    model derived from `date_of_birth`. Accepting age as input would be
    meaningless — the model does not store it as a column.
    """

    name:          Optional[str] = None
    first_name:    Optional[str] = None
    last_name:     Optional[str] = None
    preferred_name: Optional[str] = None
    medical_record_number: Optional[str] = None
    phone:         str
    sex:           Sex
    date_of_birth: Optional[date]    = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    identifiers: List[PatientIdentifierSchema] = []
    facility_id:   Optional[uuid.UUID] = None
    created_by_id: Optional[uuid.UUID] = None
    accepts_messaging: bool = False

    @model_validator(mode="after")
    def validate_identity(self):
        if not self.name and not (self.first_name and self.last_name):
            raise ValueError("Provide either name or both first_name and last_name.")
        return self

    @field_validator("name", "first_name", "last_name", "preferred_name", "emergency_contact_name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if len(v) < 2 or len(v) > 255:
            raise ValueError("Name must be between 2 and 255 characters.")
        if any(char.isdigit() for char in v):
            raise ValueError("Name must not contain numbers.")
        return v

    @field_validator("medical_record_number")
    @classmethod
    def validate_mrn(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if not v:
            return None
        if not re.match(r"^[A-Z0-9][A-Z0-9\-_/]{1,63}$", v):
            raise ValueError("Medical record number contains invalid characters.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Phone number is required.")
        raw = v.strip()
        if any(c.isalpha() for c in raw):
            raise ValueError("Phone number must not contain letters.")
        digits = re.sub(r"\D", "", raw)
        if not (10 <= len(digits) <= 15):
            raise ValueError(
                "Phone number must contain 10–15 digits."
            )
        return f"+{digits}"

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        raw = v.strip()
        if any(c.isalpha() for c in raw):
            raise ValueError("Emergency contact phone must not contain letters.")
        digits = re.sub(r"\D", "", raw)
        if not (10 <= len(digits) <= 15):
            raise ValueError("Emergency contact phone must contain 10–15 digits.")
        return f"+{digits}"

    model_config = {"from_attributes": True}


# ============================================================================
# Pregnancy schemas  (NEW)
# ============================================================================


class PregnancyCreateSchema(BaseModel):
    """
    Open a new pregnancy episode for a PregnantPatient.

    Sent alongside or immediately after patient creation for the first pregnancy,
    or standalone when a returning patient becomes pregnant again.

    `patient_id` is populated from the URL path parameter — do not include in
    the request body.
    """

    patient_id:            Optional[uuid.UUID] = None   # set from URL path
    lmp_date:              Optional[date]       = None
    expected_delivery_date: Optional[date]      = None
    gestational_age_weeks: Optional[int]        = None
    risk_factors:          Optional[str]        = None
    notes:                 Optional[str]        = None

    @field_validator("gestational_age_weeks")
    @classmethod
    def validate_gestational_age(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 45):
            raise ValueError("Gestational age must be between 0 and 45 weeks.")
        return v

    @field_validator("expected_delivery_date")
    @classmethod
    def validate_edd(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v < date.today():
            raise ValueError("Expected delivery date cannot be in the past.")
        return v

    model_config = {"from_attributes": True}


class PregnancyUpdateSchema(BaseModel):
    """Update clinical data on an ongoing pregnancy episode."""

    lmp_date:              Optional[date] = None
    expected_delivery_date: Optional[date] = None
    gestational_age_weeks: Optional[int]  = None
    risk_factors:          Optional[str]  = None
    notes:                 Optional[str]  = None

    @field_validator("gestational_age_weeks")
    @classmethod
    def validate_gestational_age(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 45):
            raise ValueError("Gestational age must be between 0 and 45 weeks.")
        return v

    model_config = {"from_attributes": True}


class PregnancyCloseSchema(BaseModel):
    """
    Close an active pregnancy episode with a clinical outcome.

    Used when a pregnancy ends — delivery, loss, or other outcome.
    `increment_para` controls whether the patient's para count is incremented.
    Set to True for LIVE_BIRTH and STILLBIRTH; False for MISCARRIAGE, ABORTION,
    ECTOPIC.
    """

    outcome:        PregnancyOutcome
    delivery_date:  Optional[date] = None   # defaults to today if omitted
    increment_para: bool = True

    @field_validator("delivery_date")
    @classmethod
    def validate_delivery_date(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("Delivery date cannot be in the future.")
        return v

    model_config = {"from_attributes": True}


class PregnancySummarySchema(BaseModel):
    """
    Compact pregnancy summary — used inside PregnantPatientResponseSchema
    so API consumers can see the active pregnancy details without a separate
    call to the pregnancies endpoint.
    """

    id:                    uuid.UUID
    pregnancy_number:      int
    is_active:             bool
    lmp_date:              Optional[date]           = None
    expected_delivery_date: Optional[date]          = None
    actual_delivery_date:  Optional[date]           = None
    gestational_age_weeks: Optional[int]            = None
    outcome:               Optional[PregnancyOutcome] = None

    model_config = {"from_attributes": True}


class PregnancyResponseSchema(BaseModel):
    """Full pregnancy episode response including its children."""

    id:                    uuid.UUID
    patient_id:            uuid.UUID
    pregnancy_number:      int
    is_active:             bool
    lmp_date:              Optional[date]             = None
    expected_delivery_date: Optional[date]            = None
    actual_delivery_date:  Optional[date]             = None
    gestational_age_weeks: Optional[int]              = None
    risk_factors:          Optional[str]              = None
    notes:                 Optional[str]              = None
    outcome:               Optional[PregnancyOutcome] = None
    children:              List["ChildResponseSchema"] = []
    created_at:            datetime
    updated_at:            datetime

    model_config = {"from_attributes": True}


# ============================================================================
# Pregnant Patient
# ============================================================================


class PregnantPatientBaseSchema(PatientBaseSchema):
    """
    Input fields for a pregnant patient.

    Pregnancy-specific fields (expected_delivery_date, gestational_age_weeks,
    etc.) belong in PregnancyCreateSchema — not here. Those fields live on the
    Pregnancy episode, not on PregnantPatient.

    To create a pregnant patient with their first pregnancy in one request, use
    PregnantPatientCreateSchema which embeds a PregnancyCreateSchema.
    """

    # Pregnancy registration is restricted to female patients. Clinical edge
    # cases should be modeled explicitly instead of weakening this registry rule.
    sex: Sex = Sex.FEMALE

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: Sex) -> Sex:
        if v != Sex.FEMALE:
            raise ValueError("Pregnant patients must have sex recorded as female.")
        return v


class PregnantPatientCreateSchema(PregnantPatientBaseSchema):
    """
    Create a new pregnant patient together with her first pregnancy episode.

    `facility_id` and `created_by_id` are populated from the authenticated user
    — do not include in the request body.

    `first_pregnancy` is required: you must always open a pregnancy episode when
    registering a pregnant patient.
    """

    first_pregnancy: PregnancyCreateSchema

    model_config = {"from_attributes": True}


class PregnantPatientUpdateSchema(BaseModel):
    """
    Update patient-level fields on a PregnantPatient.

    To update pregnancy data (dates, gestational age, risk factors) use the
    PATCH /pregnancies/{pregnancy_id} endpoint with PregnancyUpdateSchema.
    To close a pregnancy use POST /pregnancies/{pregnancy_id}/close with
    PregnancyCloseSchema.
    """

    name:          Optional[str]           = None
    first_name:    Optional[str]           = None
    last_name:     Optional[str]           = None
    preferred_name: Optional[str]          = None
    medical_record_number: Optional[str]   = None
    phone:         Optional[str]           = None
    date_of_birth: Optional[date]          = None
    address_line: Optional[str]            = None
    city: Optional[str]                    = None
    district: Optional[str]                = None
    region: Optional[str]                  = None
    country: Optional[str]                 = None
    emergency_contact_name: Optional[str]  = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    status:        Optional[PatientStatus] = None
    accepts_messaging: Optional[bool]      = None
    updated_by_id: Optional[uuid.UUID]     = None

    @field_validator("name", "first_name", "last_name", "preferred_name", "emergency_contact_name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty.")
        if len(v) < 2 or len(v) > 255:
            raise ValueError("Name must be between 2 and 255 characters.")
        return v

    @field_validator("medical_record_number")
    @classmethod
    def validate_mrn(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if not v:
            return None
        if not re.match(r"^[A-Z0-9][A-Z0-9\-_/]{1,63}$", v):
            raise ValueError("Medical record number contains invalid characters.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        raw = v.strip()
        if any(c.isalpha() for c in raw):
            raise ValueError("Phone number must not contain letters.")
        digits = re.sub(r"\D", "", raw)
        if not (10 <= len(digits) <= 15):
            raise ValueError(
                "Phone number must contain 10–15 digits."
            )
        return f"+{digits}"

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        raw = v.strip()
        if any(c.isalpha() for c in raw):
            raise ValueError("Emergency contact phone must not contain letters.")
        digits = re.sub(r"\D", "", raw)
        if not (10 <= len(digits) <= 15):
            raise ValueError("Emergency contact phone must contain 10–15 digits.")
        return f"+{digits}"

    model_config = {"from_attributes": True}


class PregnantPatientResponseSchema(BaseModel):
    """
    Full response for a pregnant patient.

    Includes the active pregnancy summary (if any) and full pregnancy history
    so API consumers always have the current obstetric context without a
    separate round-trip.
    """

    id:           uuid.UUID
    name:         Optional[str]        = None
    first_name:   Optional[str]        = None
    last_name:    Optional[str]        = None
    preferred_name: Optional[str]      = None
    medical_record_number: Optional[str] = None
    phone:        Optional[str]        = None
    age:          Optional[int]        = None
    sex:          Sex
    date_of_birth: Optional[date]      = None
    patient_type: str
    status:       PatientStatus
    accepts_messaging: bool
    address_line: Optional[str]        = None
    city: Optional[str]                = None
    district: Optional[str]            = None
    region: Optional[str]              = None
    country: Optional[str]             = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    identifiers: List[PatientIdentifierSchema] = []
    gravida:      int
    para:         int

    # Active pregnancy summary — None if no current pregnancy.
    active_pregnancy: Optional[PregnancySummarySchema] = None

    # Compact history list — full detail available via GET /pregnancies/{id}.
    pregnancy_history: List[PregnancySummarySchema] = []

    # Audit
    facility:    Optional[FacilityInfoSchema] = None
    created_by:  Optional[UserInfoSchema]     = None
    updated_by:  Optional[UserInfoSchema]     = None
    created_at:  datetime
    updated_at:  datetime
    links:       Dict[str, str]

    model_config = {"from_attributes": True}

    @classmethod
    def from_patient(cls, patient: "PregnantPatient") -> "PregnantPatientResponseSchema":
        """Build response including HATEOAS links and pregnancy context."""
        base_id = str(patient.id)

        facility_info = None
        if patient.facility:
            facility_info = FacilityInfoSchema(
                id=patient.facility.id,
                name=patient.facility.facility_name,
            )

        created_by_info = None
        if patient.created_by:
            created_by_info = UserInfoSchema(
                id=patient.created_by.id,
                name=patient.created_by.full_name or patient.created_by.username,
            )

        updated_by_info = None
        if patient.updated_by:
            updated_by_info = UserInfoSchema(
                id=patient.updated_by.id,
                name=patient.updated_by.full_name or patient.updated_by.username,
            )

        # Active pregnancy summary — traverses the loaded relationship.
        active_preg_schema = None
        if patient.active_pregnancy:
            active_preg_schema = PregnancySummarySchema.model_validate(
                patient.active_pregnancy
            )

        # Completed pregnancy summaries.
        history_schemas = [
            PregnancySummarySchema.model_validate(p)
            for p in patient.pregnancy_history
        ]

        return cls(
            id=patient.id,
            name=patient.name,
            first_name=patient.first_name,
            last_name=patient.last_name,
            preferred_name=patient.preferred_name,
            medical_record_number=patient.medical_record_number,
            phone=patient.phone,
            age=patient.age,   # computed property
            sex=patient.sex,
            date_of_birth=patient.date_of_birth,
            patient_type=patient.patient_type,
            status=patient.status,
            accepts_messaging=patient.accepts_messaging,
            address_line=patient.address_line,
            city=patient.city,
            district=patient.district,
            region=patient.region,
            country=patient.country,
            emergency_contact_name=patient.emergency_contact_name,
            emergency_contact_phone=patient.emergency_contact_phone,
            emergency_contact_relationship=patient.emergency_contact_relationship,
            identifiers=[
                PatientIdentifierSchema.model_validate(i)
                for i in getattr(patient, "identifiers", [])
            ],
            gravida=patient.gravida,
            para=patient.para,
            active_pregnancy=active_preg_schema,
            pregnancy_history=history_schemas,
            facility=facility_info,
            created_by=created_by_info,
            updated_by=updated_by_info,
            created_at=patient.created_at,
            updated_at=patient.updated_at,
            links={
                "self":               f"/api/v1/patients/pregnant/{base_id}",
                "update_patient":     f"/api/v1/patients/pregnant/{base_id}",
                "delete_patient":     f"/api/v1/patients/{base_id}",
                "pregnancies":        f"/api/v1/patients/pregnant/{base_id}/pregnancies",
                "open_pregnancy":     f"/api/v1/patients/pregnant/{base_id}/pregnancies",
                "purchase_vaccine":   f"/api/v1/purchase-vaccine/{base_id}",
                "convert_to_regular": f"/api/v1/patients/pregnant/{base_id}/convert",
            },
        )


# ============================================================================
# Regular Patient
# ============================================================================


class RegularPatientBaseSchema(PatientBaseSchema):
    """Identity/contact fields for a regular (non-pregnant) patient."""


class RegularPatientCreateSchema(RegularPatientBaseSchema):
    """
    Create a new regular patient.

    `facility_id` and `created_by_id` are populated from the authenticated user
    — do not include in the request body.
    """
    pass


class RegularPatientUpdateSchema(BaseModel):
    """Update patient-level regular patient fields. All fields optional."""

    name:                Optional[str]           = None
    first_name:          Optional[str]           = None
    last_name:           Optional[str]           = None
    preferred_name:      Optional[str]           = None
    medical_record_number: Optional[str]         = None
    phone:               Optional[str]           = None
    date_of_birth:       Optional[date]          = None
    address_line:        Optional[str]           = None
    city:                Optional[str]           = None
    district:            Optional[str]           = None
    region:              Optional[str]           = None
    country:             Optional[str]           = None
    emergency_contact_name: Optional[str]        = None
    emergency_contact_phone: Optional[str]       = None
    emergency_contact_relationship: Optional[str] = None
    status:              Optional[PatientStatus] = None
    accepts_messaging:   Optional[bool]          = None
    updated_by_id:       Optional[uuid.UUID]     = None

    @field_validator("name", "first_name", "last_name", "preferred_name", "emergency_contact_name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty.")
        if len(v) < 2 or len(v) > 255:
            raise ValueError("Name must be between 2 and 255 characters.")
        return v

    @field_validator("medical_record_number")
    @classmethod
    def validate_mrn(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if not v:
            return None
        if not re.match(r"^[A-Z0-9][A-Z0-9\-_/]{1,63}$", v):
            raise ValueError("Medical record number contains invalid characters.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        raw = v.strip()
        if any(c.isalpha() for c in raw):
            raise ValueError("Phone number must not contain letters.")
        digits = re.sub(r"\D", "", raw)
        if not (10 <= len(digits) <= 15):
            raise ValueError(
                "Phone number must contain 10–15 digits."
            )
        return f"+{digits}"

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        raw = v.strip()
        if any(c.isalpha() for c in raw):
            raise ValueError("Emergency contact phone must not contain letters.")
        digits = re.sub(r"\D", "", raw)
        if not (10 <= len(digits) <= 15):
            raise ValueError("Emergency contact phone must contain 10–15 digits.")
        return f"+{digits}"

    model_config = {"from_attributes": True}


class RegularPatientResponseSchema(BaseModel):
    """Full response for a regular patient."""

    id:                  uuid.UUID
    name:                Optional[str]        = None
    first_name:          Optional[str]        = None
    last_name:           Optional[str]        = None
    preferred_name:      Optional[str]        = None
    medical_record_number: Optional[str]      = None
    phone:               Optional[str]        = None
    age:                 Optional[int]        = None   # computed property — read only
    sex:                 Sex
    date_of_birth:       Optional[date]       = None
    patient_type:        str
    status:              PatientStatus
    accepts_messaging:   bool
    address_line:        Optional[str]        = None
    city:                Optional[str]        = None
    district:            Optional[str]        = None
    region:              Optional[str]        = None
    country:             Optional[str]        = None
    emergency_contact_name: Optional[str]     = None
    emergency_contact_phone: Optional[str]    = None
    emergency_contact_relationship: Optional[str] = None
    identifiers:         List[PatientIdentifierSchema] = []
    facility:            Optional[FacilityInfoSchema] = None
    created_by:          Optional[UserInfoSchema]     = None
    updated_by:          Optional[UserInfoSchema]     = None
    created_at:          datetime
    updated_at:          datetime
    links:               Dict[str, str]

    model_config = {"from_attributes": True}

    @classmethod
    def from_patient(cls, patient: "RegularPatient") -> "RegularPatientResponseSchema":
        """Build response including HATEOAS links."""
        base_id = str(patient.id)

        facility_info = None
        if patient.facility:
            facility_info = FacilityInfoSchema(
                id=patient.facility.id,
                name=patient.facility.facility_name,
            )

        created_by_info = None
        if patient.created_by:
            created_by_info = UserInfoSchema(
                id=patient.created_by.id,
                name=patient.created_by.full_name or patient.created_by.username,
            )

        updated_by_info = None
        if patient.updated_by:
            updated_by_info = UserInfoSchema(
                id=patient.updated_by.id,
                name=patient.updated_by.full_name or patient.updated_by.username,
            )

        return cls(
            id=patient.id,
            name=patient.name,
            first_name=patient.first_name,
            last_name=patient.last_name,
            preferred_name=patient.preferred_name,
            medical_record_number=patient.medical_record_number,
            phone=patient.phone,
            age=patient.age,   # computed property
            sex=patient.sex,
            date_of_birth=patient.date_of_birth,
            patient_type=patient.patient_type,
            status=patient.status,
            accepts_messaging=patient.accepts_messaging,
            address_line=patient.address_line,
            city=patient.city,
            district=patient.district,
            region=patient.region,
            country=patient.country,
            emergency_contact_name=patient.emergency_contact_name,
            emergency_contact_phone=patient.emergency_contact_phone,
            emergency_contact_relationship=patient.emergency_contact_relationship,
            identifiers=[
                PatientIdentifierSchema.model_validate(i)
                for i in getattr(patient, "identifiers", [])
            ],
            facility=facility_info,
            created_by=created_by_info,
            updated_by=updated_by_info,
            created_at=patient.created_at,
            updated_at=patient.updated_at,
            links={
                "self":           f"/api/v1/patients/regular/{base_id}",
                "update_patient": f"/api/v1/patients/regular/{base_id}",
                "delete_patient": f"/api/v1/patients/{base_id}",
                "purchase_vaccine": f"/api/v1/purchase-vaccine/{base_id}",
            },
        )




# ============================================================================
# Polymorphic Patient Response
# ============================================================================

# Used by GET /patients/{patient_id}. FastAPI/Pydantic can serialize either
# response shape depending on the current patient_type discriminator.
class PatientResponseSchema(BaseModel):
    """
    Stable polymorphic response wrapper for GET /patients/{patient_id}.

    Frontend receives a consistent envelope:
    {
        "patient_type": "pregnant" | "regular",
        "data": {...}
    }
    """

    patient_type: PatientType
    data: PregnantPatientResponseSchema | RegularPatientResponseSchema

    model_config = {"from_attributes": True}
# ============================================================================
# Child
# ============================================================================


class ChildBaseSchema(BaseModel):
    """Base fields for a child record."""

    name:          Optional[str] = None
    date_of_birth: date
    sex:           Optional[Sex] = None
    notes:         Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if v and (len(v) < 2 or len(v) > 255):
                raise ValueError("Name must be between 2 and 255 characters.")
        return v

    model_config = {"from_attributes": True}


class ChildCreateSchema(ChildBaseSchema):
    """
    Create a child record linked to a specific pregnancy episode.

    `pregnancy_id` is populated from the URL path parameter.
    Do not include it in the request body.
    """

    pregnancy_id: Optional[uuid.UUID] = None


class ChildUpdateSchema(BaseModel):
    """Update monitoring fields on a child record."""

    name:                        Optional[str]           = None
    sex:                         Optional[Sex]           = None
    six_month_checkup_date:      Optional[date]          = None
    six_month_checkup_completed: Optional[bool]          = None
    hep_b_antibody_test_result:  Optional[HepBTestResult] = None
    test_date:                   Optional[date]          = None
    notes:                       Optional[str]           = None
    updated_by_id:               Optional[uuid.UUID]     = None  # set from auth context

    model_config = {"from_attributes": True}


class ChildResponseSchema(ChildBaseSchema):
    """Child response including pregnancy context and mother reference."""

    id:                          uuid.UUID
    pregnancy_id:                uuid.UUID
    # Convenience field: resolved from pregnancy.patient_id so API consumers
    # can identify the mother without traversing the relationship.
    mother_id:                   Optional[uuid.UUID]     = None
    six_month_checkup_date:      Optional[date]          = None
    six_month_checkup_completed: bool
    hep_b_antibody_test_result:  Optional[HepBTestResult] = None
    test_date:                   Optional[date]          = None
    updated_by:                  Optional[UserInfoSchema] = None
    created_at:                  datetime
    updated_at:                  datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_child(cls, child: "Child") -> "ChildResponseSchema":
        """Build response, resolving mother_id via the pregnancy relationship."""
        mother_id = None
        if child.pregnancy:
            mother_id = child.pregnancy.patient_id

        updated_by_info = None
        if child.updated_by:
            updated_by_info = UserInfoSchema(
                id=child.updated_by.id,
                name=child.updated_by.full_name or child.updated_by.username,
            )

        return cls(
            id=child.id,
            pregnancy_id=child.pregnancy_id,
            mother_id=mother_id,
            name=child.name,
            date_of_birth=child.date_of_birth,
            sex=child.sex,
            notes=child.notes,
            six_month_checkup_date=child.six_month_checkup_date,
            six_month_checkup_completed=child.six_month_checkup_completed,
            hep_b_antibody_test_result=child.hep_b_antibody_test_result,
            test_date=child.test_date,
            updated_by=updated_by_info,
            created_at=child.created_at,
            updated_at=child.updated_at,
        )


# Rebuild forward reference in PregnancyResponseSchema after ChildResponseSchema is defined.
PregnancyResponseSchema.model_rebuild()


# ============================================================================
# Conversion (Pregnant → Regular)
# ============================================================================


class ConvertToRegularPatientSchema(BaseModel):
    """
    Convert a pregnant patient to a regular patient.

    This closes the active pregnancy with the given outcome before converting
    the patient type. `outcome` is required so Pregnancy.close() is called
    with a proper clinical outcome — not left as None.
    """

    outcome:          PregnancyOutcome
    actual_delivery_date: Optional[date] = None # defaults to today if omitted

    @field_validator("actual_delivery_date")
    @classmethod
    def validate_delivery_date(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("Delivery date cannot be in the future.")
        return v

    model_config = {"from_attributes": True}


class ReRegisterAsPregnantSchema(BaseModel):
    """
    Re-register a regular patient as pregnant.

    Used when a patient who previously delivered and was converted to REGULAR
    becomes pregnant again. The pregnant_patients row already exists from the
    first pregnancy — this just flips the discriminator back and opens a new
    Pregnancy episode.

    All fields optional — clinical data can be added later via PATCH /pregnancies/{id}.
    """
    lmp_date:               Optional[date] = None
    expected_delivery_date: Optional[date] = None
    gestational_age_weeks:  Optional[int]  = None
    risk_factors:           Optional[str]  = None
    notes:                  Optional[str]  = None

    model_config = {"from_attributes": True}


# ============================================================================
# Patient Search Result
# ============================================================================

class PatientSearchResult(BaseModel):
    """
    Compact patient record returned by the paginated patient list/search endpoint.

    IMPORTANT:
    This schema must only read columns from the base patients table.
    Do not access gravida, para, pregnancies, or active_pregnancy here,
    because those live in subtype tables/relationships and can trigger
    MissingGreenlet in async SQLAlchemy.
    """

    id: uuid.UUID
    name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[Sex] = None
    date_of_birth: Optional[date] = None
    patient_type: Optional[str] = None
    status: Optional[PatientStatus] = None
    facility_id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_patient(cls, patient: "Patient") -> "PatientSearchResult":
        """
        Build compact response from the base Patient ORM object only.
        """

        patient_id = patient.id
        if patient_id is None:
            raise ValueError(
                "PatientSearchResult.from_patient: patient.id is None. "
                "This indicates a corrupted patient ORM object."
            )

        return cls(
            id=patient_id,
            name=patient.name,
            phone=patient.phone,
            age=patient.age,
            sex=patient.sex,
            date_of_birth=patient.date_of_birth,
            patient_type=(
                patient.patient_type.value
                if hasattr(patient.patient_type, "value")
                else patient.patient_type
            ),
            status=patient.status,
            facility_id=patient.facility_id,
            created_at=patient.created_at,
        )


# ============================================================================
# Diagnosis
# ============================================================================


class DiagnosisBaseSchema(BaseModel):
    patient_id:              uuid.UUID
    diagnosed_by_id:         uuid.UUID
    history:                 Optional[str] = None
    preliminary_diagnosis:   Optional[str] = None
    model_config = {"from_attributes": True}


class DiagnosisCreateSchema(BaseModel):
    """
    Create a diagnosis record.
    
    `patient_id` and `diagnosed_by_id` are set by the route handler:
    - `patient_id` from the URL path
    - `diagnosed_by_id` from the current user
    """
    patient_id:              Optional[uuid.UUID] = None
    diagnosed_by_id:         Optional[uuid.UUID] = None
    history:                 Optional[str] = None
    preliminary_diagnosis:   Optional[str] = None
    model_config = {"from_attributes": True}


class DiagnosisUpdateSchema(BaseModel):
    """
    Update a diagnosis record.

    Fields are all optional — only the provided fields are updated.
    `patient_id` and `diagnosed_by_id` are NOT included: the patient and
    diagnosing clinician are set at creation and must not be changed via update.
    """
    history:               Optional[str] = None
    preliminary_diagnosis: Optional[str] = None
    actual_diagnosis:      Optional[str] = None
    model_config = {"from_attributes": True}


class DiagnosisResponseSchema(BaseModel):
    id:                    uuid.UUID
    patient_id:            uuid.UUID
    diagnosed_by:          Optional[UserInfoSchema] = None
    history:               Optional[str]  = None
    preliminary_diagnosis: Optional[str]  = None
    actual_diagnosis:      Optional[str]  = None
    diagnosed_on:          datetime
    is_deleted:            Optional[bool] = False
    deleted_at:            Optional[datetime] = None
    updated_at:            datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_diagnosis(cls, diagnosis: "Diagnosis") -> "DiagnosisResponseSchema":
        diagnosed_by_info = None
        if diagnosis.diagnosed_by:
            diagnosed_by_info = UserInfoSchema(
                id=diagnosis.diagnosed_by.id,
                name=diagnosis.diagnosed_by.full_name or diagnosis.diagnosed_by.username,
            )
        return cls(
            id=diagnosis.id,
            patient_id=diagnosis.patient_id,
            diagnosed_by=diagnosed_by_info,
            history=diagnosis.history,
            preliminary_diagnosis=diagnosis.preliminary_diagnosis,
            actual_diagnosis=diagnosis.actual_diagnosis,
            diagnosed_on=diagnosis.diagnosed_on,
            is_deleted=diagnosis.is_deleted,
            deleted_at=diagnosis.deleted_at,
            updated_at=diagnosis.updated_at,
        )


# ============================================================================
# Patient Lab Tests
# ============================================================================


class PatientLabResultBaseSchema(BaseModel):
    component_name: str
    component_code: Optional[str] = None
    value_numeric: Optional[Decimal] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    reference_min: Optional[Decimal] = None
    reference_max: Optional[Decimal] = None
    abnormal_flag: Optional[LabResultFlag] = None
    is_abnormal: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("component_name")
    @classmethod
    def validate_component_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Result component name is required.")
        return v.strip()

    @field_validator("component_code", "unit", "value_text")
    @classmethod
    def normalize_optional_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def validate_value_and_range(self):
        if self.value_numeric is None and self.value_text is None:
            raise ValueError("Provide either a numeric or text result value.")
        if (
            self.reference_min is not None
            and self.reference_max is not None
            and self.reference_min > self.reference_max
        ):
            raise ValueError("Reference minimum cannot be greater than reference maximum.")
        return self

    model_config = {"from_attributes": True}


class PatientLabResultCreateSchema(PatientLabResultBaseSchema):
    pass


class PatientLabResultUpdateSchema(BaseModel):
    component_name: Optional[str] = None
    component_code: Optional[str] = None
    value_numeric: Optional[Decimal] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    reference_min: Optional[Decimal] = None
    reference_max: Optional[Decimal] = None
    abnormal_flag: Optional[LabResultFlag] = None
    is_abnormal: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("component_name")
    @classmethod
    def validate_component_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("Result component name is required.")
        return v.strip()

    @field_validator("component_code", "unit", "value_text")
    @classmethod
    def normalize_optional_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    model_config = {"from_attributes": True}


class PatientLabResultResponseSchema(BaseModel):
    id: uuid.UUID
    lab_test_id: uuid.UUID
    component_name: str
    component_code: Optional[str] = None
    value_numeric: Optional[Decimal] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    reference_min: Optional[Decimal] = None
    reference_max: Optional[Decimal] = None
    abnormal_flag: LabResultFlag
    is_abnormal: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientLabTestCreateSchema(BaseModel):
    """
    Create a Hep B, RFT, or LFT lab test for a patient.

    `patient_id` and `ordered_by_id` are set by the route handler.
    """
    patient_id: Optional[uuid.UUID] = None
    test_type: LabTestType
    test_name: Optional[str] = None
    ordered_by_id: Optional[uuid.UUID] = None
    ordered_at: Optional[datetime] = None
    collected_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    status: LabTestStatus = LabTestStatus.ORDERED
    notes: Optional[str] = None
    results: List[PatientLabResultCreateSchema] = []

    @field_validator("test_name")
    @classmethod
    def normalize_test_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    model_config = {"from_attributes": True}


class PatientLabTestUpdateSchema(BaseModel):
    test_type: Optional[LabTestType] = None
    test_name: Optional[str] = None
    collected_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    status: Optional[LabTestStatus] = None
    notes: Optional[str] = None

    @field_validator("test_name")
    @classmethod
    def normalize_test_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    model_config = {"from_attributes": True}


class PatientLabTestResponseSchema(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    test_type: LabTestType
    test_name: str
    status: LabTestStatus
    ordered_by: Optional[UserInfoSchema] = None
    reviewed_by: Optional[UserInfoSchema] = None
    ordered_at: datetime
    collected_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    has_abnormal_results: bool
    notes: Optional[str] = None
    results: List[PatientLabResultResponseSchema] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_lab_test(cls, lab_test: "PatientLabTest") -> "PatientLabTestResponseSchema":
        ordered_by_info = None
        if lab_test.ordered_by:
            ordered_by_info = UserInfoSchema(
                id=lab_test.ordered_by.id,
                name=lab_test.ordered_by.full_name or lab_test.ordered_by.username,
            )

        reviewed_by_info = None
        if lab_test.reviewed_by:
            reviewed_by_info = UserInfoSchema(
                id=lab_test.reviewed_by.id,
                name=lab_test.reviewed_by.full_name or lab_test.reviewed_by.username,
            )

        return cls(
            id=lab_test.id,
            patient_id=lab_test.patient_id,
            test_type=lab_test.test_type,
            test_name=lab_test.test_name,
            status=lab_test.status,
            ordered_by=ordered_by_info,
            reviewed_by=reviewed_by_info,
            ordered_at=lab_test.ordered_at,
            collected_at=lab_test.collected_at,
            reported_at=lab_test.reported_at,
            has_abnormal_results=any(r.is_abnormal for r in getattr(lab_test, "results", [])),
            notes=lab_test.notes,
            results=[
                PatientLabResultResponseSchema.model_validate(result)
                for result in getattr(lab_test, "results", [])
            ],
            created_at=lab_test.created_at,
            updated_at=lab_test.updated_at,
        )


# ============================================================================
# Prescription
# ============================================================================


class PrescriptionBaseSchema(BaseModel):
    medication_name: str
    dosage:          str
    frequency:       str
    duration_months: int  = 6
    prescription_date: date
    start_date:      date
    end_date:        Optional[date] = None
    instructions:    Optional[str]  = None

    @field_validator("medication_name")
    @classmethod
    def validate_medication_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Medication name cannot be empty.")
        v = v.strip()
        if len(v) < 2 or len(v) > 255:
            raise ValueError("Medication name must be between 2 and 255 characters.")
        return v

    @field_validator("duration_months")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v < 1 or v > 24:
            raise ValueError("Duration must be between 1 and 24 months.")
        return v

    model_config = {"from_attributes": True}


class PrescriptionCreateSchema(PrescriptionBaseSchema):
    """
    Create a prescription.
    `patient_id` and `prescribed_by_id` are auto-populated.
    """
    patient_id:       Optional[uuid.UUID] = None
    prescribed_by_id: Optional[uuid.UUID] = None


class PrescriptionUpdateSchema(BaseModel):
    medication_name:  Optional[str]  = None
    dosage:           Optional[str]  = None
    frequency:        Optional[str]  = None
    duration_months:  Optional[int]  = None
    end_date:         Optional[date] = None
    instructions:     Optional[str]  = None
    is_active:        Optional[bool] = None
    model_config = {"from_attributes": True}


class PrescriptionResponseSchema(PrescriptionBaseSchema):
    id:           uuid.UUID
    patient_id:   uuid.UUID
    prescribed_by: Optional[UserInfoSchema] = None
    updated_by:   Optional[UserInfoSchema] = None
    is_active:    bool
    created_at:   datetime
    updated_at:   datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_prescription(cls, prescription: "Prescription") -> "PrescriptionResponseSchema":
        prescribed_by_info = None
        if prescription.prescribed_by:
            prescribed_by_info = UserInfoSchema(
                id=prescription.prescribed_by.id,
                name=prescription.prescribed_by.full_name or prescription.prescribed_by.username,
            )
        updated_by_info = None
        if prescription.updated_by:
            updated_by_info = UserInfoSchema(
                id=prescription.updated_by.id,
                name=prescription.updated_by.full_name or prescription.updated_by.username,
            )
        return cls(
            id=prescription.id,
            patient_id=prescription.patient_id,
            prescribed_by=prescribed_by_info,
            updated_by=updated_by_info,
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
            updated_at=prescription.updated_at,
        )


# ============================================================================
# Medication Schedule
# ============================================================================


class MedicationScheduleBaseSchema(BaseModel):
    medication_name:  str
    scheduled_date:   date
    quantity_purchased: Optional[int] = None
    months_supply:    Optional[int]   = None
    notes:            Optional[str]   = None

    @field_validator("quantity_purchased", "months_supply")
    @classmethod
    def validate_positive_integer(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("Value must be at least 1.")
        return v

    model_config = {"from_attributes": True}


class MedicationScheduleCreateSchema(MedicationScheduleBaseSchema):
    """
    Create a medication schedule.
    `patient_id` is auto-populated from the URL path parameter.
    `prescription_id` links this schedule to its originating prescription for
    the audit trail — optional so manually created schedules still work.
    """
    patient_id:      Optional[uuid.UUID] = None
    prescription_id: Optional[uuid.UUID] = None


class MedicationScheduleUpdateSchema(BaseModel):
    quantity_purchased:    Optional[int]  = None
    months_supply:         Optional[int]  = None
    next_dose_due_date:    Optional[date] = None
    is_completed:          Optional[bool] = None
    completed_date:        Optional[date] = None
    lab_review_scheduled:  Optional[bool] = None
    lab_review_date:       Optional[date] = None
    lab_review_completed:  Optional[bool] = None
    notes:                 Optional[str]  = None
    model_config = {"from_attributes": True}


class MedicationScheduleResponseSchema(MedicationScheduleBaseSchema):
    id:                   uuid.UUID
    patient_id:           uuid.UUID
    prescription_id:      Optional[uuid.UUID] = None
    next_dose_due_date:   Optional[date] = None
    is_completed:         bool
    completed_date:       Optional[date] = None
    lab_review_scheduled: bool
    lab_review_date:      Optional[date] = None
    lab_review_completed: bool
    updated_by:           Optional[UserInfoSchema] = None
    created_at:           datetime
    updated_at:           datetime
    model_config = {"from_attributes": True}


# ============================================================================
# Patient Reminder
# ============================================================================


class PatientReminderBaseSchema(BaseModel):
    reminder_type:  ReminderType
    scheduled_date: date
    message:        str
    child_id:       Optional[uuid.UUID] = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message cannot be empty.")
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Message must be at least 10 characters.")
        return v

    model_config = {"from_attributes": True}


class PatientReminderCreateSchema(PatientReminderBaseSchema):
    """
    Create a reminder.
    `patient_id` is auto-populated from the URL path parameter.
    """
    patient_id: Optional[uuid.UUID] = None


class PatientReminderUpdateSchema(BaseModel):
    scheduled_date: Optional[date]           = None
    message:        Optional[str]            = None
    status:         Optional[ReminderStatus] = None
    model_config = {"from_attributes": True}


class PatientReminderResponseSchema(PatientReminderBaseSchema):
    id:         uuid.UUID
    patient_id: uuid.UUID
    status:     ReminderStatus
    sent_at:    Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class FacilityNotificationUpdateSchema(BaseModel):
    status: Optional[str] = None
    assigned_to_id: Optional[uuid.UUID] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in {"unread", "acknowledged", "in_progress", "resolved", "dismissed"}:
            raise ValueError("Invalid notification status.")
        return v


class FacilityNotificationResponseSchema(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    patient_id: uuid.UUID
    reminder_id: Optional[uuid.UUID] = None
    title: str
    message: str
    notification_type: str
    priority: str
    status: str
    action_label: Optional[str] = None
    action_url: Optional[str] = None
    due_date: Optional[date] = None
    patient_phone: Optional[str] = None
    patient_name: Optional[str] = None
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    assigned_to: Optional[UserInfoSchema] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_notification(cls, notification) -> "FacilityNotificationResponseSchema":
        assigned_to = None
        if getattr(notification, "assigned_to", None):
            assigned_to = UserInfoSchema(
                id=notification.assigned_to.id,
                name=notification.assigned_to.full_name or notification.assigned_to.username,
            )
        return cls(
            id=notification.id,
            facility_id=notification.facility_id,
            patient_id=notification.patient_id,
            reminder_id=notification.reminder_id,
            title=notification.title,
            message=notification.message,
            notification_type=notification.notification_type,
            priority=notification.priority,
            status=notification.status,
            action_label=notification.action_label,
            action_url=notification.action_url,
            due_date=notification.due_date,
            patient_phone=notification.patient_phone,
            patient_name=getattr(getattr(notification, "patient", None), "name", None),
            created_at=notification.created_at,
            acknowledged_at=notification.acknowledged_at,
            resolved_at=notification.resolved_at,
            assigned_to=assigned_to,
        )
