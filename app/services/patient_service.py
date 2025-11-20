from datetime import timedelta
from typing import List, Optional
import uuid
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_model import (
    PregnantPatient,
    RegularPatient,
    Child,
    Prescription,
    MedicationSchedule,
    PatientReminder,
)
from app.schemas.patient_schemas import (
    PregnantPatientCreateSchema,
    PregnantPatientUpdateSchema,
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
)
from app.repositories.patient_repo import PatientRepository


class PatientService:
    """Service layer for patient business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PatientRepository(self.db)

    # ============= Pregnant Patient Services =============
    async def create_pregnant_patient(
        self, patient_data: PregnantPatientCreateSchema
    ) -> PregnantPatient:
        """Create a new pregnant patient."""
        # # Check if patient with phone already exists in facility
        existing = await self.repo.get_patient_by_phone(
            patient_data.phone, patient_data.facility_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient with this phone number already exists in this facility",
            )

        patient_dict = patient_data.model_dump()
        patient_dict["patient_type"] = "pregnant"
        patient_dict["status"] = PatientStatus.ACTIVE

        db_patient = PregnantPatient(**patient_dict)
        return await self.repo.create_pregnant_patient(db_patient)

    async def get_pregnant_patient(self, patient_id: uuid.UUID) -> PregnantPatient:
        """Get pregnant patient by ID."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found",
            )
        return patient

    async def update_pregnant_patient(
        self,updated_by_id:uuid.UUID, patient_id: uuid.UUID, update_data: PregnantPatientUpdateSchema
    ) -> PregnantPatient:
        """Update pregnant patient."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found",
            )

        update_dict = update_data.model_dump(exclude_unset=True)

        # Check if phone is being updated and already exists
        if "phone" in update_dict and update_dict["phone"] != patient.phone:
            existing = await self.repo.get_patient_by_phone(
                update_dict["phone"], patient.facility_id
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Patient with this phone number already exists",
                )

        for field, value in update_dict.items():
            setattr(patient, field, value)

        return await self.repo.update_pregnant_patient(updated_by_id, patient)

    async def convert_to_regular_patient(
        self, user_id: uuid.UUID, patient_id: uuid.UUID, conversion_data: ConvertToRegularPatientSchema
    ) -> RegularPatient:
        """Convert pregnant patient to regular patient after delivery."""
        pregnant_patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not pregnant_patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found",
            )

        if pregnant_patient.status != PatientStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient must be in active status to convert",
            )

        # Create regular patient with data from pregnant patient
        regular_patient_data = {
            "name": pregnant_patient.name,
            "phone": pregnant_patient.phone,
            "sex": pregnant_patient.sex,
            "age": pregnant_patient.age,
            # "date_of_birth": pregnant_patient.date_of_birth,
            "facility_id": pregnant_patient.facility_id,
            "created_by_id": pregnant_patient.created_by_id,
            "patient_type": "regular",
            "status": PatientStatus.ACTIVE,
            "diagnosis_date": pregnant_patient.actual_delivery_date,
            "treatment_start_date": pregnant_patient.actual_delivery_date,
            "treatment_regimen": conversion_data.treatment_regimen,
            "notes": conversion_data.notes,
        }

        regular_patient = RegularPatient(**regular_patient_data)
        created_patient = await self.repo.create_regular_patient(regular_patient)

        # Update pregnant patient status
        pregnant_patient.status = PatientStatus.POSTPARTUM
        pregnant_patient.actual_delivery_date = conversion_data.actual_delivery_date
        # await self.repo.update_pregnant_patient(pregnant_patient)
        await self.repo.update_pregnant_patient(user_id, pregnant_patient)

        return created_patient

    # ============= Regular Patient Services =============
    async def create_regular_patient(
        self, patient_data: RegularPatientCreateSchema
    ) -> RegularPatient:
        """Create a new regular patient."""
        existing = await self.repo.get_patient_by_phone(
            patient_data.phone, patient_data.facility_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient with this phone number already exists in this facility",
            )

        patient_dict = patient_data.model_dump()
        patient_dict["patient_type"] = "regular"
        patient_dict["status"] = PatientStatus.ACTIVE

        db_patient = RegularPatient(**patient_dict)
        return await self.repo.create_regular_patient(db_patient)

    async def get_regular_patient(self, patient_id: uuid.UUID) -> RegularPatient:
        """Get regular patient by ID."""
        patient = await self.repo.get_regular_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regular patient not found",
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
                detail="Regular patient not found",
            )

        update_dict = update_data.model_dump(exclude_unset=True)

        if "phone" in update_dict and update_dict["phone"] != patient.phone:
            existing = await self.repo.get_patient_by_phone(
                update_dict["phone"], patient.facility_id
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Patient with this phone number already exists",
                )

        for field, value in update_dict.items():
            setattr(patient, field, value)

        return await self.repo.update_regular_patient(updated_by_id, patient)

    # ============= Common Patient Services =============
    async def list_patients(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List:
        """List patients with optional filters."""
        return await self.repo.get_patients(facility_id, patient_type, status)

    async def list_patients_paginated(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        patient_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[List, int]:
        """
        Get paginated list of patients with filters.

        Args:
            facility_id: Filter by facility
            patient_type: Filter by patient type (pregnant/regular)
            patient_status: Filter by patient status
            page: Page number (starts at 1)
            page_size: Items per page

        Returns:
            Tuple of (list of patients, total count)
        """
        # Validate pagination parameters
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page number must be greater than 0",
            )

        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page size must be between 1 and 100",
            )

        # Validate patient_type if provided
        if patient_type and patient_type not in ["pregnant", "regular"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid patient_type. Must be 'pregnant' or 'regular'",
            )

        # Validate patient_status if provided
        if patient_status:
            try:
                PatientStatus(patient_status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid patient_status. Must be one of: {[s.value for s in PatientStatus]}",
                )

        # Calculate skip
        skip = (page - 1) * page_size

        # Get patients from repository
        patients, total_count = await self.repo.list_patients_paginated(
            facility_id=facility_id,
            patient_type=patient_type,
            patient_status=patient_status,
            skip=skip,
            limit=page_size,
        )

        return patients, total_count

    async def delete_patient(self, patient_id: uuid.UUID) -> bool:
        """Soft delete a patient."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
            )

        await self.repo.delete_patient(patient)
        return True

    # ============= Child Services =============
    async def create_child(self, child_data: ChildCreateSchema) -> Child:
        """Create a new child record."""
        # Verify mother exists
        mother = await self.repo.get_patient_by_id(child_data.mother_id)
        if not mother:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Mother not found"
            )

        if not mother.patient_type.PREGNANT:
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Cannot create child for regular patients"
            )

        child_dict = child_data.model_dump()
        due_date = child_dict.get("date_of_birth") + timedelta(days=180)
        child_dict["six_month_checkup_date"] = due_date
        child = Child(**child_dict)
        return await self.repo.create_child(child)

    async def get_child(self, child_id: uuid.UUID) -> Child:
        """Get child by ID."""
        child = await self.repo.get_child_by_id(child_id)
        if not child:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Child record not found"
            )
        return child

    async def update_child(
        self, child_id: uuid.UUID, update_data: ChildUpdateSchema
    ) -> Child:
        """Update child record."""
        child = await self.repo.get_child_by_id(child_id)
        print(child)
        if not child:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Child record not found"
            )

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(child, field, value)

        return await self.repo.update_child(child)

    async def list_mother_children(self, mother_id: uuid.UUID) -> List[Child]:
        """List all children for a mother."""
        mother = await self.repo.get_patient_by_id(mother_id)
        if not mother:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Mother not found"
            )
        return await self.repo.get_mother_children(mother_id)

    # ============= Prescription Services =============
    async def create_prescription(
        self, prescription_data: PrescriptionCreateSchema
    ) -> Prescription:
        """Create a new prescription."""
        patient = await self.repo.get_patient_by_id(prescription_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
            )

        prescription_dict = prescription_data.model_dump()
        prescription_dict["is_active"] = True
        prescription = Prescription(**prescription_dict)
        return await self.repo.create_prescription(prescription)

    async def get_prescription(self, prescription_id: uuid.UUID) -> Prescription:
        """Get prescription by ID."""
        prescription = await self.repo.get_prescription_by_id(prescription_id)
        if not prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found",
            )
        return prescription

    async def update_prescription(
        self, prescription_id: uuid.UUID, update_data: PrescriptionUpdateSchema
    ) -> Prescription:
        """Update prescription."""
        prescription = await self.repo.get_prescription_by_id(prescription_id)
        if not prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found",
            )

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(prescription, field, value)

        return await self.repo.update_prescription(prescription)

    async def list_patient_prescriptions(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[Prescription]:
        """List prescriptions for a patient."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
            )
        return await self.repo.get_patient_prescriptions(patient_id, active_only)

    # ============= Medication Schedule Services =============
    async def create_medication_schedule(
        self, schedule_data: MedicationScheduleCreateSchema
    ) -> MedicationSchedule:
        """Create a new medication schedule."""
        patient = await self.repo.get_patient_by_id(schedule_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
            )

        schedule_dict = schedule_data.model_dump()
        schedule_dict["is_completed"] = False
        schedule_dict["lab_review_scheduled"] = False
        schedule_dict["lab_review_completed"] = False
        schedule = MedicationSchedule(**schedule_dict)
        return await self.repo.create_medication_schedule(schedule)

    async def get_medication_schedule(
        self, schedule_id: uuid.UUID
    ) -> MedicationSchedule:
        """Get medication schedule by ID."""
        schedule = await self.repo.get_medication_schedule_by_id(schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medication schedule not found",
            )
        return schedule

    async def update_medication_schedule(
        self, schedule_id: uuid.UUID, update_data: MedicationScheduleUpdateSchema
    ) -> MedicationSchedule:
        """Update medication schedule."""
        schedule = await self.repo.get_medication_schedule_by_id(schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medication schedule not found",
            )

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(schedule, field, value)

        return await self.repo.update_medication_schedule(schedule)

    async def list_patient_medication_schedules(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[MedicationSchedule]:
        """List medication schedules for a patient."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
            )
        return await self.repo.get_patient_medication_schedules(patient_id, active_only)

    # ============= Reminder Services =============
    async def create_reminder(
        self, reminder_data: PatientReminderCreateSchema
    ) -> PatientReminder:
        """Create a new reminder."""
        patient = await self.repo.get_patient_by_id(reminder_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
            )

        if reminder_data.child_id:
            child = await self.repo.get_child_by_id(reminder_data.child_id)
            if not child:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Child not found"
                )

        reminder_dict = reminder_data.model_dump()
        reminder_dict["status"] = "pending"
        reminder = PatientReminder(**reminder_dict)
        return await self.repo.create_reminder(reminder)

    async def get_reminder(self, reminder_id: uuid.UUID) -> PatientReminder:
        """Get reminder by ID."""
        reminder = await self.repo.get_reminder_by_id(reminder_id)
        if not reminder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found"
            )
        return reminder

    async def update_reminder(
        self, reminder_id: uuid.UUID, update_data: PatientReminderUpdateSchema
    ) -> PatientReminder:
        """Update reminder."""
        reminder = await self.repo.get_reminder_by_id(reminder_id)
        if not reminder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found"
            )

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(reminder, field, value)

        return await self.repo.update_reminder(reminder)

    async def list_patient_reminders(
        self, patient_id: uuid.UUID, pending_only: bool = False
    ) -> List[PatientReminder]:
        """List reminders for a patient."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found"
            )
        return await self.repo.get_patient_reminders(patient_id, pending_only)
