from datetime import datetime, timezone
from typing import Optional, List
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models.patient_model import (
    Patient,
    PregnantPatient,
    RegularPatient,
    Vaccination,
    Child,
    PatientWallet,
    Payment,
    Prescription,
    MedicationSchedule,
    PatientReminder,
)
from app.schemas.patient_schemas import PaymentStatus


class PatientRepository:
    """Repository layer for patient data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============= Patient Base Operations =============
    async def get_patient_by_id(self, patient_id: uuid.UUID) -> Optional[Patient]:
        """Get patient by ID."""
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id, Patient.is_deleted == False)
        )
        return result.scalars().first()

    async def get_patients(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Patient]:
        """Get filtered list of patients."""
        query = select(Patient).where(Patient.is_deleted == False)

        if facility_id:
            query = query.where(Patient.facility_id == facility_id)
        if patient_type:
            query = query.where(Patient.patient_type == patient_type)
        if status:
            query = query.where(Patient.status == status)

        query = query.order_by(Patient.created_at.desc())

        result = await self.db.execute(query)
        return result.scalars().all()

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

    async def delete_patient(self, patient: Patient) -> None:
        """Soft delete a patient."""
        patient.is_deleted = True
        patient.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(patient)

    # ============= Pregnant Patient Operations =============
    async def create_pregnant_patient(
        self, patient: PregnantPatient
    ) -> PregnantPatient:
        """Create a new pregnant patient."""
        self.db.add(patient)
        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    async def get_pregnant_patient_by_id(
        self, patient_id: uuid.UUID
    ) -> Optional[PregnantPatient]:
        """Get pregnant patient by ID with relationships."""
        result = await self.db.execute(
            select(PregnantPatient)
            .options(selectinload(PregnantPatient.children))
            .options(selectinload(PregnantPatient.vaccinations))
            .options(selectinload(PregnantPatient.wallet))
            .where(
                PregnantPatient.id == patient_id,
                PregnantPatient.is_deleted == False,
            )
        )
        return result.scalars().first()

    async def update_pregnant_patient(
        self, updated_by_id:uuid.UUID, patient: PregnantPatient
    ) -> PregnantPatient:
        """Update pregnant patient."""
        patient.updated_by_id = updated_by_id
        self.db.add(patient)
        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    # ============= Regular Patient Operations =============
    async def create_regular_patient(self, patient: RegularPatient) -> RegularPatient:
        """Create a new regular patient."""
        self.db.add(patient)
        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    async def get_regular_patient_by_id(
        self, patient_id: uuid.UUID
    ) -> Optional[RegularPatient]:
        """Get regular patient by ID with relationships."""
        result = await self.db.execute(
            select(RegularPatient)
            .options(selectinload(RegularPatient.prescriptions))
            .options(selectinload(RegularPatient.medication_schedules))
            .options(selectinload(RegularPatient.wallet))
            .where(
                RegularPatient.id == patient_id,
                RegularPatient.is_deleted == False,
            )
        )
        return result.scalars().first()

    async def update_regular_patient(self,updated_by_id: uuid.UUID, patient: RegularPatient) -> RegularPatient:
        """Update regular patient."""
        patient.updated_by_id = updated_by_id
        self.db.add(patient)
        await self.db.commit()
        await self.db.refresh(patient)
        return patient

    async def list_patients_paginated(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        patient_status: Optional[str] = None,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[List[Patient], int]:
        """
        Get paginated list of patients with filters and total count.

        Args:
            facility_id: Filter by facility
            patient_type: Filter by patient type (pregnant/regular)
            patient_status: Filter by patient status
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            Tuple of (list of patients, total count)
        """
        from sqlalchemy.orm import with_polymorphic
        from sqlalchemy import func, select

        # Use with_polymorphic to load all subclass columns
        poly_patient = with_polymorphic(Patient, [PregnantPatient, RegularPatient])

        # Build base query with all relationships eagerly loaded
        query = (
            select(poly_patient)
            .options(
                selectinload(poly_patient.facility),
                selectinload(poly_patient.created_by),
                selectinload(poly_patient.updated_by),
                selectinload(poly_patient.vaccinations),
                selectinload(poly_patient.wallet),
                selectinload(poly_patient.prescriptions),
                selectinload(poly_patient.medication_schedules),
                selectinload(poly_patient.reminders),
            )
            .where(poly_patient.is_deleted == False)
        )

        # Apply filters
        if facility_id:
            query = query.where(poly_patient.facility_id == facility_id)

        if patient_type:
            query = query.where(poly_patient.patient_type == patient_type)

        if patient_status:
            query = query.where(poly_patient.status == patient_status)

        # Order by creation date
        query = query.order_by(poly_patient.created_at.desc())

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total_count = total_result.scalar() or 0

        # Get paginated results
        paginated_query = query.offset(skip).limit(limit)
        result = await self.db.execute(paginated_query)
        patients = result.scalars().all()

        return patients, total_count

    # ============= Vaccination Operations =============
    async def create_vaccination(self, vaccination: Vaccination) -> Vaccination:
        """Create a new vaccination record."""
        self.db.add(vaccination)
        await self.db.commit()
        await self.db.refresh(vaccination)
        return vaccination

    async def get_vaccination_by_id(
        self, vaccination_id: uuid.UUID
    ) -> Optional[Vaccination]:
        """Get vaccination by ID."""
        result = await self.db.execute(
            select(Vaccination).where(Vaccination.id == vaccination_id)
        )
        return result.scalars().first()

    async def get_patient_vaccinations(
        self, patient_id: uuid.UUID
    ) -> List[Vaccination]:
        """Get all vaccinations for a patient."""
        result = await self.db.execute(
            select(Vaccination)
            .where(Vaccination.patient_id == patient_id)
            .order_by(Vaccination.dose_number)
        )
        return result.scalars().all()

    async def update_vaccination(self, vaccination: Vaccination) -> Vaccination:
        """Update vaccination record."""
        self.db.add(vaccination)
        await self.db.commit()
        await self.db.refresh(vaccination)
        return vaccination

    async def delete_vaccination(self, vaccination: Vaccination) -> None:
        """Delete vaccination record."""
        await self.db.delete(vaccination)
        await self.db.commit()

    # ============= Child Operations =============
    async def create_child(self, child: Child) -> Child:
        """Create a new child record."""
        self.db.add(child)
        await self.db.commit()
        await self.db.refresh(child)
        return child

    async def get_child_by_id(self, child_id: uuid.UUID) -> Optional[Child]:
        """Get child by ID."""
        print(f"=================={child_id}")
        result = await self.db.execute(select(Child).where(Child.id == child_id))
        return result.scalars().first()

    async def get_mother_children(self, mother_id: uuid.UUID) -> List[Child]:
        """Get all children for a mother."""
        result = await self.db.execute(
            select(Child)
            .where(Child.mother_id == mother_id)
            .order_by(Child.date_of_birth.desc())
        )
        return result.scalars().all()

    async def update_child(self, child: Child) -> Child:
        """Update child record."""
        self.db.add(child)
        await self.db.commit()
        await self.db.refresh(child)
        return child

    async def delete_child(self, child: Child) -> None:
        """Delete child record."""
        await self.db.delete(child)
        await self.db.commit()

    # ============= Wallet Operations =============
    async def create_wallet(self, wallet: PatientWallet) -> PatientWallet:
        """Create a new patient wallet."""
        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def get_wallet_by_patient_id(
        self, patient_id: uuid.UUID
    ) -> Optional[PatientWallet]:
        """Get wallet by patient ID."""
        result = await self.db.execute(
            select(PatientWallet).where(PatientWallet.patient_id == patient_id)
        )
        return result.scalars().first()

    async def get_wallet_by_id(self, wallet_id: uuid.UUID) -> Optional[PatientWallet]:
        """Get wallet by ID."""
        result = await self.db.execute(
            select(PatientWallet).where(PatientWallet.id == wallet_id)
        )
        return result.scalars().first()

    async def update_wallet(self, wallet: PatientWallet) -> PatientWallet:
        """Update wallet."""
        self.db.add(wallet)
        if wallet.amount_paid == wallet.total_amount:
            wallet.payment_status = PaymentStatus.COMPLETED
        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    # ============= Payment Operations =============
    async def create_payment(self, payment: Payment) -> Payment:
        """Create a new payment."""
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def get_payment_by_id(self, payment_id: uuid.UUID) -> Optional[Payment]:
        """Get payment by ID."""
        result = await self.db.execute(select(Payment).where(Payment.id == payment_id))
        return result.scalars().first()

    async def get_wallet_payments(self, wallet_id: uuid.UUID) -> List[Payment]:
        """Get all payments for a wallet."""
        result = await self.db.execute(
            select(Payment)
            .where(Payment.wallet_id == wallet_id)
            .order_by(Payment.payment_date.desc())
        )
        return result.scalars().all()

    # ============= Prescription Operations =============
    async def create_prescription(self, prescription: Prescription) -> Prescription:
        """Create a new prescription."""
        self.db.add(prescription)
        await self.db.commit()
        await self.db.refresh(prescription)
        return prescription

    async def get_prescription_by_id(
        self, prescription_id: uuid.UUID
    ) -> Optional[Prescription]:
        """Get prescription by ID."""
        result = await self.db.execute(
            select(Prescription).where(Prescription.id == prescription_id)
        )
        return result.scalars().first()

    async def get_patient_prescriptions(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[Prescription]:
        """Get all prescriptions for a patient."""
        query = select(Prescription).where(Prescription.patient_id == patient_id)

        if active_only:
            query = query.where(Prescription.is_active == True)

        query = query.order_by(Prescription.prescription_date.desc())

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_prescription(self, prescription: Prescription) -> Prescription:
        """Update prescription."""
        self.db.add(prescription)
        await self.db.commit()
        await self.db.refresh(prescription)
        return prescription

    # ============= Medication Schedule Operations =============
    async def create_medication_schedule(
        self, schedule: MedicationSchedule
    ) -> MedicationSchedule:
        """Create a new medication schedule."""
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def get_medication_schedule_by_id(
        self, schedule_id: uuid.UUID
    ) -> Optional[MedicationSchedule]:
        """Get medication schedule by ID."""
        result = await self.db.execute(
            select(MedicationSchedule).where(MedicationSchedule.id == schedule_id)
        )
        return result.scalars().first()

    async def get_patient_medication_schedules(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[MedicationSchedule]:
        """Get all medication schedules for a patient."""
        query = select(MedicationSchedule).where(
            MedicationSchedule.patient_id == patient_id
        )

        if active_only:
            query = query.where(MedicationSchedule.is_completed == False)

        query = query.order_by(MedicationSchedule.scheduled_date.desc())

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_medication_schedule(
        self, schedule: MedicationSchedule
    ) -> MedicationSchedule:
        """Update medication schedule."""
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    # ============= Reminder Operations =============
    async def create_reminder(self, reminder: PatientReminder) -> PatientReminder:
        """Create a new reminder."""
        self.db.add(reminder)
        await self.db.commit()
        await self.db.refresh(reminder)
        return reminder

    async def get_reminder_by_id(
        self, reminder_id: uuid.UUID
    ) -> Optional[PatientReminder]:
        """Get reminder by ID."""
        result = await self.db.execute(
            select(PatientReminder).where(PatientReminder.id == reminder_id)
        )
        return result.scalars().first()

    async def get_patient_reminders(
        self, patient_id: uuid.UUID, pending_only: bool = False
    ) -> List[PatientReminder]:
        """Get all reminders for a patient."""
        query = select(PatientReminder).where(PatientReminder.patient_id == patient_id)

        if pending_only:
            query = query.where(PatientReminder.status == "pending")

        query = query.order_by(PatientReminder.scheduled_date.desc())

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_reminder(self, reminder: PatientReminder) -> PatientReminder:
        """Update reminder."""
        self.db.add(reminder)
        await self.db.commit()
        await self.db.refresh(reminder)
        return reminder

    async def delete_reminder(self, reminder: PatientReminder) -> None:
        """Delete reminder."""
        await self.db.delete(reminder)
        await self.db.commit()
