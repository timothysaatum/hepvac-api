"""
Patient repository — data access layer.
"""

from datetime import datetime, timezone
from typing import Optional, List, Sequence
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import case, func
from sqlalchemy.orm import selectinload

from app.schemas.patient_schemas import PatientType, ReminderStatus
from app.core.pagination import PaginationParams, PaginatedResponse, PageInfo

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
    FacilityNotification,
    PatientIdentifier,
    PatientAllergy,
    PatientLabResult,
    PatientLabTest,
)


class PatientRepository:
    """Repository layer for patient data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Patient base
    # =========================================================================

    async def get_patient_by_id(self, patient_id: uuid.UUID) -> Optional[Patient]:
        """
        Get a patient by ID and return the correct polymorphic subtype.

        This method first reads the base discriminator, then delegates to the
        subtype-specific loader. That keeps response serialization safe in async
        SQLAlchemy because the required relationships are eagerly loaded by the
        subtype loaders.
        """
        result = await self.db.execute(
            select(Patient.patient_type).where(
                Patient.id == patient_id,
                Patient.is_deleted == False,
            )
        )
        patient_type = result.scalar_one_or_none()
        if patient_type is None:
            return None

        # Clear any stale subtype instance from the identity map before loading
        # through the current discriminator. This prevents converted patients
        # from being represented as their old subtype in the same session.
        self.db.expunge_all()

        if patient_type == PatientType.PREGNANT:
            return await self.get_pregnant_patient_by_id(patient_id)
        if patient_type == PatientType.REGULAR:
            return await self.get_regular_patient_by_id(patient_id)

        return None

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

    async def get_patient_facility_id(
        self,
        patient_id: uuid.UUID,
    ) -> Optional[uuid.UUID]:
        """Return a patient's facility id without loading PHI-heavy objects."""
        result = await self.db.execute(
            select(Patient.facility_id).where(
                Patient.id == patient_id,
                Patient.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def get_pregnancy_facility_id(
        self,
        pregnancy_id: uuid.UUID,
    ) -> Optional[uuid.UUID]:
        result = await self.db.execute(
            select(Patient.facility_id)
            .join(PregnantPatient, PregnantPatient.id == Patient.id)
            .join(Pregnancy, Pregnancy.patient_id == PregnantPatient.id)
            .where(
                Pregnancy.id == pregnancy_id,
                Patient.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def get_child_facility_id(
        self,
        child_id: uuid.UUID,
    ) -> Optional[uuid.UUID]:
        result = await self.db.execute(
            select(Patient.facility_id)
            .join(PregnantPatient, PregnantPatient.id == Patient.id)
            .join(Pregnancy, Pregnancy.patient_id == PregnantPatient.id)
            .join(Child, Child.pregnancy_id == Pregnancy.id)
            .where(
                Child.id == child_id,
                Patient.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def get_diagnosis_facility_id(
        self,
        diagnosis_id: uuid.UUID,
    ) -> Optional[uuid.UUID]:
        result = await self.db.execute(
            select(Patient.facility_id)
            .join(Diagnosis, Diagnosis.patient_id == Patient.id)
            .where(
                Diagnosis.id == diagnosis_id,
                Diagnosis.is_deleted == False,
                Patient.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def get_lab_test_facility_id(
        self,
        lab_test_id: uuid.UUID,
    ) -> Optional[uuid.UUID]:
        result = await self.db.execute(
            select(Patient.facility_id)
            .join(PatientLabTest, PatientLabTest.patient_id == Patient.id)
            .where(
                PatientLabTest.id == lab_test_id,
                Patient.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def get_lab_result_facility_id(
        self,
        lab_result_id: uuid.UUID,
    ) -> Optional[uuid.UUID]:
        result = await self.db.execute(
            select(Patient.facility_id)
            .join(PatientLabTest, PatientLabTest.patient_id == Patient.id)
            .join(PatientLabResult, PatientLabResult.lab_test_id == PatientLabTest.id)
            .where(
                PatientLabResult.id == lab_result_id,
                Patient.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()

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

    async def search_patients(
        self,
        query: str,
        facility_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[List[Patient], int]:
        """
        Full-text patient search by name or phone, with optional facility scope.

        Uses plain select(Patient) rather than with_polymorphic.
        PatientSearchResult only reads base-table columns so no subtype JOIN is
        needed, and avoiding the JOIN eliminates the null-subtype-PK trap that
        with_polymorphic exposes when a subtype row is missing: the LEFT JOIN
        returns NULL for the subtype PK, which SQLAlchemy maps to .id on the
        loaded instance, delivering id=None to the Pydantic layer.

        Plain select(Patient) reads only patients.id — which is the base PK and
        is never NULL — so the trap cannot fire.
        """
        from sqlalchemy import or_

        base_query = select(Patient).where(Patient.is_deleted == False)

        if query:
            search_term = f"%{query.strip()}%"
            base_query = base_query.where(
                or_(
                    Patient.name.ilike(search_term),
                    Patient.phone.ilike(search_term),
                )
            )

        if facility_id:
            base_query = base_query.where(Patient.facility_id == facility_id)

        base_query = base_query.order_by(Patient.created_at.desc())

        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total_count = total_result.scalar() or 0

        paginated_query = base_query.offset(skip).limit(limit)
        result = await self.db.execute(paginated_query)
        patients = list(result.scalars().all())

        return patients, total_count

    async def list_patients_paginated(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        patient_status: Optional[str] = None,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[List[Patient], int]:
        """
        Paginated patient list — base columns only.

        Uses plain select(Patient) rather than with_polymorphic.
        PatientSearchResult only consumes base-table columns (id, name, phone,
        sex, date_of_birth, patient_type, status, facility_id, created_at) so
        the subtype LEFT JOINs are unnecessary overhead.

        More importantly, with_polymorphic exposes a data-integrity trap: if a
        patients row exists whose patient_type discriminator points to a subtype
        but the corresponding subtype row is missing (incomplete transaction,
        failed migration, manual DB edit), the LEFT JOIN returns NULL for the
        subtype PK.  In SQLAlchemy joined-table inheritance, the subtype PK
        populates .id on the loaded instance — delivering id=None to the Pydantic
        layer and causing a 500 on the entire listing.

        Plain select(Patient) hits only the patients table.  patient.id is always
        patients.id (the base PK), which is never NULL by definition.
        """
        base_query = select(Patient).where(Patient.is_deleted == False)

        if facility_id:
            base_query = base_query.where(Patient.facility_id == facility_id)
        if patient_type:
            base_query = base_query.where(Patient.patient_type == patient_type)
        if patient_status:
            base_query = base_query.where(Patient.status == patient_status)

        base_query = base_query.order_by(Patient.created_at.desc())

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

        Returns None when no row matching PregnantPatient's discriminator exists
        for this ID (i.e. the patient was converted to REGULAR or never existed).

        FIX: Removed the InvalidRequestError try/except that was silently
        swallowing identity map discriminator mismatches. The service layer now
        calls expunge_all() before any discriminator-sensitive query, so the
        identity map is always clean and this exception can never fire. Keeping
        the catch block was masking real bugs and causing false 409s.
        """
        result = await self.db.execute(
            select(PregnantPatient)
            .where(
                PregnantPatient.id == patient_id,
                PregnantPatient.is_deleted == False,
                PregnantPatient.patient_type == PatientType.PREGNANT,
            )
            .options(
                selectinload(PregnantPatient.facility),
                selectinload(PregnantPatient.created_by),
                selectinload(PregnantPatient.updated_by),
                selectinload(PregnantPatient.pregnancies),
                selectinload(PregnantPatient.identifiers),
                selectinload(PregnantPatient.allergies_structured),
            )
        )
        return result.scalars().first()

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

        Returns None when no row matching RegularPatient's discriminator exists
        for this ID (i.e. the patient was re-registered as pregnant or never existed).

        FIX: Removed the InvalidRequestError try/except that was silently
        swallowing identity map discriminator mismatches. The service layer now
        calls expunge_all() before any discriminator-sensitive query, so the
        identity map is always clean and this exception can never fire. Keeping
        the catch block was masking real bugs and causing false 409s.
        """
        result = await self.db.execute(
            select(RegularPatient)
            .where(
                RegularPatient.id == patient_id,
                RegularPatient.is_deleted == False,
                RegularPatient.patient_type == PatientType.REGULAR,
            )
            .options(
                selectinload(RegularPatient.facility),
                selectinload(RegularPatient.created_by),
                selectinload(RegularPatient.updated_by),
                selectinload(RegularPatient.identifiers),
                selectinload(RegularPatient.allergies_structured),
            )
        )
        return result.scalars().first()

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
    # Patient allergy
    # =========================================================================

    async def create_patient_allergy(self, allergy: PatientAllergy) -> PatientAllergy:
        self.db.add(allergy)
        await self.db.commit()
        await self.db.refresh(allergy)
        return allergy

    async def get_patient_allergy_by_id(
        self, allergy_id: uuid.UUID
    ) -> Optional[PatientAllergy]:
        result = await self.db.execute(
            select(PatientAllergy).where(PatientAllergy.id == allergy_id)
        )
        return result.scalars().first()

    async def get_patient_allergies(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[PatientAllergy]:
        query = select(PatientAllergy).where(PatientAllergy.patient_id == patient_id)
        if active_only:
            query = query.where(PatientAllergy.is_active == True)
        query = query.order_by(PatientAllergy.is_active.desc(), PatientAllergy.allergen.asc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_patient_allergy(self, allergy: PatientAllergy) -> PatientAllergy:
        self.db.add(allergy)
        await self.db.commit()
        await self.db.refresh(allergy)
        return allergy

    # =========================================================================
    # Patient lab tests
    # =========================================================================

    async def create_patient_lab_test(self, lab_test: PatientLabTest) -> PatientLabTest:
        self.db.add(lab_test)
        await self.db.commit()
        created = await self.get_patient_lab_test_by_id(lab_test.id)
        return created

    async def get_patient_lab_test_by_id(
        self, lab_test_id: uuid.UUID
    ) -> Optional[PatientLabTest]:
        result = await self.db.execute(
            select(PatientLabTest)
            .where(PatientLabTest.id == lab_test_id)
            .options(
                selectinload(PatientLabTest.results),
                selectinload(PatientLabTest.ordered_by),
                selectinload(PatientLabTest.reviewed_by),
            )
        )
        return result.scalars().first()

    async def get_patient_lab_tests(
        self,
        patient_id: uuid.UUID,
        test_type: Optional[str] = None,
    ) -> List[PatientLabTest]:
        query = (
            select(PatientLabTest)
            .where(PatientLabTest.patient_id == patient_id)
            .options(
                selectinload(PatientLabTest.results),
                selectinload(PatientLabTest.ordered_by),
                selectinload(PatientLabTest.reviewed_by),
            )
        )
        if test_type:
            query = query.where(PatientLabTest.test_type == test_type)
        query = query.order_by(PatientLabTest.ordered_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_patient_lab_test(self, lab_test: PatientLabTest) -> PatientLabTest:
        self.db.add(lab_test)
        await self.db.commit()
        updated = await self.get_patient_lab_test_by_id(lab_test.id)
        return updated

    async def create_patient_lab_result(
        self, lab_result: PatientLabResult
    ) -> PatientLabResult:
        self.db.add(lab_result)
        await self.db.commit()
        await self.db.refresh(lab_result)
        return lab_result

    async def get_patient_lab_result_by_id(
        self, lab_result_id: uuid.UUID
    ) -> Optional[PatientLabResult]:
        result = await self.db.execute(
            select(PatientLabResult).where(PatientLabResult.id == lab_result_id)
        )
        return result.scalars().first()

    async def update_patient_lab_result(
        self, lab_result: PatientLabResult
    ) -> PatientLabResult:
        self.db.add(lab_result)
        await self.db.commit()
        await self.db.refresh(lab_result)
        return lab_result

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

    async def get_patient_reminders_paginated(
        self,
        patient_id: uuid.UUID,
        pagination: PaginationParams,
        status_filter: Optional[str] = None,
        upcoming_only: bool = False,
    ) -> PaginatedResponse:
        """
        Get paginated reminders for a patient with smart ordering.
        
        Ordering: Pending/upcoming first (by scheduled_date), then sent/cancelled.
        
        Args:
            patient_id: Patient ID
            pagination: Pagination parameters (page, page_size)
            status_filter: Optional status filter (PENDING, SENT, FAILED, CANCELLED)
            upcoming_only: If True, only show scheduled_date >= today
        
        Returns:
            PaginatedResponse with items and page_info
        """
        from datetime import date
        
        # Build base query
        query = select(PatientReminder).where(
            PatientReminder.patient_id == patient_id
        )
        
        # Filter by status if provided
        if status_filter:
            query = query.where(PatientReminder.status == status_filter)
        
        # Filter upcoming if requested
        if upcoming_only:
            query = query.where(PatientReminder.scheduled_date >= date.today())
        
        # Smart ordering: pending/upcoming first, then by date
        # CASE WHEN status = 'PENDING' THEN 0 ELSE 1 END, scheduled_date
        from sqlalchemy import case
        priority_case = case(
            (PatientReminder.status == ReminderStatus.PENDING, 0),
            else_=1
        )
        query = query.order_by(priority_case, PatientReminder.scheduled_date)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total_count = total_result.scalar() or 0
        
        # Apply pagination
        query = query.offset(pagination.skip).limit(pagination.limit)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        
        # Build page info
        total_pages = (total_count + pagination.page_size - 1) // pagination.page_size
        page_info = PageInfo(
            total_items=total_count,
            total_pages=total_pages,
            current_page=pagination.page,
            page_size=pagination.page_size,
            has_next=pagination.page < total_pages,
            has_previous=pagination.page > 1,
            next_page=pagination.page + 1 if pagination.page < total_pages else None,
            previous_page=pagination.page - 1 if pagination.page > 1 else None,
        )
        
        return PaginatedResponse(items=items, page_info=page_info)

    async def update_reminder(self, reminder: PatientReminder) -> PatientReminder:
        self.db.add(reminder)
        await self.db.commit()
        await self.db.refresh(reminder)
        return reminder

    # =========================================================================
    # Facility notifications
    # =========================================================================

    async def create_facility_notification(
        self, notification: FacilityNotification
    ) -> FacilityNotification:
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def get_facility_notification_by_reminder(
        self, reminder_id: uuid.UUID
    ) -> Optional[FacilityNotification]:
        result = await self.db.execute(
            select(FacilityNotification)
            .options(
                selectinload(FacilityNotification.patient),
                selectinload(FacilityNotification.reminder),
                selectinload(FacilityNotification.assigned_to),
            )
            .where(FacilityNotification.reminder_id == reminder_id)
        )
        return result.scalars().first()

    async def get_facility_notification_by_id(
        self, notification_id: uuid.UUID
    ) -> Optional[FacilityNotification]:
        result = await self.db.execute(
            select(FacilityNotification)
            .options(
                selectinload(FacilityNotification.patient),
                selectinload(FacilityNotification.reminder),
                selectinload(FacilityNotification.assigned_to),
            )
            .where(FacilityNotification.id == notification_id)
        )
        return result.scalars().first()

    async def list_facility_notifications(
        self,
        facility_id: uuid.UUID,
        status_filter: Optional[str] = None,
        unresolved_only: bool = True,
        limit: int = 50,
    ) -> List[FacilityNotification]:
        query = (
            select(FacilityNotification)
            .options(
                selectinload(FacilityNotification.patient),
                selectinload(FacilityNotification.reminder),
                selectinload(FacilityNotification.assigned_to),
            )
            .where(FacilityNotification.facility_id == facility_id)
        )
        if status_filter:
            query = query.where(FacilityNotification.status == status_filter)
        elif unresolved_only:
            query = query.where(FacilityNotification.status.notin_(["resolved", "dismissed"]))
        priority_case = case(
            (FacilityNotification.priority == "urgent", 0),
            (FacilityNotification.priority == "high", 1),
            (FacilityNotification.priority == "normal", 2),
            else_=3,
        )
        query = query.order_by(priority_case, FacilityNotification.due_date.asc(), FacilityNotification.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_facility_notification(
        self, notification: FacilityNotification
    ) -> FacilityNotification:
        self.db.add(notification)
        await self.db.commit()
        refreshed = await self.get_facility_notification_by_id(notification.id)
        return refreshed or notification

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
