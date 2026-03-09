"""
Patient models — base and specialised subtypes.

Schema (joined-table inheritance):
    Patient  (base, table: patients)
    ├── PregnantPatient  (table: pregnant_patients)
    │       └── Pregnancy  (table: pregnancies)  ← one row per episode
    │               └── Child  (table: children)  ← linked to specific pregnancy
    └── RegularPatient  (table: regular_patients)

Supporting models:
    Diagnosis, Vaccination, Child, Payment,
    Prescription, MedicationSchedule, PatientReminder


Data model:
    PregnantPatient  ──(1:many)──  Pregnancy  ──(1:many)──  Child
    gravida/para are                  per-episode dates,         birth details +
    lifetime counts                   gestational data,          monitoring
                                      risk factors, outcome
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.schemas.patient_schemas import (
    DoseType,
    HepBTestResult,
    PatientStatus,
    PatientType,
    PregnancyOutcome,
    ReminderStatus,
    ReminderType,
    Sex,
    hep_b_test_result_enum,
    pregnancy_outcome_enum,
    dose_type_enum,
    patient_status_enum,
    patient_type_enum,
    reminder_status_enum,
    reminder_type_enum,
    sex_enum_type,
)

if TYPE_CHECKING:
    from app.models.facility_model import Facility
    from app.models.vaccine_model import PatientVaccinePurchase
    from app.models.user_model import User


# ============================================================================
# Patient (base)
# ============================================================================


class Patient(Base):
    """
    Base patient record — fields shared by all patient types.

    Uses SQLAlchemy joined-table polymorphic inheritance.  The `patient_type`
    column is the discriminator; type-specific data lives in the subtype tables.
    """

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # ── Demographics ──────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sex: Mapped[Sex] = mapped_column(sex_enum_type, nullable=False)

    # Age is a computed @property derived from this — never store raw age integers.
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Polymorphic discriminator ─────────────────────────────────────────────
    patient_type: Mapped[PatientType] = mapped_column(
        patient_type_enum,
        default=PatientType.PREGNANT,
        nullable=False,
        index=True,
    )

    status: Mapped[PatientStatus] = mapped_column(
        patient_status_enum,
        default=PatientStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # ── Facility ──────────────────────────────────────────────────────────────
    facility_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        # RESTRICT prevents accidental wipe of all patients when a facility
        # is deleted. Deactivate/migrate patients first, then delete facility.
        ForeignKey("facilities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
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

    # ── Soft-delete ───────────────────────────────────────────────────────────
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    accepts_messaging: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )

    __mapper_args__ = {
        "polymorphic_identity": "patient",
        "polymorphic_on": patient_type,
    }

    # ── Relationships ─────────────────────────────────────────────────────────

    # SAFETY: noload on all collection/audit relationships — load explicitly
    # at the query site with .options(selectinload(...)) to avoid MissingGreenlet
    # in async context. Never use lazy="select" with AsyncSession.
    facility: Mapped["Facility"] = relationship(
        "Facility",
        foreign_keys=[facility_id],
        lazy="noload",
    )

    created_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by_id],
        lazy="noload",
        back_populates="created_patients",
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by_id],
        lazy="noload",
        back_populates="updated_patients",
    )

    vaccine_purchases: Mapped[List["PatientVaccinePurchase"]] = relationship(
        "PatientVaccinePurchase",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    vaccinations: Mapped[List["Vaccination"]] = relationship(
        "Vaccination",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    prescriptions: Mapped[List["Prescription"]] = relationship(
        "Prescription",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    diagnoses: Mapped[List["Diagnosis"]] = relationship(
        "Diagnosis",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    medication_schedules: Mapped[List["MedicationSchedule"]] = relationship(
        "MedicationSchedule",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    reminders: Mapped[List["PatientReminder"]] = relationship(
        "PatientReminder",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def age(self) -> Optional[int]:
        """
        Current age in whole years, derived from date_of_birth.

        Returns None when date_of_birth has not been recorded.
        Storing age as a column is wrong — it goes stale on every birthday.
        """
        if self.date_of_birth is None:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    def __repr__(self) -> str:
        return f"<Patient id={self.id} name={self.name} type={self.patient_type}>"


# ============================================================================
# Diagnosis
# ============================================================================


class Diagnosis(Base):
    """Clinical diagnosis record linked to a patient."""

    __tablename__ = "diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    diagnosed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preliminary_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actual_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="diagnoses",
        lazy="noload",
    )
    
    diagnosed_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[diagnosed_by_id],
        back_populates="diagnoses_given",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Diagnosis id={self.id} patient_id={self.patient_id}>"

    def __str__(self) -> str:
        
        return str(self.patient_id)


# ============================================================================
# Pregnancy
# ============================================================================


class Pregnancy(Base):
    """
    A single pregnancy episode belonging to a PregnantPatient.

    One patient can have many Pregnancy rows over her lifetime (gravida > 1).
    All per-pregnancy obstetric data lives here — dates, gestational age,
    risk factors, and outcome.  Children are linked to this record, not
    directly to the patient, so you always know which child came from which
    pregnancy.

    Lifecycle:
        1.  Patient is registered → PregnantPatient created, gravida incremented.
        2.  New Pregnancy row inserted with is_active=True.
        3.  At delivery → actual_delivery_date set, outcome recorded,
            is_active set to False, para incremented on PregnantPatient.
        4.  If patient becomes pregnant again → repeat from step 2.
    """

    __tablename__ = "pregnancies"

    __table_args__ = (
        # Each pregnancy for a patient gets a unique sequential number.
        # Enforces no duplicate numbering at the DB level.
        UniqueConstraint(
            "patient_id",
            "pregnancy_number",
            name="uq_patient_pregnancy_number",
        ),
        # Partial unique index: only ONE active pregnancy per patient at a time.
        # Allows unlimited completed (is_active=FALSE) pregnancies freely.
        Index(
            "uix_one_active_pregnancy_per_patient",
            "patient_id",
            unique=True,
            postgresql_where="is_active = TRUE",
        ),
        # Pregnancy number must be a positive integer.
        CheckConstraint("pregnancy_number > 0", name="ck_pregnancy_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pregnant_patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pregnancy_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Dates ─────────────────────────────────────────────────────────────────
    # Last Menstrual Period — used to calculate gestational age.
    lmp_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expected_delivery_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )
    actual_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Gestational data ──────────────────────────────────────────────────────
    # Weeks of gestation at time of registration/first visit for this pregnancy.
    gestational_age_weeks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Risk & clinical notes ─────────────────────────────────────────────────
    risk_factors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Outcome ───────────────────────────────────────────────────────────────
    # Set when is_active is flipped to False (i.e. the pregnancy ends).
    # Add PregnancyOutcome to patient_schemas — see MIGRATION GUIDE below.
    outcome: Mapped[Optional["PregnancyOutcome"]] = mapped_column(
        pregnancy_outcome_enum,
        nullable=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────
    # True  = pregnancy currently ongoing.
    # False = pregnancy ended (delivered, miscarried, etc.).
    # The partial unique index above ensures only one active=True per patient.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    patient: Mapped["PregnantPatient"] = relationship(
        "PregnantPatient",
        back_populates="pregnancies",
        foreign_keys=[patient_id],
        lazy="selectin",
    )

    # Children born from THIS specific pregnancy episode.
    # noload: don't pull all children on every Pregnancy fetch.
    # Load explicitly: .options(selectinload(Pregnancy.children))
    children: Mapped[List["Child"]] = relationship(
        "Child",
        back_populates="pregnancy",
        cascade="all, delete-orphan",
        order_by="Child.date_of_birth",
        lazy="noload",
    )

    # ── Business logic ────────────────────────────────────────────────────────

    def has_delivered(self) -> bool:
        """Return True if an actual delivery date has been recorded."""
        return self.actual_delivery_date is not None

    def close(
        self,
        outcome: "PregnancyOutcome",
        delivery_date: Optional[date] = None,
    ) -> None:
        """
        Mark this pregnancy as ended.

        Call this when a pregnancy concludes (delivery, loss, or other outcome).
        The caller is responsible for incrementing `para` on the parent
        PregnantPatient when the outcome warrants it (LIVE_BIRTH, STILLBIRTH).

        Args:
            outcome:       The clinical outcome of this pregnancy.
            delivery_date: The actual delivery/loss date. Defaults to today.
        """
        self.is_active = False
        self.outcome = outcome
        self.actual_delivery_date = delivery_date or date.today()

    def __repr__(self) -> str:
        return (
            f"<Pregnancy id={self.id} patient_id={self.patient_id} "
            f"number={self.pregnancy_number} active={self.is_active}>"
        )


# ============================================================================
# PregnantPatient
# ============================================================================


class PregnantPatient(Patient):
    """
    Pregnant patient subtype.

    Holds only patient-level obstetric SUMMARY fields that accumulate over a
    lifetime (gravida, para).  All per-episode data (dates, gestational age,
    risk factors, children) lives in individual Pregnancy rows.

    Accessing pregnancy data:
        patient.active_pregnancy       → the single ongoing Pregnancy, or None
        patient.pregnancies            → all Pregnancy rows ordered by number
        patient.pregnancy_history      → completed pregnancies, newest first

    Opening / closing pregnancies:
        pregnancy = patient.open_new_pregnancy()
        session.add(pregnancy)

        patient.close_active_pregnancy(outcome=PregnancyOutcome.LIVE_BIRTH)
    """

    __tablename__ = "pregnant_patients"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Lifetime obstetric counts — updated at each pregnancy event.
    #   gravida: total pregnancies, including any currently active one.
    #   para:    total completed deliveries (live births + stillbirths).
    # These are summary fields that reflect the patient's full obstetric history to date. All episode-specific details (dates, gestational age, risk factors,
    gravida: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False
    )
    para: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "pregnant",
    }

    # ── Relationships ─────────────────────────────────────────────────────────

    pregnancies: Mapped[List["Pregnancy"]] = relationship(
        "Pregnancy",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="Pregnancy.pregnancy_number",
        lazy="selectin",
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def active_pregnancy(self) -> Optional[Pregnancy]:
        """
        Return the single currently active Pregnancy, or None.

        Uniqueness is enforced by the partial unique index on
        pregnancies(is_active = TRUE).  Iterates the already-loaded list
        to avoid an extra query.
        """
        return next((p for p in self.pregnancies if p.is_active), None)

    @property
    def pregnancy_history(self) -> List[Pregnancy]:
        """
        All completed (inactive) pregnancies, most recent first.

        Useful for displaying the full obstetric history in the UI.
        """
        return sorted(
            [p for p in self.pregnancies if not p.is_active],
            key=lambda p: p.pregnancy_number,
            reverse=True,
        )

    # ── Business logic ────────────────────────────────────────────────────────

    def open_new_pregnancy(self) -> Pregnancy:
        """
        Create and attach a new Pregnancy episode for this patient.

        Assigns the next sequential pregnancy_number based on the highest
        existing pregnancy_number (not len(pregnancies)), so hard-deleted
        rows never cause a numbering collision or UniqueConstraint violation.

        The caller must add the pregnancy to the session and flush/commit.

        Raises:
            ValueError: if the patient already has an active pregnancy.

        Usage:
            pregnancy = patient.open_new_pregnancy()
            pregnancy.expected_delivery_date = date(2025, 9, 1)
            session.add(pregnancy)
            await session.flush()
        """
        if self.active_pregnancy is not None:
            raise ValueError(
                f"Patient {self.id} already has an active pregnancy "
                f"(Pregnancy id={self.active_pregnancy.id}). "
                "Close the current pregnancy before opening a new one."
            )

        # Use max(pregnancy_number) across loaded pregnancies rather than
        # len() — len() breaks if any row was hard-deleted, producing a
        # duplicate number that violates uq_patient_pregnancy_number.
        if self.pregnancies:
            next_pregnancy_number = max(p.pregnancy_number for p in self.pregnancies) + 1
        else:
            next_pregnancy_number = 1

        self.gravida = max(self.gravida or 0, next_pregnancy_number)

        new_pregnancy = Pregnancy(
            patient_id=self.id,
            pregnancy_number=next_pregnancy_number,
            is_active=True,
        )
        self.pregnancies.append(new_pregnancy)
        return new_pregnancy

    def close_active_pregnancy(
        self,
        outcome: "PregnancyOutcome",
        delivery_date: Optional[date] = None,
        increment_para: bool = True,
    ) -> Pregnancy:
        """
        Close the currently active pregnancy and update para if applicable.

        Args:
            outcome:        Clinical outcome of the pregnancy.
            delivery_date:  Actual delivery/loss date. Defaults to today.
            increment_para: Whether to increment para. Pass True for
                            LIVE_BIRTH and STILLBIRTH; False for
                            MISCARRIAGE, ABORTION, ECTOPIC.

        Returns:
            The now-closed Pregnancy instance.

        Raises:
            ValueError: if there is no active pregnancy to close.
        """
        pregnancy = self.active_pregnancy
        if pregnancy is None:
            raise ValueError(
                f"Patient {self.id} has no active pregnancy to close."
            )

        pregnancy.close(outcome=outcome, delivery_date=delivery_date)

        if increment_para:
            self.para += 1

        return pregnancy

    def __repr__(self) -> str:
        return (
            f"<PregnantPatient id={self.id} name={self.name} "
            f"gravida={self.gravida} para={self.para}>"
        )


# ============================================================================
# RegularPatient
# ============================================================================


class RegularPatient(Patient):
    """
    Regular (non-pregnant) patient subtype.

    Extends Patient with HIV/chronic-condition treatment fields.
    """

    __tablename__ = "regular_patients"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        primary_key=True,
    )

    diagnosis_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    viral_load: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_viral_load_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    treatment_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    treatment_regimen: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    medical_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allergies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "regular",
    }

    def __repr__(self) -> str:
        return f"<RegularPatient id={self.id} name={self.name}>"


# ============================================================================
# Vaccination
# ============================================================================


class Vaccination(Base):
    """Record of a single vaccine dose administered to a patient."""

    __tablename__ = "vaccinations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vaccine_purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_vaccine_purchases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    dose_number: Mapped[DoseType] = mapped_column(
        dose_type_enum,
        default=DoseType.FIRST_DOSE,
        nullable=False,
        index=True,
    )
    dose_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)

    # Snapshot of vaccine details at administration time — denormalised
    # intentionally so historical records are not affected by future changes
    # to the Vaccine master record.
    vaccine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    vaccine_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

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

    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="vaccinations",
        foreign_keys=[patient_id],
        lazy="noload",
    )
    vaccine_purchase: Mapped["PatientVaccinePurchase"] = relationship(
        "PatientVaccinePurchase",
        back_populates="vaccinations",
        lazy="selectin",
    )
    administered_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[administered_by_id],
        lazy="selectin",
        back_populates="administered_vaccinations",
    )

    def __repr__(self) -> str:
        return (
            f"<Vaccination id={self.id} patient_id={self.patient_id} "
            f"dose={self.dose_number}>"
        )


# ============================================================================
# Child
# ============================================================================


class Child(Base):
    """
    Child born from a specific Pregnancy episode.

    Linked to a Pregnancy (not directly to PregnantPatient) so the full
    obstetric history is always queryable:
        patient → pregnancies → [pregnancy] → children

    Tracks birth details and six-month monitoring milestones.
    """

    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # FK to the specific pregnancy this child came from.
    # This replaces the old mother_id → pregnant_patients FK, which lost
    # the pregnancy-episode context entirely.
    pregnancy_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pregnancies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Birth details ─────────────────────────────────────────────────────────
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sex: Mapped[Optional[Sex]] = mapped_column(sex_enum_type, nullable=True)

    # ── Six-month monitoring ──────────────────────────────────────────────────
    six_month_checkup_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    six_month_checkup_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Constrained enum — prevents free-text variants ("pos", "reactive", etc.)
    # from corrupting the column and breaking downstream reporting.
    hep_b_antibody_test_result: Mapped[Optional[HepBTestResult]] = mapped_column(
        hep_b_test_result_enum,
        nullable=True,
    )
    test_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    # Track who last modified clinical data (six-month checkup, test result).
    # Required for the same compliance reasons as Prescription and Diagnosis.
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    pregnancy: Mapped["Pregnancy"] = relationship(
        "Pregnancy",
        back_populates="children",
        foreign_keys=[pregnancy_id],
        lazy="selectin",
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by_id],
        lazy="selectin",
    )

    # NOTE: Child.mother intentionally removed. Accessing pregnancy.patient
    # from a synchronously-called property in an async context raises
    # MissingGreenlet. Load the full chain explicitly at the query site:
    #   .options(selectinload(Child.pregnancy).selectinload(Pregnancy.patient))

    def __repr__(self) -> str:
        return f"<Child id={self.id} pregnancy_id={self.pregnancy_id}>"


# ============================================================================
# Payment
# ============================================================================


class Payment(Base):
    """Individual installment payment transaction against a vaccine purchase."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    vaccine_purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient_vaccine_purchases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # history required a join through PatientVaccinePurchase, making reporting,
    # billing, and row-level security (by facility) significantly harder.
    # Denormalised intentionally — direct indexed lookups simplify the entire
    # billing surface.
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
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

    vaccine_purchase: Mapped["PatientVaccinePurchase"] = relationship(
        "PatientVaccinePurchase",
        back_populates="payments",
        lazy="noload",
    )
    patient: Mapped["Patient"] = relationship(
        "Patient",
        foreign_keys=[patient_id],
        lazy="noload",
    )
    received_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[received_by_id],
        lazy="selectin",
        back_populates="received_payments",
    )

    def __repr__(self) -> str:
        return f"<Payment id={self.id} amount={self.amount} date={self.payment_date}>"


# ============================================================================
# Prescription
# ============================================================================


class Prescription(Base):
    """Medication prescription issued to a patient."""

    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
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
    # changed a prescription is a compliance requirement (audit trail).
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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

    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="prescriptions",
        foreign_keys=[patient_id],
        lazy="noload",
    )
    prescribed_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[prescribed_by_id],
        lazy="selectin",
        back_populates="prescribed_prescriptions",
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by_id],
        lazy="noload",
        back_populates="updated_prescriptions",
    )

    def __repr__(self) -> str:
        return f"<Prescription id={self.id} medication={self.medication_name}>"


# ============================================================================
# MedicationSchedule
# ============================================================================


class MedicationSchedule(Base):
    """Monthly medication dispensing schedule and completion tracking."""

    __tablename__ = "medication_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Audit trail: links this dispensing schedule back to the originating
    # prescription. Nullable so legacy/manually created schedules still work.
    prescription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("prescriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    medication_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity_purchased: Mapped[Optional[int]] = mapped_column(nullable=True)
    months_supply: Mapped[Optional[int]] = mapped_column(nullable=True)
    next_dose_due_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Lab review tracking (typically 6-month interval)
    lab_review_scheduled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    lab_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    lab_review_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Knowing who last modified a dispensing schedule is a compliance requirement.
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
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

    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="medication_schedules",
        foreign_keys=[patient_id],
        lazy="noload",
    )
    prescription: Mapped[Optional["Prescription"]] = relationship(
        "Prescription",
        foreign_keys=[prescription_id],
        lazy="noload",
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by_id],
        lazy="noload",
        back_populates="updated_medication_schedules",
    )

    def __repr__(self) -> str:
        return (
            f"<MedicationSchedule id={self.id} patient_id={self.patient_id} "
            f"date={self.scheduled_date}>"
        )


# ============================================================================
# PatientReminder
# ============================================================================


class PatientReminder(Base):
    """Automated reminder for a patient (appointment, dose, lab review, etc.)."""

    __tablename__ = "patient_reminders"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reminder_type: Mapped[ReminderType] = mapped_column(
        reminder_type_enum,
        nullable=False,
        index=True,
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

    # Optional: pin a reminder to a specific child record.
    child_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("children.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="reminders",
        foreign_keys=[patient_id],
        lazy="noload",
    )
    child: Mapped[Optional["Child"]] = relationship(
        "Child",
        foreign_keys=[child_id],
        lazy="selectin",
    )

    def mark_as_sent(self) -> None:
        """Mark this reminder as sent and record the UTC timestamp."""
        self.status = ReminderStatus.SENT
        self.sent_at = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return (
            f"<PatientReminder id={self.id} type={self.reminder_type} "
            f"status={self.status}>"
        )