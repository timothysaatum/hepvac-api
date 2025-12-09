# import uuid
# from datetime import datetime, date
# from decimal import Decimal
# from typing import Optional, List, TYPE_CHECKING
# from sqlalchemy import (
#     TIMESTAMP,
#     Boolean,
#     ForeignKey,
#     String,
#     Date,
#     Numeric,
#     Text,
#     Enum as SQLEnum,
#     func,
# )
# from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy.dialects.postgresql import UUID as PGUUID
# from app.db.base import Base
# from app.schemas.patient_schemas import (
#     DoseType,
#     PatientStatus,
#     ReminderStatus,
#     ReminderType,
#     sex_enum_type,
#     PatientType,
# )


# from app.models.vaccine_model import PatientVaccinePurchase
# if TYPE_CHECKING:
#     from app.models.user_model import User
#     from app.models.facility_model import Facility


# class Patient(Base):
#     """Base patient model with common fields for all patient types"""

#     __tablename__ = "patients"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         primary_key=True,
#         default=uuid.uuid4,
#         unique=True,
#         index=True,
#     )

#     # Basic Information (Common to all patients)
#     name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
#     phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
#     sex: Mapped[Sex] = mapped_column(sex_enum_type, nullable=False)
#     age: Mapped[int] = mapped_column(nullable=False)
#     date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

#     # Discriminator for inheritance
#     patient_type: Mapped[PatientType] = mapped_column(
#         SQLEnum(PatientType), default=PatientType.PREGNANT, nullable=False, index=True
#     )

#     # Patient Status
#     status: Mapped[PatientStatus] = mapped_column(
#         SQLEnum(PatientStatus), default=PatientStatus.ACTIVE, nullable=False, index=True
#     )

#     # Facility relationship
#     facility_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("facilities.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     # Created by which staff
#     created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("users.id", ondelete="SET NULL"),
#         nullable=True,
#         index=True,
#     )

#     created_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )

#     updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("users.id", ondelete="SET NULL"),
#         nullable=True,
#         index=True,
#     )

#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )

#     is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
#     accepts_messaging: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
#     deleted_at: Mapped[Optional[datetime]] = mapped_column(
#         TIMESTAMP(timezone=True), nullable=True
#     )

#     # Polymorphic configuration
#     __mapper_args__ = {
#         "polymorphic_identity": "patient",
#         "polymorphic_on": patient_type,
#     }

#     facility: Mapped["Facility"] = relationship(
#         "Facility", foreign_keys=[facility_id], lazy="selectin"
#     )

#     created_by: Mapped[Optional["User"]] = relationship(
#         "User", foreign_keys=[created_by_id], lazy="selectin"
#     )

#     updated_by: Mapped[Optional["User"]] = relationship(
#         "User", foreign_keys=[updated_by_id], lazy="selectin"
#     )

#     # Vaccine purchases replace wallet
#     vaccine_purchases: Mapped[List["PatientVaccinePurchase"]] = relationship(
#         "PatientVaccinePurchase", back_populates="patient", cascade="all, delete-orphan"
#     )

#     vaccinations: Mapped[List["Vaccination"]] = relationship(
#         "Vaccination", back_populates="patient", cascade="all, delete-orphan"
#     )

#     prescriptions: Mapped[List["Prescription"]] = relationship(
#         "Prescription", back_populates="patient", cascade="all, delete-orphan"
#     )

#     diagnosis: Mapped[List["Diagnosis"]] = relationship(
#         "Diagnosis", back_populates="patient", cascade="all, delete-orphan"
#     )

#     medication_schedules: Mapped[List["MedicationSchedule"]] = relationship(
#         "MedicationSchedule", back_populates="patient", cascade="all, delete-orphan"
#     )

#     reminders: Mapped[List["PatientReminder"]] = relationship(
#         "PatientReminder", back_populates="patient", cascade="all, delete-orphan"
#     )

#     def __repr__(self) -> str:
#         return f"<Patient id={self.id} name={self.name} type={self.patient_type}>"


# class Diagnosis(Base):

#     __tablename__ = "diagnosis"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         primary_key=True,
#         default=uuid.uuid4,
#         unique=True,
#         index=True,
#     )
#     history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
#     preliminary_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
#     actual_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

#     diagnose_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("users.id", ondelete="SET NULL"),
#         nullable=True,
#     )

#     patient_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patients.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     patient: Mapped["Patient"] = relationship("Patient", back_populates="diagnosis")

#     diagnose_by: Mapped[Optional["User"]] = relationship(
#         "User", foreign_keys=[diagnose_by_id], lazy="selectin"
#     )

#     is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

#     diagnosed_on: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )

#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )

#     deleted_at: Mapped[Optional[datetime]] = mapped_column(
#         TIMESTAMP(timezone=True), nullable=True
#     )

#     def __str__(self):
#         return self.patient.name


# class PregnantPatient(Patient):
#     """Pregnant patient model - inherits from Patient"""

#     __tablename__ = "pregnant_patients"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patients.id", ondelete="CASCADE"),
#         primary_key=True,
#     )

#     # Pregnancy-specific Information
#     expected_delivery_date: Mapped[Optional[date]] = mapped_column(
#         Date, nullable=True, index=True
#     )
#     actual_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

#     # Gestational information
#     gestational_age_weeks: Mapped[Optional[int]] = mapped_column(nullable=True)
#     gravida: Mapped[Optional[int]] = mapped_column(
#         nullable=True
#     )  # Number of pregnancies
#     para: Mapped[Optional[int]] = mapped_column(nullable=True)  # Number of deliveries

#     # Risk factors
#     risk_factors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
#     notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

#     # Polymorphic configuration
#     __mapper_args__ = {
#         "polymorphic_identity": "pregnant",
#     }

#     # Relationships specific to pregnant patients
#     children: Mapped[List["Child"]] = relationship(
#         "Child",
#         back_populates="mother",
#         foreign_keys="[Child.mother_id]",
#         cascade="all, delete-orphan",
#     )

#     def __repr__(self) -> str:
#         return self.name

#     def has_delivered(self) -> bool:
#         if self.actual_delivery_date is not None:
#             return True


# class RegularPatient(Patient):
#     """Regular patient model - inherits from Patient"""

#     __tablename__ = "regular_patients"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patients.id", ondelete="CASCADE"),
#         primary_key=True,
#     )

#     # Regular patient specific information
#     diagnosis_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
#     viral_load: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
#     last_viral_load_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

#     # Treatment information
#     treatment_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
#     treatment_regimen: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

#     # Medical history
#     medical_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
#     allergies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
#     notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

#     # Polymorphic configuration
#     __mapper_args__ = {
#         "polymorphic_identity": "regular",
#     }

#     def __repr__(self) -> str:
#         return f"<RegularPatient id={self.id} name={self.name}>"


# class Vaccination(Base):
#     """Vaccination record for patients"""

#     __tablename__ = "vaccinations"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         primary_key=True,
#         default=uuid.uuid4,
#         unique=True,
#         index=True,
#     )

#     patient_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patients.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     # Link to the vaccine purchase (replaces wallet_id)
#     vaccine_purchase_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patient_vaccine_purchases.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     # Dose Information
#     dose_number: Mapped[DoseType] = mapped_column(
#         SQLEnum(DoseType), default=DoseType.FIRST_DOSE, nullable=False, index=True
#     )
#     dose_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
#     batch_number: Mapped[str] = mapped_column(String(100), nullable=False)

#     # Snapshot of vaccine info at time of administration
#     vaccine_name: Mapped[str] = mapped_column(String(100), nullable=False)
#     vaccine_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

#     # Additional Information
#     administered_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("users.id", ondelete="SET NULL"),
#         nullable=True,
#     )
#     notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

#     created_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )

#     # Relationships
#     patient: Mapped["Patient"] = relationship(
#         "Patient", back_populates="vaccinations", foreign_keys=[patient_id]
#     )

#     vaccine_purchase: Mapped["PatientVaccinePurchase"] = relationship(
#         "PatientVaccinePurchase", back_populates="vaccinations", lazy="selectin"
#     )

#     administered_by: Mapped[Optional["User"]] = relationship(
#         "User", foreign_keys=[administered_by_id], lazy="selectin"
#     )

#     def __repr__(self) -> str:
#         return f"<Vaccination id={self.id} patient_id={self.patient_id} dose={self.dose_number}>"


# class Child(Base):
#     """Child tracking for postpartum mothers"""

#     __tablename__ = "children"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         primary_key=True,
#         default=uuid.uuid4,
#         unique=True,
#         index=True,
#     )

#     mother_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("pregnant_patients.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     # Child Information
#     name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     date_of_birth: Mapped[date] = mapped_column(Date, nullable=False, index=True)
#     sex: Mapped[Optional[Sex]] = mapped_column(sex_enum_type, nullable=False)

#     # Monitoring Information
#     six_month_checkup_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
#     six_month_checkup_completed: Mapped[bool] = mapped_column(
#         default=False, nullable=False
#     )
#     hep_b_antibody_test_result: Mapped[Optional[str]] = mapped_column(
#         String(100), nullable=True
#     )
#     test_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

#     notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

#     created_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )
#     # Relationships
#     mother: Mapped["PregnantPatient"] = relationship(
#         "PregnantPatient", back_populates="children", foreign_keys=[mother_id]
#     )

#     def __repr__(self) -> str:
#         return f"<Child id={self.id} mother_id={self.mother_id}>"


# class Payment(Base):
#     """Individual installment payment transactions"""

#     __tablename__ = "payments"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         primary_key=True,
#         default=uuid.uuid4,
#         unique=True,
#         index=True,
#     )

#     # Link to vaccine purchase (replaces wallet_id)
#     vaccine_purchase_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patient_vaccine_purchases.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
#     payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
#     payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
#     reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
#     notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

#     received_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("users.id", ondelete="SET NULL"),
#         nullable=True,
#     )

#     created_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )

#     # Relationships
#     vaccine_purchase: Mapped["PatientVaccinePurchase"] = relationship(
#         "PatientVaccinePurchase", back_populates="payments", lazy="selectin"
#     )

#     received_by: Mapped[Optional["User"]] = relationship(
#         "User", foreign_keys=[received_by_id], lazy="selectin"
#     )

#     def __repr__(self) -> str:
#         return f"<Payment id={self.id} amount={self.amount} date={self.payment_date}>"


# class Prescription(Base):
#     """Patient prescriptions"""

#     __tablename__ = "prescriptions"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         primary_key=True,
#         default=uuid.uuid4,
#         unique=True,
#         index=True,
#     )

#     patient_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patients.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     prescribed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("users.id", ondelete="SET NULL"),
#         nullable=True,
#     )

#     medication_name: Mapped[str] = mapped_column(String(255), nullable=False)
#     dosage: Mapped[str] = mapped_column(String(100), nullable=False)
#     frequency: Mapped[str] = mapped_column(String(100), nullable=False)
#     duration_months: Mapped[int] = mapped_column(default=6, nullable=False)

#     prescription_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
#     start_date: Mapped[date] = mapped_column(Date, nullable=False)
#     end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

#     instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
#     is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

#     created_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )

#     # Relationships
#     patient: Mapped["Patient"] = relationship(
#         "Patient", back_populates="prescriptions", foreign_keys=[patient_id]
#     )

#     prescribed_by: Mapped[Optional["User"]] = relationship(
#         "User", foreign_keys=[prescribed_by_id], lazy="selectin"
#     )

#     def __repr__(self) -> str:
#         return f"<Prescription id={self.id} medication={self.medication_name}>"


# class MedicationSchedule(Base):
#     """Monthly medication schedule and tracking"""

#     __tablename__ = "medication_schedules"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         primary_key=True,
#         default=uuid.uuid4,
#         unique=True,
#         index=True,
#     )

#     patient_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patients.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     medication_name: Mapped[str] = mapped_column(String(255), nullable=False)
#     scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
#     # Purchase and dispensing tracking
#     quantity_purchased: Mapped[Optional[int]] = mapped_column(nullable=True)
#     months_supply: Mapped[Optional[int]] = mapped_column(nullable=True)
#     next_dose_due_date: Mapped[Optional[date]] = mapped_column(
#         Date, nullable=True, index=True
#     )
#     is_completed: Mapped[bool] = mapped_column(default=False, nullable=False)
#     completed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
#     # Lab review tracking (after 6 months)
#     lab_review_scheduled: Mapped[bool] = mapped_column(default=False, nullable=False)
#     lab_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
#     lab_review_completed: Mapped[bool] = mapped_column(default=False, nullable=False)

#     notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

#     created_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )

#     # Relationships
#     patient: Mapped["Patient"] = relationship(
#         "Patient", back_populates="medication_schedules", foreign_keys=[patient_id]
#     )

#     def __repr__(self) -> str:
#         return f"<MedicationSchedule id={self.id} patient_id={self.patient_id} date={self.scheduled_date}>"


# class PatientReminder(Base):
#     """Automated reminders for patients"""

#     __tablename__ = "patient_reminders"

#     id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         primary_key=True,
#         default=uuid.uuid4,
#         unique=True,
#         index=True,
#     )

#     patient_id: Mapped[uuid.UUID] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("patients.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     reminder_type: Mapped[ReminderType] = mapped_column(
#         SQLEnum(ReminderType), nullable=False, index=True
#     )

#     scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
#     message: Mapped[str] = mapped_column(Text, nullable=False)

#     status: Mapped[ReminderStatus] = mapped_column(
#         SQLEnum(ReminderStatus),
#         default=ReminderStatus.PENDING,
#         nullable=False,
#         index=True,
#     )

#     sent_at: Mapped[Optional[datetime]] = mapped_column(
#         TIMESTAMP(timezone=True), nullable=True
#     )

#     # For tracking related records
#     child_id: Mapped[Optional[uuid.UUID]] = mapped_column(
#         PGUUID(as_uuid=True),
#         ForeignKey("children.id", ondelete="CASCADE"),
#         nullable=True,
#     )

#     created_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         TIMESTAMP(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )

#     # Relationships
#     patient: Mapped["Patient"] = relationship(
#         "Patient", back_populates="reminders", foreign_keys=[patient_id]
#     )

#     child: Mapped[Optional["Child"]] = relationship(
#         "Child", foreign_keys=[child_id], lazy="selectin"
#     )

#     def mark_as_sent(self) -> None:
#         """Mark reminder as sent"""
#         self.status = ReminderStatus.SENT
#         self.sent_at = datetime.now()

#     def __repr__(self) -> str:
#         return f"<PatientReminder id={self.id} type={self.reminder_type} status={self.status}>"
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    String,
    Date,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db.base import Base
from app.schemas.patient_schemas import (
    DoseType,
    PatientStatus,
    ReminderStatus,
    ReminderType,
    Sex,
    PatientType,
    # Import the pre-configured ENUM types
    sex_enum_type,
    patient_type_enum,
    patient_status_enum,
    dose_type_enum,
    reminder_type_enum,
    reminder_status_enum,
)


from app.models.vaccine_model import PatientVaccinePurchase
if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.facility_model import Facility


class Patient(Base):
    """Base patient model with common fields for all patient types"""

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    # Basic Information (Common to all patients)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sex: Mapped[Sex] = mapped_column(sex_enum_type, nullable=False)
    age: Mapped[int] = mapped_column(nullable=False)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Discriminator for inheritance
    patient_type: Mapped[PatientType] = mapped_column(
        patient_type_enum, default=PatientType.PREGNANT, nullable=False, index=True
    )

    # Patient Status
    status: Mapped[PatientStatus] = mapped_column(
        patient_status_enum, default=PatientStatus.ACTIVE, nullable=False, index=True
    )

    # Facility relationship
    facility_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Created by which staff
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    accepts_messaging: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Polymorphic configuration
    __mapper_args__ = {
        "polymorphic_identity": "patient",
        "polymorphic_on": patient_type,
    }

    facility: Mapped["Facility"] = relationship(
        "Facility", foreign_keys=[facility_id], lazy="selectin"
    )

    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id], lazy="selectin"
    )

    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[updated_by_id], lazy="selectin"
    )

    # Vaccine purchases replace wallet
    vaccine_purchases: Mapped[List["PatientVaccinePurchase"]] = relationship(
        "PatientVaccinePurchase", back_populates="patient", cascade="all, delete-orphan"
    )

    vaccinations: Mapped[List["Vaccination"]] = relationship(
        "Vaccination", back_populates="patient", cascade="all, delete-orphan"
    )

    prescriptions: Mapped[List["Prescription"]] = relationship(
        "Prescription", back_populates="patient", cascade="all, delete-orphan"
    )

    diagnosis: Mapped[List["Diagnosis"]] = relationship(
        "Diagnosis", back_populates="patient", cascade="all, delete-orphan"
    )

    medication_schedules: Mapped[List["MedicationSchedule"]] = relationship(
        "MedicationSchedule", back_populates="patient", cascade="all, delete-orphan"
    )

    reminders: Mapped[List["PatientReminder"]] = relationship(
        "PatientReminder", back_populates="patient", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Patient id={self.id} name={self.name} type={self.patient_type}>"


class Diagnosis(Base):

    __tablename__ = "diagnosis"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preliminary_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actual_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    diagnose_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    patient: Mapped["Patient"] = relationship("Patient", back_populates="diagnosis")

    diagnose_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[diagnose_by_id], lazy="selectin"
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    diagnosed_on: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    def __str__(self):
        return self.patient.name


class PregnantPatient(Patient):
    """Pregnant patient model - inherits from Patient"""

    __tablename__ = "pregnant_patients"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Pregnancy-specific Information
    expected_delivery_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )
    actual_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Gestational information
    gestational_age_weeks: Mapped[Optional[int]] = mapped_column(nullable=True)
    gravida: Mapped[Optional[int]] = mapped_column(
        nullable=True
    )  # Number of pregnancies
    para: Mapped[Optional[int]] = mapped_column(nullable=True)  # Number of deliveries

    # Risk factors
    risk_factors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Polymorphic configuration
    __mapper_args__ = {
        "polymorphic_identity": "pregnant",
    }

    # Relationships specific to pregnant patients
    children: Mapped[List["Child"]] = relationship(
        "Child",
        back_populates="mother",
        foreign_keys="[Child.mother_id]",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return self.name

    def has_delivered(self) -> bool:
        if self.actual_delivery_date is not None:
            return True


class RegularPatient(Patient):
    """Regular patient model - inherits from Patient"""

    __tablename__ = "regular_patients"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Regular patient specific information
    diagnosis_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    viral_load: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_viral_load_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Treatment information
    treatment_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    treatment_regimen: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Medical history
    medical_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allergies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Polymorphic configuration
    __mapper_args__ = {
        "polymorphic_identity": "regular",
    }

    def __repr__(self) -> str:
        return f"<RegularPatient id={self.id} name={self.name}>"


class Vaccination(Base):
    """Vaccination record for patients"""

    __tablename__ = "vaccinations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Link to the vaccine purchase (replaces wallet_id)
    vaccine_purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_vaccine_purchases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Dose Information
    dose_number: Mapped[DoseType] = mapped_column(
        dose_type_enum, default=DoseType.FIRST_DOSE, nullable=False, index=True
    )
    dose_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)

    # Snapshot of vaccine info at time of administration
    vaccine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    vaccine_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Additional Information
    administered_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="vaccinations", foreign_keys=[patient_id]
    )

    vaccine_purchase: Mapped["PatientVaccinePurchase"] = relationship(
        "PatientVaccinePurchase", back_populates="vaccinations", lazy="selectin"
    )

    administered_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[administered_by_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Vaccination id={self.id} patient_id={self.patient_id} dose={self.dose_number}>"


class Child(Base):
    """Child tracking for postpartum mothers"""

    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    mother_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pregnant_patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Child Information
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sex: Mapped[Optional[Sex]] = mapped_column(sex_enum_type, nullable=True)

    # Monitoring Information
    six_month_checkup_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    six_month_checkup_completed: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    hep_b_antibody_test_result: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    test_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Relationships
    mother: Mapped["PregnantPatient"] = relationship(
        "PregnantPatient", back_populates="children", foreign_keys=[mother_id]
    )

    def __repr__(self) -> str:
        return f"<Child id={self.id} mother_id={self.mother_id}>"


class Payment(Base):
    """Individual installment payment transactions"""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    # Link to vaccine purchase (replaces wallet_id)
    vaccine_purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_vaccine_purchases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    received_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    vaccine_purchase: Mapped["PatientVaccinePurchase"] = relationship(
        "PatientVaccinePurchase", back_populates="payments", lazy="selectin"
    )

    received_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[received_by_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Payment id={self.id} amount={self.amount} date={self.payment_date}>"


class Prescription(Base):
    """Patient prescriptions"""

    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    prescribed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    medication_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_months: Mapped[int] = mapped_column(default=6, nullable=False)

    prescription_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="prescriptions", foreign_keys=[patient_id]
    )

    prescribed_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[prescribed_by_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Prescription id={self.id} medication={self.medication_name}>"


class MedicationSchedule(Base):
    """Monthly medication schedule and tracking"""

    __tablename__ = "medication_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    medication_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Purchase and dispensing tracking
    quantity_purchased: Mapped[Optional[int]] = mapped_column(nullable=True)
    months_supply: Mapped[Optional[int]] = mapped_column(nullable=True)
    next_dose_due_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )
    is_completed: Mapped[bool] = mapped_column(default=False, nullable=False)
    completed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Lab review tracking (after 6 months)
    lab_review_scheduled: Mapped[bool] = mapped_column(default=False, nullable=False)
    lab_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    lab_review_completed: Mapped[bool] = mapped_column(default=False, nullable=False)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="medication_schedules", foreign_keys=[patient_id]
    )

    def __repr__(self) -> str:
        return f"<MedicationSchedule id={self.id} patient_id={self.patient_id} date={self.scheduled_date}>"


class PatientReminder(Base):
    """Automated reminders for patients"""

    __tablename__ = "patient_reminders"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    reminder_type: Mapped[ReminderType] = mapped_column(
        reminder_type_enum, nullable=False, index=True
    )

    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[ReminderStatus] = mapped_column(
        reminder_status_enum,
        default=ReminderStatus.PENDING,
        nullable=False,
        index=True,
    )

    sent_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # For tracking related records
    child_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("children.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="reminders", foreign_keys=[patient_id]
    )

    child: Mapped[Optional["Child"]] = relationship(
        "Child", foreign_keys=[child_id], lazy="selectin"
    )

    def mark_as_sent(self) -> None:
        """Mark reminder as sent"""
        self.status = ReminderStatus.SENT
        self.sent_at = datetime.now()

    def __repr__(self) -> str:
        return f"<PatientReminder id={self.id} type={self.reminder_type} status={self.status}>"