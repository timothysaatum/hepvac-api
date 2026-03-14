"""
Patient repository — data access layer.
"""

from datetime import datetime, timezone
from typing import Optional, List, Sequence
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload, with_polymorphic

from app.models.patient_model import (
    Patient,
    PregnantPatient,
    Pregnancy,
    RegularPatient,
    Child,
    Diagnosis,
    Prescription,
    MedicationSchedule,
    PatientReminder,
)


class PatientRepository:
    """Repository layer for patient data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Patient base
    # =========================================================================

    async def get_patient_by_id(self, patient_id: uuid.UUID) -> Optional[Patient]:
        """Get patient by ID."""
        result = await self.db.execute(
            select(Patient).where(
                Patient.id == patient_id,
                Patient.is_deleted == False,
            )
        )
        return result.scalars().first()

    async def get_patient_by_phone(
        self, phone: str, facility_id: uuid.UUID
    ) -> Optional[Patient]:
        """Get patient by phone number within a facility."""
        result = await self.db.execute(
            select(Patient).where(
                Patient.phone == phone,
                Patient.facility_id == facility_id,
                Patient.is_deleted == False,
            )
        )
        return result.scalars().first()

    async def get_patient_by_pregnancy_id(
        self, pregnancy_id: uuid.UUID
    ) -> Optional[PregnantPatient]:
        """
        Get pregnant patient by pregnancy ID — single join query.

        The FK lives on Pregnancy.patient_id, not on Patient.
        """
        result = await self.db.execute(
            select(PregnantPatient)
            .join(Pregnancy, Pregnancy.patient_id == PregnantPatient.id)
            .where(
                Pregnancy.id == pregnancy_id,
                PregnantPatient.is_deleted == False,
            )
        )
        return result.scalars().first()

    async def get_patients(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Patient]:
        """Get filtered list of patients (unpaginated)."""
        query = select(Patient).where(Patient.is_deleted == False)
        if facility_id:
            query = query.where(Patient.facility_id == facility_id)
        if patient_type:
            query = query.where(Patient.patient_type == patient_type)
        if status:
            query = query.where(Patient.status == status)
        query = query.order_by(Patient.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_patient(self, patient: Patient) -> None:
        """Soft delete a patient."""
        patient.is_deleted = True
        patient.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(patient)

    async def list_patients_paginated(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        patient_status: Optional[str] = None,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[List[Patient], int]:
        """
        Paginated patient list with polymorphic subtype loading.

        Uses with_polymorphic so subtype columns (PregnantPatient.gravida,
        RegularPatient.viral_load, etc.) are available without extra queries.
        """
        poly_patient = with_polymorphic(Patient, [PregnantPatient, RegularPatient])
        base_query = select(poly_patient).where(poly_patient.is_deleted == False)

        if facility_id:
            base_query = base_query.where(poly_patient.facility_id == facility_id)
        if patient_type:
            base_query = base_query.where(poly_patient.patient_type == patient_type)
        if patient_status:
            base_query = base_query.where(poly_patient.status == patient_status)

        base_query = base_query.order_by(poly_patient.created_at.desc())

        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total_count = total_result.scalar() or 0

        paginated_query = base_query.offset(skip).limit(limit)
        result = await self.db.execute(paginated_query)
        patients = list(result.scalars().all())

        return patients, total_count

    # =========================================================================
    # Pregnant patient
    # =========================================================================

    async def create_pregnant_patient(
        self, patient: PregnantPatient
    ) -> PregnantPatient:
        """Persist a new PregnantPatient (and any cascaded Pregnancy rows)."""
        self.db.add(patient)
        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    async def get_pregnant_patient_by_id(
        self, patient_id: uuid.UUID
    ) -> Optional[PregnantPatient]:
        """Get pregnant patient by ID with all relationships eagerly loaded.

        Returns None (rather than raising) when the patient exists but the
        discriminator no longer matches PregnantPatient — i.e. was converted
        to REGULAR.  The caller (service layer) decides how to handle it.
        """
        from sqlalchemy.exc import InvalidRequestError
        try:
            result = await self.db.execute(
                select(PregnantPatient)
                .where(
                    PregnantPatient.id == patient_id,
                    PregnantPatient.is_deleted == False,
                )
                .options(
                    selectinload(PregnantPatient.facility),
                    selectinload(PregnantPatient.created_by),
                    selectinload(PregnantPatient.updated_by),
                )
            )
            return result.scalars().first()
        except InvalidRequestError:
            # Discriminator mismatch — patient was converted to REGULAR.
            return None

    async def update_pregnant_patient(
        self, updated_by_id: uuid.UUID, patient: PregnantPatient
    ) -> PregnantPatient:
        """Persist updates to a PregnantPatient."""
        patient.updated_by_id = updated_by_id
        self.db.add(patient)
        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    # =========================================================================
    # Regular patient
    # =========================================================================

    async def create_regular_patient(self, patient: RegularPatient) -> RegularPatient:
        """Persist a new RegularPatient."""
        self.db.add(patient)
        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    async def get_regular_patient_by_id(
        self, patient_id: uuid.UUID
    ) -> Optional[RegularPatient]:
        """Get regular patient by ID with all relationships eagerly loaded.

        Returns None (rather than raising) when the patient exists but the
        discriminator no longer matches RegularPatient — i.e. was re-registered
        as pregnant.  The caller (service layer) decides how to handle it.

        This mirrors the same guard on get_pregnant_patient_by_id: SQLAlchemy's
        identity map may cache the row under a different polymorphic mapper from
        a prior request in the same worker, causing InvalidRequestError when the
        discriminator has changed since the cache was populated.
        """
        from sqlalchemy.exc import InvalidRequestError
        try:
            result = await self.db.execute(
                select(RegularPatient)
                .where(
                    RegularPatient.id == patient_id,
                    RegularPatient.is_deleted == False,
                )
                .options(
                    selectinload(RegularPatient.facility),
                    selectinload(RegularPatient.created_by),
                    selectinload(RegularPatient.updated_by),
                )
            )
            return result.scalars().first()
        except InvalidRequestError:
            # Discriminator mismatch — patient was re-registered as PREGNANT.
            return None

    async def update_regular_patient(
        self, updated_by_id: uuid.UUID, patient: RegularPatient
    ) -> RegularPatient:
        """Persist updates to a RegularPatient."""
        patient.updated_by_id = updated_by_id
        self.db.add(patient)
        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    # =========================================================================
    # Pregnancy
    # =========================================================================

    async def create_pregnancy(self, pregnancy: Pregnancy) -> Pregnancy:
        """Persist a new Pregnancy episode."""
        self.db.add(pregnancy)
        await self.db.commit()
        await self.db.refresh(pregnancy)
        return pregnancy

    async def get_pregnancy_by_id(
        self, pregnancy_id: uuid.UUID
    ) -> Optional[Pregnancy]:
        """Get a single Pregnancy episode by ID, eager-loading children."""
        stmt = (
            select(Pregnancy)
            .where(Pregnancy.id == pregnancy_id)
            .options(
                selectinload(Pregnancy.children),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_patient_pregnancies(
        self, patient_id: uuid.UUID
    ) -> List[Pregnancy]:
        """
            Get all Pregnancy episodes for a patient, ordered by pregnancy_number.
        """
        result = await self.db.execute(
            select(Pregnancy)
            .where(Pregnancy.patient_id == patient_id)
            .options(selectinload(Pregnancy.children))
            .order_by(Pregnancy.pregnancy_number)
        )

        return list(result.scalars().all())

    async def get_active_pregnancy(
        self, patient_id: uuid.UUID
    ) -> Optional[Pregnancy]:
        """Get the single active Pregnancy for a patient, or None."""
        result = await self.db.execute(
            select(Pregnancy).where(
                Pregnancy.patient_id == patient_id,
                Pregnancy.is_active == True,
            )
        )
        return result.scalars().first()

    async def update_pregnancy(self, pregnancy: Pregnancy) -> Pregnancy:
        """Persist updates to a Pregnancy episode."""
        self.db.add(pregnancy)
        await self.db.commit()
        await self.db.refresh(pregnancy)
        return pregnancy

    # =========================================================================
    # Child
    # =========================================================================

    async def create_child(self, child: Child) -> Child:
        """Persist a new Child record."""
        self.db.add(child)
        await self.db.commit()
        await self.db.refresh(child)
        return child

    async def get_child_by_id(self, child_id: uuid.UUID) -> Optional[Child]:
        """Get child by ID."""
        result = await self.db.execute(
            select(Child).where(Child.id == child_id)
        )
        return result.scalars().first()

    async def get_pregnancy_children(
        self, pregnancy_id: uuid.UUID
    ) -> List[Child]:
        """
        Get all children for a specific pregnancy episode.

        FIX: original queried Child.mother_id which no longer exists.
        Children now link to a Pregnancy, not directly to the patient.
        """
        result = await self.db.execute(
            select(Child)
            .where(Child.pregnancy_id == pregnancy_id)
            .order_by(Child.date_of_birth)
            .options(selectinload(Child.pregnancy))
        )
        return list(result.scalars().all())

    async def get_mother_children(self, patient_id: uuid.UUID) -> List[Child]:
        """
        Get all children for a mother across ALL her pregnancies.

        FIX: original queried Child.mother_id which no longer exists.
        Joins Child → Pregnancy on patient_id to traverse the relationship.
        """
        result = await self.db.execute(
            select(Child)
            .join(Pregnancy, Child.pregnancy_id == Pregnancy.id)
            .where(Pregnancy.patient_id == patient_id)
            .order_by(Child.date_of_birth)
            .options(selectinload(Child.pregnancy))
        )
        return list(result.scalars().all())

    async def update_child(self, child: Child) -> Child:
        """Persist updates to a Child record."""
        self.db.add(child)
        await self.db.commit()
        await self.db.refresh(child)
        return child

    async def delete_child(self, child: Child) -> None:
        """Hard delete a child record."""
        await self.db.delete(child)
        await self.db.commit()

    # =========================================================================
    # Prescription
    # =========================================================================

    async def create_prescription(self, prescription: Prescription) -> Prescription:
        self.db.add(prescription)
        await self.db.commit()
        await self.db.refresh(prescription)
        return prescription

    async def get_prescription_by_id(
        self, prescription_id: uuid.UUID
    ) -> Optional[Prescription]:
        result = await self.db.execute(
            select(Prescription).where(Prescription.id == prescription_id)
        )
        return result.scalars().first()

    async def get_patient_prescriptions(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[Prescription]:
        query = select(Prescription).where(Prescription.patient_id == patient_id)
        if active_only:
            query = query.where(Prescription.is_active == True)
        query = query.order_by(Prescription.prescription_date.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_prescription(self, prescription: Prescription) -> Prescription:
        self.db.add(prescription)
        await self.db.commit()
        await self.db.refresh(prescription)
        return prescription

    # =========================================================================
    # Medication schedule
    # =========================================================================

    async def create_medication_schedule(
        self, schedule: MedicationSchedule
    ) -> MedicationSchedule:
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def get_medication_schedule_by_id(
        self, schedule_id: uuid.UUID
    ) -> Optional[MedicationSchedule]:
        result = await self.db.execute(
            select(MedicationSchedule).where(MedicationSchedule.id == schedule_id)
        )
        return result.scalars().first()

    async def get_patient_medication_schedules(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[MedicationSchedule]:
        query = select(MedicationSchedule).where(
            MedicationSchedule.patient_id == patient_id
        )
        if active_only:
            query = query.where(MedicationSchedule.is_completed == False)
        query = query.order_by(MedicationSchedule.scheduled_date.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_medication_schedule(
        self, schedule: MedicationSchedule
    ) -> MedicationSchedule:
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    # =========================================================================
    # Reminder
    # =========================================================================

    async def create_reminder(self, reminder: PatientReminder) -> PatientReminder:
        self.db.add(reminder)
        await self.db.commit()
        await self.db.refresh(reminder)
        return reminder

    async def bulk_create_reminders(
        self,
        reminders: Sequence[PatientReminder],
    ) -> List[PatientReminder]:
        """
        Persist multiple PatientReminder rows in a single commit.
        Used by the escalating reminder generator — more efficient than
        calling create_reminder() in a loop (one round-trip vs N).
        """
        for r in reminders:
            self.db.add(r)
        await self.db.commit()
        for r in reminders:
            await self.db.refresh(r)
        return list(reminders)

    async def get_reminder_by_id(
        self, reminder_id: uuid.UUID
    ) -> Optional[PatientReminder]:
        result = await self.db.execute(
            select(PatientReminder).where(PatientReminder.id == reminder_id)
        )
        return result.scalars().first()

    async def get_patient_reminders(
        self, patient_id: uuid.UUID, pending_only: bool = False
    ) -> List[PatientReminder]:
        query = select(PatientReminder).where(
            PatientReminder.patient_id == patient_id
        )
        if pending_only:
            query = query.where(PatientReminder.status == "pending")
        query = query.order_by(PatientReminder.scheduled_date.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_reminder(self, reminder: PatientReminder) -> PatientReminder:
        self.db.add(reminder)
        await self.db.commit()
        await self.db.refresh(reminder)
        return reminder

    async def delete_reminder(self, reminder: PatientReminder) -> None:
        await self.db.delete(reminder)
        await self.db.commit()

    # =========================================================================
    # Diagnosis
    # =========================================================================

    async def create_diagnosis(self, diagnosis: Diagnosis) -> Diagnosis:
        """Persist a new Diagnosis record."""
        self.db.add(diagnosis)
        await self.db.commit()
        await self.db.refresh(diagnosis)
        return diagnosis

    async def get_diagnosis_by_id(self, diagnosis_id: uuid.UUID) -> Optional[Diagnosis]:
        """Get a Diagnosis by ID."""
        result = await self.db.execute(
            select(Diagnosis).where(
                Diagnosis.id == diagnosis_id,
                Diagnosis.is_deleted == False,
            )
        )
        return result.scalars().first()

    async def update_diagnosis(self, diagnosis: Diagnosis) -> Diagnosis:
        """Persist updates to a Diagnosis."""
        self.db.add(diagnosis)
        await self.db.commit()
        await self.db.refresh(diagnosis)
        return diagnosis

    async def get_patient_diagnoses(
        self, patient_id: uuid.UUID
    ) -> list[Diagnosis]:
        """List all active diagnoses for a patient, newest first."""
        result = await self.db.execute(
            select(Diagnosis)
            .where(
                Diagnosis.patient_id == patient_id,
                Diagnosis.is_deleted == False,
            )
            .order_by(Diagnosis.diagnosed_on.desc())
        )
        return list(result.scalars().all())