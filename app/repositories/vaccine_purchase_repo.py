from typing import Optional, List
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models.vaccine_model import PatientVaccinePurchase, Vaccine
from app.models.patient_model import Patient, Payment, Vaccination


class VaccinePurchaseRepository:
    """Repository layer for vaccine purchase data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============= Patient Operations =============
    async def get_patient_by_id(self, patient_id: uuid.UUID) -> Optional[Patient]:
        """Get patient by ID."""
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id, Patient.is_deleted == False)
        )
        return result.scalars().first()

    # ============= Vaccine Operations =============
    async def get_vaccine_by_id(self, vaccine_id: uuid.UUID) -> Optional[Vaccine]:
        """Get vaccine by ID."""
        result = await self.db.execute(select(Vaccine).where(Vaccine.id == vaccine_id))
        return result.scalars().first()

    async def update_vaccine(self, vaccine: Vaccine) -> Vaccine:
        """Update vaccine (for stock management)."""
        self.db.add(vaccine)
        await self.db.commit()
        await self.db.refresh(vaccine)
        return vaccine

    # ============= Vaccine Purchase Operations =============
    async def create_vaccine_purchase(
        self, purchase: PatientVaccinePurchase
    ) -> PatientVaccinePurchase:
        """Create a new vaccine purchase."""
        self.db.add(purchase)
        await self.db.commit()
        await self.db.refresh(purchase)
        return purchase

    async def get_vaccine_purchase_by_id(
        self, purchase_id: uuid.UUID
    ) -> Optional[PatientVaccinePurchase]:
        """Get vaccine purchase by ID with relationships."""
        result = await self.db.execute(
            select(PatientVaccinePurchase)
            .options(selectinload(PatientVaccinePurchase.patient))
            .options(selectinload(PatientVaccinePurchase.vaccine))
            .options(selectinload(PatientVaccinePurchase.payments))
            .options(selectinload(PatientVaccinePurchase.vaccinations))
            .where(PatientVaccinePurchase.id == purchase_id)
        )
        return result.scalars().first()

    async def get_patient_purchases(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[PatientVaccinePurchase]:
        """Get all vaccine purchases for a patient."""
        query = (
            select(PatientVaccinePurchase)
            .options(selectinload(PatientVaccinePurchase.vaccine))
            .options(selectinload(PatientVaccinePurchase.payments))
            .options(selectinload(PatientVaccinePurchase.vaccinations))
            .where(PatientVaccinePurchase.patient_id == patient_id)
        )

        if active_only:
            query = query.where(PatientVaccinePurchase.is_active == True)

        query = query.order_by(PatientVaccinePurchase.purchase_date.desc())

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_vaccine_purchase(
        self, purchase: PatientVaccinePurchase
    ) -> PatientVaccinePurchase:
        """Update vaccine purchase."""
        self.db.add(purchase)
        await self.db.commit()
        await self.db.refresh(purchase)
        return purchase

    # ============= Payment Operations =============
    async def create_payment(self, payment: Payment) -> Payment:
        """Create a new payment."""
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def get_payment_by_id(self, payment_id: uuid.UUID) -> Optional[Payment]:
        """Get payment by ID."""
        result = await self.db.execute(
            select(Payment)
            .options(selectinload(Payment.vaccine_purchase))
            .where(Payment.id == payment_id)
        )
        return result.scalars().first()

    async def get_purchase_payments(self, purchase_id: uuid.UUID) -> List[Payment]:
        """Get all payments for a vaccine purchase."""
        result = await self.db.execute(
            select(Payment)
            .where(Payment.vaccine_purchase_id == purchase_id)
            .order_by(Payment.payment_date.desc())
        )
        return result.scalars().all()

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
            select(Vaccination)
            .options(selectinload(Vaccination.vaccine_purchase))
            .options(selectinload(Vaccination.patient))
            .where(Vaccination.id == vaccination_id)
        )
        return result.scalars().first()

    async def get_purchase_vaccinations(
        self, purchase_id: uuid.UUID
    ) -> List[Vaccination]:
        """Get all vaccinations for a vaccine purchase."""
        result = await self.db.execute(
            select(Vaccination)
            .where(Vaccination.vaccine_purchase_id == purchase_id)
            .order_by(Vaccination.dose_date.asc())
        )
        return result.scalars().all()

    async def get_patient_vaccinations(
        self, patient_id: uuid.UUID
    ) -> List[Vaccination]:
        """Get all vaccinations for a patient."""
        result = await self.db.execute(
            select(Vaccination)
            .options(selectinload(Vaccination.vaccine_purchase))
            .where(Vaccination.patient_id == patient_id)
            .order_by(Vaccination.dose_date.desc())
        )
        return result.scalars().all()
