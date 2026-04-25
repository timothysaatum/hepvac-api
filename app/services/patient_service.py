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
    PatientReminder, Diagnosis,
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
    ReRegisterAsPregnantSchema,
    PatientStatus,
    PatientType, DiagnosisCreateSchema, DiagnosisUpdateSchema,
)
from app.repositories.patient_repo import PatientRepository
from app.services.reminder_schedule import build_reminder_rows, cancel_pending_reminders
from app.schemas.patient_schemas import ReminderType


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
        created = await self.repo.create_pregnant_patient(db_patient)

        # Generate delivery reminders immediately if EDD was provided at registration
        if first_preg_data.expected_delivery_date:
            rows = build_reminder_rows(
                patient_id=created.id,
                due_date=first_preg_data.expected_delivery_date,
                reminder_type=ReminderType.DELIVERY_WEEK,
                patient_name=created.name,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return created

    async def get_pregnant_patient(self, patient_id: uuid.UUID) -> PregnantPatient:
        """Get pregnant patient by ID."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            # If the base patient exists but is now regular, this endpoint is
            # simply the wrong resource. The unified GET /patients/{id} endpoint
            # should be used when the frontend does not know the current type.
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
        from app.core.utils import logger
        
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
                logger.log_error({
                    "event": "pregnancy_closure_failed",
                    "patient_id": str(patient_id),
                    "error": str(e)
                })
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                )
            await self.repo.update_pregnant_patient(user_id, pregnant_patient)

        # Steps 2 & 3: raw SQL to avoid ORM INSERT on the existing patients row.
        #
        # db.add(RegularPatient(id=existing_id)) looks new to SQLAlchemy's identity
        # map → it emits INSERT INTO patients with nulls → NOT NULL violation on name.
        # The patients row already exists; we only need to:
        #   a. UPDATE the discriminator column.
        #   b. INSERT into regular_patients (subtype table only).
        from sqlalchemy import text as _text, select as _select

        delivery_date = conversion_data.actual_delivery_date or (
            active_pregnancy.actual_delivery_date if active_pregnancy else None
        )

        try:
            await self.db.execute(
                _text("""
                    UPDATE patients
                    SET patient_type  = 'REGULAR',
                        status        = 'POSTPARTUM',
                        updated_by_id = :user_id
                    WHERE id = :patient_id
                """),
                {"user_id": str(user_id), "patient_id": str(patient_id)},
            )

            await self.db.execute(
                _text("""
                    INSERT INTO regular_patients
                        (id, diagnosis_date, treatment_start_date, treatment_regimen, notes)
                    VALUES
                        (:id, :diagnosis_date, :treatment_start_date, :treatment_regimen, :notes)
                    ON CONFLICT (id) DO UPDATE SET
                        diagnosis_date = COALESCE(EXCLUDED.diagnosis_date, regular_patients.diagnosis_date),
                        treatment_start_date = COALESCE(EXCLUDED.treatment_start_date, regular_patients.treatment_start_date),
                        treatment_regimen = COALESCE(EXCLUDED.treatment_regimen, regular_patients.treatment_regimen),
                        notes = COALESCE(EXCLUDED.notes, regular_patients.notes)
                """),
                {
                    "id":                   str(patient_id),
                    "diagnosis_date":       delivery_date,
                    "treatment_start_date": delivery_date,
                    "treatment_regimen":    conversion_data.treatment_regimen,
                    "notes":                conversion_data.notes,
                },
            )

            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.log_error({
                "event": "conversion_transaction_failed",
                "patient_id": str(patient_id),
                "error": str(e)
            }, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Conversion transaction failed. Please try again.",
            )

        # FIX: expunge_all() instead of expire_all().
        # expire_all() only marks attributes stale — it does NOT remove the
        # PregnantPatient object from the identity map. The subsequent
        # select(RegularPatient) would find the cached PregnantPatient for this
        # PK and return None or the wrong type. expunge_all() fully evicts all
        # objects so the next SELECT builds a fresh RegularPatient from the DB.
        self.db.expunge_all()

        # Reload with a clean SELECT with all eager loads the response schema needs.
        # RegularPatient relationships are lazy="noload" — selectinload is required
        # or from_patient() will trigger implicit lazy loads → MissingGreenlet error.
        from sqlalchemy.orm import selectinload as _sil
        result = await self.db.execute(
            _select(RegularPatient)
            .where(RegularPatient.id == patient_id)
            .options(
                _sil(RegularPatient.facility),
                _sil(RegularPatient.created_by),
                _sil(RegularPatient.updated_by),
            )
        )
        regular_patient = result.scalars().first()
        
        if not regular_patient:
            logger.log_error({
                "event": "conversion_verification_failed",
                "patient_id": str(patient_id),
                "detail": "Could not reload RegularPatient after conversion"
            })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Conversion succeeded but patient could not be reloaded.",
            )
        
        logger.log_info({
            "event": "patient_converted_to_regular",
            "patient_id": str(patient_id),
            "converted_by": str(user_id),
        })
        
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

    async def get_patient(self, patient_id: uuid.UUID):
        """Get a patient by ID, automatically returning the current subtype."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )
        return patient

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
        updated_by_id: uuid.UUID,
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
        await self.repo.update_pregnant_patient(updated_by_id, patient)
        created_pregnancy = await self.repo.create_pregnancy(pregnancy)

        # Generate delivery reminders if EDD was provided when opening the episode
        if created_pregnancy.expected_delivery_date:
            patient_record = await self.repo.get_pregnant_patient_by_id(patient_id)
            patient_name = patient_record.name if patient_record else "Dear patient"
            rows = build_reminder_rows(
                patient_id=patient_id,
                due_date=created_pregnancy.expected_delivery_date,
                reminder_type=ReminderType.DELIVERY_WEEK,
                patient_name=patient_name,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return created_pregnancy

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

        update_dict = update_data.model_dump(exclude_unset=True)

        # Track whether EDD is actually changing before applying updates
        edd_changed = (
            "expected_delivery_date" in update_dict
            and update_dict["expected_delivery_date"] != pregnancy.expected_delivery_date
        )

        for field, value in update_dict.items():
            setattr(pregnancy, field, value)

        updated = await self.repo.update_pregnancy(pregnancy)

        # Regenerate delivery reminders when EDD is set or changed
        if edd_changed and updated.expected_delivery_date:
            patient = await self.repo.get_pregnant_patient_by_id(updated.patient_id)
            patient_name = patient.name if patient else "Dear patient"

            # Cancel all pending delivery reminders for this patient first
            await cancel_pending_reminders(
                db=self.repo.db,
                patient_id=updated.patient_id,
                reminder_type=ReminderType.DELIVERY_WEEK,
            )

            # Build and persist the fresh escalating reminder set
            rows = build_reminder_rows(
                patient_id=updated.patient_id,
                due_date=updated.expected_delivery_date,
                reminder_type=ReminderType.DELIVERY_WEEK,
                patient_name=patient_name,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return updated

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

        # Generate 6-month checkup reminders immediately — the date is always
        # set at creation, so no need to wait for an update.
        if child.six_month_checkup_date and child.pregnancy:
            patient = await self.repo.get_pregnant_patient_by_id(child.pregnancy.patient_id)
            patient_name = patient.name if patient else "Dear patient"

            rows = build_reminder_rows(
                patient_id=child.pregnancy.patient_id,
                due_date=child.six_month_checkup_date,
                reminder_type=ReminderType.CHILD_6MONTH_CHECKUP,
                patient_name=patient_name,
                child_id=child.id,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

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

        # Detect if six_month_checkup_date is being set or changed
        checkup_changed = (
            "six_month_checkup_date" in update_dict
            and update_dict["six_month_checkup_date"] != child.six_month_checkup_date
        )

        for field, value in update_dict.items():
            setattr(child, field, value)

        updated_child = await self.repo.update_child(child)

        # Regenerate checkup reminders when the date changes and checkup isn't done yet
        if checkup_changed and updated_child.six_month_checkup_date and not updated_child.six_month_checkup_completed:
            pregnancy = await self.repo.get_pregnancy_by_id(updated_child.pregnancy_id)
            patient_name = "Dear patient"
            if pregnancy:
                patient = await self.repo.get_pregnant_patient_by_id(pregnancy.patient_id)
                if patient:
                    patient_name = patient.name

            # Cancel existing pending checkup reminders for this specific child
            await cancel_pending_reminders(
                db=self.repo.db,
                patient_id=pregnancy.patient_id if pregnancy else updated_child.pregnancy_id,
                reminder_type=ReminderType.CHILD_6MONTH_CHECKUP,
                child_id=updated_child.id,
            )

            # Build and persist the fresh escalating reminder set
            rows = build_reminder_rows(
                patient_id=pregnancy.patient_id if pregnancy else updated_child.pregnancy_id,
                due_date=updated_child.six_month_checkup_date,
                reminder_type=ReminderType.CHILD_6MONTH_CHECKUP,
                patient_name=patient_name,
                child_id=updated_child.id,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return updated_child

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

    async def list_patient_reminders_paginated(
        self,
        patient_id: uuid.UUID,
        pagination,  # PaginationParams
        status_filter: Optional[str] = None,
        upcoming_only: bool = False,
    ):
        """Get paginated reminders with smart filtering and ordering."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        return await self.repo.get_patient_reminders_paginated(
            patient_id=patient_id,
            pagination=pagination,
            status_filter=status_filter,
            upcoming_only=upcoming_only,
        )

    # =========================================================================
    # Diagnosis
    # =========================================================================

    async def create_diagnosis(
                self, diagnosis_data: DiagnosisCreateSchema
        ) -> Diagnosis:
        if diagnosis_data.patient_id is None:
            raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Patient ID is required to create a diagnosis.",
                )
        patient = await self.repo.get_patient_by_id(diagnosis_data.patient_id)
        if not patient:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
                )
        diagnosis_dict = diagnosis_data.model_dump()
        return await self.repo.create_diagnosis(Diagnosis(**diagnosis_dict))

    async def get_diagnosis(self, diagnosis_id: uuid.UUID) -> Diagnosis:
        diagnosis = await self.repo.get_diagnosis_by_id(diagnosis_id)
        if not diagnosis:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found."
                )
        return diagnosis

    async def update_diagnosis(
                self, diagnosis_id: uuid.UUID, update_data: DiagnosisUpdateSchema
        ) -> Diagnosis:
        diagnosis = await self.repo.get_diagnosis_by_id(diagnosis_id)
        if not diagnosis:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found."
                )
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(diagnosis, field, value)
        return await self.repo.update_diagnosis(diagnosis)

    async def delete_diagnosis(self, diagnosis_id: uuid.UUID) -> None:
        diagnosis = await self.repo.get_diagnosis_by_id(diagnosis_id)
        if not diagnosis:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found."
                )
        diagnosis.is_deleted = True
        from datetime import datetime, timezone
        diagnosis.deleted_at = datetime.now(timezone.utc)
        await self.repo.update_diagnosis(diagnosis)

    async def list_patient_diagnoses(
                self, patient_id: uuid.UUID
        ) -> list[Diagnosis]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
                )
        return await self.repo.get_patient_diagnoses(patient_id)

    # =========================================================================
    # Re-register as pregnant
    # =========================================================================

    async def re_register_as_pregnant(
        self,
        user_id: uuid.UUID,
        patient_id: uuid.UUID,
        pregnancy_data: "ReRegisterAsPregnantSchema",
    ) -> PregnantPatient:
        """
        Re-register a regular patient as pregnant (second or later pregnancy).

        The pregnant_patients row is never deleted on conversion — it stays for
        history. So re-registration only needs to:
          1. UPDATE the discriminator back to PREGNANT.
          2. Load the existing PregnantPatient ORM object.
          3. Call open_new_pregnancy() — increments gravida, creates new episode.
          4. Apply any clinical data from the request.
          5. Commit. No INSERT into pregnant_patients needed.
        """
        from sqlalchemy import text as _text, select as _select
        from app.core.utils import logger

        # FIX: expunge_all() instead of expire_all().
        # expire_all() only marks attributes stale — it does NOT evict objects
        # from the identity map. If a prior request in the same worker loaded
        # this patient as PregnantPatient, get_regular_patient_by_id() would
        # encounter a discriminator mismatch, silently return None, and cause
        # a false 409. expunge_all() fully clears the identity map so every
        # subsequent query builds fresh ORM instances from the current DB state.
        self.db.expunge_all()

        regular = await self.repo.get_regular_patient_by_id(patient_id)
        if not regular:
            base = await self.repo.get_patient_by_id(patient_id)
            if base:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Patient is already registered as pregnant.",
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regular patient not found.",
            )

        # Step 1: Flip discriminator back to PREGNANT.
        await self.db.execute(
            _text("""
                UPDATE patients
                SET patient_type  = 'PREGNANT',
                    status        = 'ACTIVE',
                    updated_by_id = :user_id
                WHERE id = :patient_id
            """),
            {"user_id": str(user_id), "patient_id": str(patient_id)},
        )
        await self.db.commit()

        # FIX: expunge_all() instead of expire_all().
        # This is the critical call. After the raw SQL UPDATE above, the identity
        # map still holds the RegularPatient instance for this UUID. expire_all()
        # would refresh its attribute values but cannot change its Python class.
        # The subsequent select(PregnantPatient) would hit the identity map,
        # find the cached RegularPatient, and return it — causing the
        # AttributeError: 'RegularPatient' object has no attribute 'open_new_pregnancy'.
        # expunge_all() fully evicts all objects so SQLAlchemy builds a fresh
        # PregnantPatient from the updated DB row.
        self.db.expunge_all()

        # Load the existing PregnantPatient row with all relationships the response
        # schema needs (facility, created_by, updated_by, pregnancies).
        # All relationships are lazy="noload" — they MUST be selectinload'd here.
        from sqlalchemy.orm import selectinload as _sil
        result = await self.db.execute(
            _select(PregnantPatient)
            .where(PregnantPatient.id == patient_id)
            .options(
                _sil(PregnantPatient.facility),
                _sil(PregnantPatient.created_by),
                _sil(PregnantPatient.updated_by),
                _sil(PregnantPatient.pregnancies),
            )
        )
        pregnant_patient = result.scalars().first()
        
        # CRITICAL FIX: If pregnant_patients row is missing, create it now.
        # This can happen if the initial conversion had data inconsistencies.
        if not pregnant_patient:
            logger.log_warning({
                "event": "pregnant_patients_row_missing_during_reregistration",
                "patient_id": str(patient_id),
                "detail": "Creating missing pregnant_patients row"
            })
            
            # Create the missing subtype row with default/inherited values
            await self.db.execute(
                _text("""
                    INSERT INTO pregnant_patients
                        (id, gravida, para)
                    VALUES
                        (:id, 1, :para)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": str(patient_id),
                    "para": regular.para if hasattr(regular, "para") else 0,
                },
            )
            await self.db.commit()
            self.db.expunge_all()
            
            # Retry load
            result = await self.db.execute(
                _select(PregnantPatient)
                .where(PregnantPatient.id == patient_id)
                .options(
                    _sil(PregnantPatient.facility),
                    _sil(PregnantPatient.created_by),
                    _sil(PregnantPatient.updated_by),
                    _sil(PregnantPatient.pregnancies),
                )
            )
            pregnant_patient = result.scalars().first()
        
        if not pregnant_patient:
            logger.log_error({
                "event": "re_register_pregnant_fatal_error",
                "patient_id": str(patient_id),
                "detail": "Still could not load PregnantPatient after row creation"
            })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Re-registration failed: unable to load patient data.",
            )

        # Step 3: Open the new episode via the model's business logic.
        try:
            pregnancy = pregnant_patient.open_new_pregnancy()
        except ValueError as e:
            logger.log_warning({
                "event": "pregnancy_creation_failed",
                "patient_id": str(patient_id),
                "error": str(e)
            })
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )

        # Apply optional clinical data.
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

        pregnant_patient.updated_by_id = user_id
        self.db.add(pregnant_patient)
        await self.db.commit()

        logger.log_info({
            "event": "pregnancy_episode_opened",
            "patient_id": str(patient_id),
            "gravida": pregnant_patient.gravida,
        })

        # After commit, do a final SELECT with all eager loads so the response
        # schema can access facility/created_by/updated_by/pregnancies without
        # triggering implicit lazy loads on an async session (MissingGreenlet).
        self.db.expunge_all()
        final = await self.db.execute(
            _select(PregnantPatient)
            .where(PregnantPatient.id == patient_id)
            .options(
                _sil(PregnantPatient.facility),
                _sil(PregnantPatient.created_by),
                _sil(PregnantPatient.updated_by),
                _sil(PregnantPatient.pregnancies),
            )
        )
        return final.scalars().first()