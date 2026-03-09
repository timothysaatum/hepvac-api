"""
Patient schemas — Pydantic models for request validation and response serialisation.

Covers: Patient (base), PregnantPatient, RegularPatient, Pregnancy,
        Child, Diagnosis, Prescription, MedicationSchedule, PatientReminder.
"""

from datetime import date, datetime
from enum import Enum
import re
from typing import TYPE_CHECKING, Dict, List, Optional
import uuid

from pydantic import BaseModel, field_validator
from sqlalchemy.dialects.postgresql import ENUM as PGENUM

if TYPE_CHECKING:
    from app.models.patient_model import Child, Diagnosis, PregnantPatient, Prescription, RegularPatient

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

    name:          str
    phone:         str
    sex:           Sex
    date_of_birth: Optional[date]    = None
    facility_id:   Optional[uuid.UUID] = None
    created_by_id: Optional[uuid.UUID] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name cannot be empty.")
        v = v.strip()
        if len(v) < 2 or len(v) > 255:
            raise ValueError("Name must be between 2 and 255 characters.")
        if any(char.isdigit() for char in v):
            raise ValueError("Name must not contain numbers.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Phone number is required.")
        v = v.strip()
        if any(c.isalpha() for c in v):
            raise ValueError("Phone number must not contain letters.")
        if not re.match(r"^\+?\d{10,15}$", v):
            raise ValueError(
                "Phone number must be 10–15 digits, optionally starting with '+'."
            )
        return v

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

    # Sex defaults to FEMALE for pregnant patients; can be overridden for
    # edge cases but is validated at the service layer.
    sex: Sex = Sex.FEMALE

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: Sex) -> Sex:
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
    phone:         Optional[str]           = None
    date_of_birth: Optional[date]          = None
    status:        Optional[PatientStatus] = None
    updated_by_id: Optional[uuid.UUID]     = None

    @field_validator("name")
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

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^\+?\d{10,15}$", v):
            raise ValueError(
                "Phone number must be 10–15 digits, optionally starting with '+'."
            )
        return v

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
    phone:        Optional[str]        = None
    age:          Optional[int]        = None
    sex:          Sex
    date_of_birth: Optional[date]      = None
    patient_type: str
    status:       PatientStatus
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
            phone=patient.phone,
            age=patient.age,   # computed property
            sex=patient.sex,
            date_of_birth=patient.date_of_birth,
            patient_type=patient.patient_type,
            status=patient.status,
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
    """Input fields for a regular (non-pregnant) patient."""

    diagnosis_date:     Optional[date] = None
    viral_load:         Optional[str]  = None
    last_viral_load_date: Optional[date] = None
    treatment_start_date: Optional[date] = None
    treatment_regimen:  Optional[str]  = None
    medical_history:    Optional[str]  = None
    allergies:          Optional[str]  = None
    notes:              Optional[str]  = None


class RegularPatientCreateSchema(RegularPatientBaseSchema):
    """
    Create a new regular patient.

    `facility_id` and `created_by_id` are populated from the authenticated user
    — do not include in the request body.
    """
    pass


class RegularPatientUpdateSchema(BaseModel):
    """Update a regular patient. All fields optional."""

    name:                Optional[str]           = None
    phone:               Optional[str]           = None
    date_of_birth:       Optional[date]          = None
    diagnosis_date:      Optional[date]          = None
    viral_load:          Optional[str]           = None
    last_viral_load_date: Optional[date]         = None
    treatment_start_date: Optional[date]         = None
    treatment_regimen:   Optional[str]           = None
    medical_history:     Optional[str]           = None
    allergies:           Optional[str]           = None
    notes:               Optional[str]           = None
    status:              Optional[PatientStatus] = None
    updated_by_id:       Optional[uuid.UUID]     = None

    @field_validator("name")
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

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^\+?\d{10,15}$", v):
            raise ValueError(
                "Phone number must be 10–15 digits, optionally starting with '+'."
            )
        return v

    model_config = {"from_attributes": True}


class RegularPatientResponseSchema(BaseModel):
    """Full response for a regular patient."""

    id:                  uuid.UUID
    name:                Optional[str]        = None
    phone:               Optional[str]        = None
    age:                 Optional[int]        = None   # computed property — read only
    sex:                 Sex
    date_of_birth:       Optional[date]       = None
    patient_type:        str
    status:              PatientStatus
    diagnosis_date:      Optional[date]       = None
    viral_load:          Optional[str]        = None
    last_viral_load_date: Optional[date]      = None
    treatment_start_date: Optional[date]      = None
    treatment_regimen:   Optional[str]        = None
    medical_history:     Optional[str]        = None
    allergies:           Optional[str]        = None
    notes:               Optional[str]        = None
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
            phone=patient.phone,
            age=patient.age,   # computed property
            sex=patient.sex,
            date_of_birth=patient.date_of_birth,
            patient_type=patient.patient_type,
            status=patient.status,
            diagnosis_date=getattr(patient, "diagnosis_date", None),
            viral_load=getattr(patient, "viral_load", None),
            last_viral_load_date=getattr(patient, "last_viral_load_date", None),
            treatment_start_date=getattr(patient, "treatment_start_date", None),
            treatment_regimen=getattr(patient, "treatment_regimen", None),
            medical_history=getattr(patient, "medical_history", None),
            allergies=getattr(patient, "allergies", None),
            notes=getattr(patient, "notes", None),
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
    treatment_regimen: Optional[str]     = None
    notes:            Optional[str]      = None

    @field_validator("actual_delivery_date")
    @classmethod
    def validate_delivery_date(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("Delivery date cannot be in the future.")
        return v

    model_config = {"from_attributes": True}


# ============================================================================
# Diagnosis
# ============================================================================


class DiagnosisBaseSchema(BaseModel):
    patient_id:              uuid.UUID
    diagnosed_by_id:         uuid.UUID
    history:                 Optional[str] = None
    preliminary_diagnosis:   Optional[str] = None
    model_config = {"from_attributes": True}


class DiagnosisCreateSchema(DiagnosisBaseSchema):
    pass


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