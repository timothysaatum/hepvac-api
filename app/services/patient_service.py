"""
Patient service — business logic layer.
The service layer orchestrates complex operations that may involve multiple repository calls, transactions, and business rules. It owns the transaction
"""

from datetime import timedelta
from typing import List, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_model import (
    PregnantPatient,
    Pregnancy,
    RegularPatient,
    Child,
    Prescription,
    MedicationSchedule,
    PatientReminder,
)
from app.schemas.patient_schemas import (
    PregnantPatientCreateSchema,
    PregnantPatientUpdateSchema,
    PregnancyCreateSchema,
    PregnancyUpdateSchema,
    PregnancyCloseSchema,
    RegularPatientCreateSchema,
    RegularPatientUpdateSchema,
    ChildCreateSchema,
    ChildUpdateSchema,
    PrescriptionCreateSchema,
    PrescriptionUpdateSchema,
    MedicationScheduleCreateSchema,
    MedicationScheduleUpdateSchema,
    PatientReminderCreateSchema,
    PatientReminderUpdateSchema,
    ConvertToRegularPatientSchema,
    PatientStatus,
    PatientType,
)
from app.repositories.patient_repo import PatientRepository


class PatientService:
    """Service layer for patient business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PatientRepository(self.db)

    # =========================================================================
    # Pregnant patient
    # =========================================================================

    async def create_pregnant_patient(
        self, patient_data: PregnantPatientCreateSchema
    ) -> PregnantPatient:
        """
        Create a new pregnant patient together with her first pregnancy episode.

        The schema embeds a `first_pregnancy: PregnancyCreateSchema`. We pop
        that field before constructing the ORM model, then call
        open_new_pregnancy() to attach the episode atomically.
        """
        if patient_data.facility_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Facility ID is required to create a patient.",
            )

        existing = await self.repo.get_patient_by_phone(
            patient_data.phone, patient_data.facility_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A patient with this phone number already exists in this facility.",
            )

        # Separate the nested pregnancy data before ORM construction.
        # Passing it through model_dump() would include `first_pregnancy` as a
        # dict kwarg to PregnantPatient(**...) which has no such column.
        patient_dict = patient_data.model_dump(exclude={"first_pregnancy"})
        patient_dict["patient_type"] = PatientType.PREGNANT
        patient_dict["status"] = PatientStatus.ACTIVE

        db_patient = PregnantPatient(**patient_dict)

        # Open the first pregnancy episode using the model's business logic.
        # This increments gravida to 1 and sets pregnancy_number = 1.
        pregnancy = db_patient.open_new_pregnancy()

        # Apply any clinical data that was provided in the request.
        first_preg_data = patient_data.first_pregnancy
        if first_preg_data.lmp_date:
            pregnancy.lmp_date = first_preg_data.lmp_date
        if first_preg_data.expected_delivery_date:
            pregnancy.expected_delivery_date = first_preg_data.expected_delivery_date
        if first_preg_data.gestational_age_weeks is not None:
            pregnancy.gestational_age_weeks = first_preg_data.gestational_age_weeks
        if first_preg_data.risk_factors:
            pregnancy.risk_factors = first_preg_data.risk_factors
        if first_preg_data.notes:
            pregnancy.notes = first_preg_data.notes

        # create_pregnant_patient cascades the Pregnancy via the relationship.
        return await self.repo.create_pregnant_patient(db_patient)

    async def get_pregnant_patient(self, patient_id: uuid.UUID) -> PregnantPatient:
        """Get pregnant patient by ID."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        return patient

    async def update_pregnant_patient(
        self,
        updated_by_id: uuid.UUID,
        patient_id: uuid.UUID,
        update_data: PregnantPatientUpdateSchema,
    ) -> PregnantPatient:
        """Update patient-level fields on a PregnantPatient."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )

        update_dict = update_data.model_dump(exclude_unset=True)

        if "phone" in update_dict and update_dict["phone"] != patient.phone:
            existing = await self.repo.get_patient_by_phone(
                update_dict["phone"], patient.facility_id
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A patient with this phone number already exists.",
                )

        for field, value in update_dict.items():
            setattr(patient, field, value)

        return await self.repo.update_pregnant_patient(updated_by_id, patient)

    async def convert_to_regular_patient(
        self,
        user_id: uuid.UUID,
        patient_id: uuid.UUID,
        conversion_data: ConvertToRegularPatientSchema,
    ) -> RegularPatient:
        """
        Convert a pregnant patient to a regular patient after delivery.

        How it works:
          1. Close the active Pregnancy episode with the provided outcome.
          2. Update the patient_type discriminator on the base Patient row.
          3. Create a RegularPatient subtype row using the SAME primary key,
             so all existing prescriptions, vaccinations, and payments remain
             linked to the same patient_id.
          4. Soft-mark the old pregnant_patients row (via status = POSTPARTUM)
             — the actual row is kept for Pregnancy/Child history.

        The old approach created a brand new UUID, permanently orphaning all
        related records. That approach has been replaced here.
        """
        pregnant_patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not pregnant_patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )

        if pregnant_patient.status not in (PatientStatus.ACTIVE, PatientStatus.POSTPARTUM):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only active or postpartum patients can be converted.",
            )

        # Step 1: close the active Pregnancy episode.
        active_pregnancy = await self.repo.get_active_pregnancy(patient_id)
        if active_pregnancy:
            # increment_para=True for LIVE_BIRTH and STILLBIRTH; the model
            # method handles it; we pass the flag based on outcome type.
            from app.schemas.patient_schemas import PregnancyOutcome
            increment = conversion_data.outcome in (
                PregnancyOutcome.LIVE_BIRTH,
                PregnancyOutcome.STILLBIRTH,
            )
            try:
                pregnant_patient.close_active_pregnancy(
                    outcome=conversion_data.outcome,
                    delivery_date=conversion_data.actual_delivery_date,
                    increment_para=increment,
                )
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                )
            await self.repo.update_pregnant_patient(user_id, pregnant_patient)

        # Step 2 & 3: change the discriminator and insert the RegularPatient row
        # with the SAME primary key so all FK-linked records stay intact.
        #
        # SQLAlchemy joined-table inheritance requires:
        #   a. Update patient_type on the base patients row.
        #   b. Insert a row into regular_patients with the same id.
        #   c. The pregnant_patients row is kept (Pregnancy/Child history lives there).
        #
        # We do this at the ORM level by directly modifying the discriminator
        # and adding the new subtype row.
        pregnant_patient.patient_type = PatientType.REGULAR
        pregnant_patient.status = PatientStatus.POSTPARTUM
        pregnant_patient.updated_by_id = user_id

        delivery_date = conversion_data.actual_delivery_date or (
            active_pregnancy.actual_delivery_date if active_pregnancy else None
        )

        regular_patient = RegularPatient(
            id=patient_id,                               # same PK — keeps all FKs intact
            diagnosis_date=delivery_date,
            treatment_start_date=delivery_date,
            treatment_regimen=conversion_data.treatment_regimen,
            notes=conversion_data.notes,
        )

        # Add only the RegularPatient subtype row — the base patients row already
        # exists and will be updated via the flush.
        self.db.add(pregnant_patient)
        self.db.add(regular_patient)
        await self.db.commit()
        await self.db.refresh(regular_patient)
        return regular_patient

    # =========================================================================
    # Regular patient
    # =========================================================================

    async def create_regular_patient(
        self, patient_data: RegularPatientCreateSchema
    ) -> RegularPatient:
        """Create a new regular patient."""
        if patient_data.facility_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Facility ID is required to create a patient.",
            )

        existing = await self.repo.get_patient_by_phone(
            patient_data.phone, patient_data.facility_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A patient with this phone number already exists in this facility.",
            )

        patient_dict = patient_data.model_dump()
        patient_dict["patient_type"] = PatientType.REGULAR
        patient_dict["status"] = PatientStatus.ACTIVE

        db_patient = RegularPatient(**patient_dict)
        return await self.repo.create_regular_patient(db_patient)

    async def get_regular_patient(self, patient_id: uuid.UUID) -> RegularPatient:
        """Get regular patient by ID."""
        patient = await self.repo.get_regular_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regular patient not found.",
            )
        return patient

    async def update_regular_patient(
        self,
        updated_by_id: uuid.UUID,
        patient_id: uuid.UUID,
        update_data: RegularPatientUpdateSchema,
    ) -> RegularPatient:
        """Update regular patient."""
        patient = await self.repo.get_regular_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regular patient not found.",
            )

        update_dict = update_data.model_dump(exclude_unset=True)

        if "phone" in update_dict and update_dict["phone"] != patient.phone:
            existing = await self.repo.get_patient_by_phone(
                update_dict["phone"], patient.facility_id
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A patient with this phone number already exists.",
                )

        for field, value in update_dict.items():
            setattr(patient, field, value)

        return await self.repo.update_regular_patient(updated_by_id, patient)

    # =========================================================================
    # Common patient
    # =========================================================================

    async def list_patients_paginated(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        patient_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[List, int]:
        """Paginated patient list with validation."""
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page number must be greater than 0.",
            )
        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page size must be between 1 and 100.",
            )
        if patient_type and patient_type not in ("pregnant", "regular"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid patient_type. Must be 'pregnant' or 'regular'.",
            )
        if patient_status:
            try:
                PatientStatus(patient_status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid patient_status. Must be one of: {[s.value for s in PatientStatus]}.",
                )

        skip = (page - 1) * page_size
        return await self.repo.list_patients_paginated(
            facility_id=facility_id,
            patient_type=patient_type,
            patient_status=patient_status,
            skip=skip,
            limit=page_size,
        )

    async def delete_patient(self, patient_id: uuid.UUID) -> bool:
        """Soft delete a patient."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        await self.repo.delete_patient(patient)
        return True

    # =========================================================================
    # Pregnancy
    # =========================================================================

    async def open_pregnancy(
        self,
        patient_id: uuid.UUID,
        pregnancy_data: PregnancyCreateSchema,
    ) -> Pregnancy:
        """
        Open a new pregnancy episode for a returning pregnant patient.

        Raises 404 if patient not found, 400 if she already has an active
        pregnancy (enforced by PregnantPatient.open_new_pregnancy()).
        """
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )

        try:
            pregnancy = patient.open_new_pregnancy()
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )

        # Apply provided clinical data.
        if pregnancy_data.lmp_date:
            pregnancy.lmp_date = pregnancy_data.lmp_date
        if pregnancy_data.expected_delivery_date:
            pregnancy.expected_delivery_date = pregnancy_data.expected_delivery_date
        if pregnancy_data.gestational_age_weeks is not None:
            pregnancy.gestational_age_weeks = pregnancy_data.gestational_age_weeks
        if pregnancy_data.risk_factors:
            pregnancy.risk_factors = pregnancy_data.risk_factors
        if pregnancy_data.notes:
            pregnancy.notes = pregnancy_data.notes

        # Persist the updated gravida count and the new Pregnancy row.
        await self.repo.update_pregnant_patient(patient_id, patient)
        return await self.repo.create_pregnancy(pregnancy)

    async def get_pregnancy(self, pregnancy_id: uuid.UUID) -> Pregnancy:
        """Get a pregnancy episode by ID."""
        pregnancy = await self.repo.get_pregnancy_by_id(pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        return pregnancy

    async def list_patient_pregnancies(
        self, patient_id: uuid.UUID
    ) -> List[Pregnancy]:
        """List all pregnancy episodes for a patient."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        return await self.repo.get_patient_pregnancies(patient_id)

    async def update_pregnancy(
        self,
        pregnancy_id: uuid.UUID,
        update_data: PregnancyUpdateSchema,
    ) -> Pregnancy:
        """Update clinical data on an active pregnancy episode."""
        pregnancy = await self.repo.get_pregnancy_by_id(pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        if not pregnancy.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update a closed pregnancy episode.",
            )

        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(pregnancy, field, value)

        return await self.repo.update_pregnancy(pregnancy)

    async def close_pregnancy(
        self,
        pregnancy_id: uuid.UUID,
        close_data: PregnancyCloseSchema,
        closing_user_id: uuid.UUID,
    ) -> Pregnancy:
        """
        Close an active pregnancy episode with a clinical outcome.

        Also updates para on the parent PregnantPatient when appropriate.
        """
        pregnancy = await self.repo.get_pregnancy_by_id(pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        if not pregnancy.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This pregnancy episode is already closed.",
            )

        # Update the episode itself.
        pregnancy.close(
            outcome=close_data.outcome,
            delivery_date=close_data.delivery_date,
        )

        # Update para on the parent patient if warranted.
        if close_data.increment_para:
            patient = await self.repo.get_pregnant_patient_by_id(pregnancy.patient_id)
            if patient:
                patient.para += 1
                await self.repo.update_pregnant_patient(closing_user_id, patient)

        return await self.repo.update_pregnancy(pregnancy)

    # =========================================================================
    # Child
    # =========================================================================

    async def create_child(self, child_data: ChildCreateSchema) -> Child:
        """
        Create a child record linked to a specific pregnancy episode.

        Automatically calculates the six-month checkup date from date_of_birth.
        Verifies the pregnancy exists before creating the child.
        """
        if child_data.pregnancy_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pregnancy ID is required to create a child record.",
            )

        pregnancy = await self.repo.get_pregnancy_by_id(child_data.pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )

        child_dict = child_data.model_dump()
        child_dict["six_month_checkup_date"] = (
            child_data.date_of_birth + timedelta(days=180)
        )

        child = Child(**child_dict)
        self.db.add(child)
        await self.db.flush()  # flush to get the child ID for logging
        await self.db.refresh(child, ["pregnancy"])
        return child

    async def get_child(self, child_id: uuid.UUID) -> Child:
        """Get child by ID."""
        child = await self.repo.get_child_by_id(child_id)
        if not child:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child record not found.",
            )
        return child

    async def update_child(
        self,
        child_id: uuid.UUID,
        update_data: ChildUpdateSchema,
        updated_by_id: Optional[uuid.UUID] = None,
    ) -> Child:
        """Update child monitoring fields."""
        child = await self.repo.get_child_by_id(child_id)
        if not child:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child record not found.",
            )
        update_dict = update_data.model_dump(exclude_unset=True)
        # Stamp the audit field regardless of whether the caller included it
        # in the schema body — always prefer the injected auth-context value.
        if updated_by_id is not None:
            update_dict["updated_by_id"] = updated_by_id
        for field, value in update_dict.items():
            setattr(child, field, value)
        return await self.repo.update_child(child)

    async def list_pregnancy_children(
        self, pregnancy_id: uuid.UUID
    ) -> List[Child]:
        """List all children born from a specific pregnancy episode."""
        pregnancy = await self.repo.get_pregnancy_by_id(pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        return await self.repo.get_pregnancy_children(pregnancy_id)

    async def list_mother_children(self, patient_id: uuid.UUID) -> List[Child]:
        """List all children for a mother across all her pregnancies."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        return await self.repo.get_mother_children(patient_id)

    # =========================================================================
    # Prescription
    # =========================================================================

    async def create_prescription(
        self, prescription_data: PrescriptionCreateSchema
    ) -> Prescription:
        if prescription_data.patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient ID is required to create a prescription.",
            )
        patient = await self.repo.get_patient_by_id(prescription_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        prescription_dict = prescription_data.model_dump()
        prescription_dict["is_active"] = True
        return await self.repo.create_prescription(Prescription(**prescription_dict))

    async def get_prescription(self, prescription_id: uuid.UUID) -> Prescription:
        prescription = await self.repo.get_prescription_by_id(prescription_id)
        if not prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found.",
            )
        return prescription

    async def update_prescription(
        self, prescription_id: uuid.UUID, update_data: PrescriptionUpdateSchema
    ) -> Prescription:
        prescription = await self.repo.get_prescription_by_id(prescription_id)
        if not prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found.",
            )
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(prescription, field, value)
        return await self.repo.update_prescription(prescription)

    async def list_patient_prescriptions(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[Prescription]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        return await self.repo.get_patient_prescriptions(patient_id, active_only)

    # =========================================================================
    # Medication schedule
    # =========================================================================

    async def create_medication_schedule(
        self, schedule_data: MedicationScheduleCreateSchema
    ) -> MedicationSchedule:
        if schedule_data.patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient ID is required to create a medication schedule.",
            )
        patient = await self.repo.get_patient_by_id(schedule_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        schedule_dict = schedule_data.model_dump()
        schedule_dict.update(
            is_completed=False,
            lab_review_scheduled=False,
            lab_review_completed=False,
        )
        return await self.repo.create_medication_schedule(
            MedicationSchedule(**schedule_dict)
        )

    async def get_medication_schedule(
        self, schedule_id: uuid.UUID
    ) -> MedicationSchedule:
        schedule = await self.repo.get_medication_schedule_by_id(schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medication schedule not found.",
            )
        return schedule

    async def update_medication_schedule(
        self, schedule_id: uuid.UUID, update_data: MedicationScheduleUpdateSchema
    ) -> MedicationSchedule:
        schedule = await self.repo.get_medication_schedule_by_id(schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medication schedule not found.",
            )
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(schedule, field, value)
        return await self.repo.update_medication_schedule(schedule)

    async def list_patient_medication_schedules(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[MedicationSchedule]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        return await self.repo.get_patient_medication_schedules(patient_id, active_only)

    # =========================================================================
    # Reminder
    # =========================================================================

    async def create_reminder(
        self, reminder_data: PatientReminderCreateSchema
    ) -> PatientReminder:
        if reminder_data.patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient ID is required to create a reminder.",
            )
        patient = await self.repo.get_patient_by_id(reminder_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        if reminder_data.child_id:
            child = await self.repo.get_child_by_id(reminder_data.child_id)
            if not child:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Child not found."
                )
        reminder_dict = reminder_data.model_dump()
        reminder_dict["status"] = "pending"
        return await self.repo.create_reminder(PatientReminder(**reminder_dict))

    async def get_reminder(self, reminder_id: uuid.UUID) -> PatientReminder:
        reminder = await self.repo.get_reminder_by_id(reminder_id)
        if not reminder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found."
            )
        return reminder

    async def update_reminder(
        self, reminder_id: uuid.UUID, update_data: PatientReminderUpdateSchema
    ) -> PatientReminder:
        reminder = await self.repo.get_reminder_by_id(reminder_id)
        if not reminder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found."
            )
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(reminder, field, value)
        return await self.repo.update_reminder(reminder)

    async def list_patient_reminders(
        self, patient_id: uuid.UUID, pending_only: bool = False
    ) -> List[PatientReminder]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        return await self.repo.get_patient_reminders(patient_id, pending_only)