from decimal import Decimal
from typing import List
import uuid
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.vaccine_model import PatientVaccinePurchase
from app.models.patient_model import Payment, Vaccination
from app.repositories.vaccine_purchase_repo import VaccinePurchaseRepository
from app.schemas.patient_schemas import DoseType
from app.schemas.vaccine_schemas import (
    PatientVaccinePurchaseCreateSchema, 
    PatientVaccinePurchaseUpdateSchema, 
    PaymentCreateSchema, 
    VaccinationCreateSchema
)


class VaccinePurchaseService:
    """Service layer for vaccine purchase business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = VaccinePurchaseRepository(self.db)

    # ============= Vaccine Purchase Services =============
    async def create_vaccine_purchase(
        self, purchase_data: PatientVaccinePurchaseCreateSchema
    ) -> PatientVaccinePurchase:
        """Create a new vaccine purchase for a patient."""

        # Verify patient exists
        patient = await self.repo.get_patient_by_id(purchase_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found",
            )

        # Verify vaccine exists
        vaccine = await self.repo.get_vaccine_by_id(purchase_data.vaccine_id)
        if not vaccine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine not found",
            )

        # Check vaccine stock
        if vaccine.quantity < purchase_data.total_doses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient vaccine stock. Available: {vaccine.quantity}, Required: {purchase_data.total_doses}",
            )

        # Check if patient already has an active purchase for this vaccine
        existing_purchases = await self.repo.get_patient_purchases(
            purchase_data.patient_id, active_only=True
        )
        for existing in existing_purchases:
            if (
                existing.vaccine_id == purchase_data.vaccine_id
                and not existing.is_completed()
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Patient already has an active purchase for {vaccine.vaccine_name}",
                )
            
        # Create purchase with calculated values
        purchase_dict = purchase_data.model_dump()
        total_package_price = vaccine.price_per_dose * purchase_data.total_doses
        purchase_dict["vaccine_name"] = vaccine.vaccine_name
        purchase_dict["price_per_dose"] = vaccine.price_per_dose
        purchase_dict["total_package_price"] = total_package_price
        purchase_dict["batch_number"] = vaccine.batch_number
        purchase_dict["balance"] = total_package_price
        purchase_dict["amount_paid"] = Decimal("0.00")
        purchase_dict["doses_administered"] = 0
        purchase_dict["payment_status"] = "pending"

        purchase = PatientVaccinePurchase(**purchase_dict)
        created_purchase = await self.repo.create_vaccine_purchase(purchase)

        # Reserve vaccine stock
        vaccine.quantity -= purchase_data.total_doses
        await self.repo.update_vaccine(vaccine)

        return created_purchase

    async def get_vaccine_purchase(
        self, purchase_id: uuid.UUID
    ) -> PatientVaccinePurchase:
        """Get vaccine purchase by ID."""
        purchase = await self.repo.get_vaccine_purchase_by_id(purchase_id)
        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine purchase not found",
            )
        return purchase

    async def update_vaccine_purchase(
        self, purchase_id: uuid.UUID, update_data: PatientVaccinePurchaseUpdateSchema
    ) -> PatientVaccinePurchase:
        """Update vaccine purchase (notes and is_active only)."""
        purchase = await self.repo.get_vaccine_purchase_by_id(purchase_id)
        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine purchase not found",
            )

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(purchase, field, value)

        return await self.repo.update_vaccine_purchase(purchase)

    async def list_patient_purchases(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[PatientVaccinePurchase]:
        """List all vaccine purchases for a patient."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found",
            )
        return await self.repo.get_patient_purchases(patient_id, active_only)

    async def get_purchase_progress(self, purchase_id: uuid.UUID) -> dict:
        """Get detailed progress information for a vaccine purchase."""
        purchase = await self.repo.get_vaccine_purchase_by_id(purchase_id)
        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine purchase not found",
            )
        return purchase.get_payment_progress()

    # ============= Payment Services =============
    async def create_payment(self, payment_data: PaymentCreateSchema) -> Payment:
        """Create a payment and update vaccine purchase balance."""

        # Get vaccine purchase
        purchase = await self.repo.get_vaccine_purchase_by_id(
            payment_data.vaccine_purchase_id
        )
        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine purchase not found",
            )

        # Validate payment amount
        if payment_data.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount must be greater than zero",
            )

        # Check if payment exceeds balance
        if payment_data.amount > purchase.balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment amount (GHS {payment_data.amount}) exceeds balance (GHS {purchase.balance})",
            )

        # Check if purchase is already fully paid
        if purchase.payment_status == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vaccine purchase is already fully paid",
            )

        # Create payment
        payment_dict = payment_data.model_dump()
        payment = Payment(**payment_dict)
        created_payment = await self.repo.create_payment(payment)

        # Update purchase balance
        purchase.record_payment(payment_data.amount)
        await self.repo.update_vaccine_purchase(purchase)

        return created_payment

    async def get_payment(self, payment_id: uuid.UUID) -> Payment:
        """Get payment by ID."""
        payment = await self.repo.get_payment_by_id(payment_id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )
        return payment

    async def list_purchase_payments(self, purchase_id: uuid.UUID) -> List[Payment]:
        """List all payments for a vaccine purchase."""
        purchase = await self.repo.get_vaccine_purchase_by_id(purchase_id)
        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine purchase not found",
            )
        return await self.repo.get_purchase_payments(purchase_id)

    # ============= Vaccination Services =============
    async def administer_vaccination(
        self, vaccination_data: VaccinationCreateSchema
    ) -> Vaccination:
        """Administer a vaccination dose."""

        # Get vaccine purchase
        purchase = await self.repo.get_vaccine_purchase_by_id(
            vaccination_data.vaccine_purchase_id
        )
        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine purchase not found",
            )

        # Set patient_id from purchase
        vaccination_data.patient_id = purchase.patient_id

        # Check eligibility
        can_administer, message = purchase.can_administer_next_dose()
        if not can_administer:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=message,
            )

        # Get next dose number
        next_dose = purchase.get_next_dose_number()
        if next_dose is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All doses have been administered",
            )

        # Map dose number to DoseType
        dose_mapping = {
            1: DoseType.FIRST_DOSE,
            2: DoseType.SECOND_DOSE,
            3: DoseType.THIRD_DOSE,
        }
        vaccination_data.dose_number = dose_mapping.get(next_dose, DoseType.FIRST_DOSE)

        # Set vaccine details from purchase
        vaccination_data.vaccine_name = purchase.vaccine_name
        vaccination_data.vaccine_price = purchase.price_per_dose
        vaccination_data.batch_number = purchase.batch_number
        # Create vaccination
        vaccination_dict = vaccination_data.model_dump()
        vaccination = Vaccination(**vaccination_dict)
        created_vaccination = await self.repo.create_vaccination(vaccination)

        # Update purchase dose count
        purchase.record_dose_administered()
        await self.repo.update_vaccine_purchase(purchase)

        return created_vaccination

    async def list_purchase_vaccinations(
        self, purchase_id: uuid.UUID
    ) -> List[Vaccination]:
        """List all vaccinations for a vaccine purchase."""
        purchase = await self.repo.get_vaccine_purchase_by_id(purchase_id)
        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine purchase not found",
            )
        return await self.repo.get_purchase_vaccinations(purchase_id)

    async def check_eligibility(self, purchase_id: uuid.UUID) -> dict:
        """Check if patient is eligible for next vaccination dose."""
        purchase = await self.repo.get_vaccine_purchase_by_id(purchase_id)
        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine purchase not found",
            )

        can_administer, message = purchase.can_administer_next_dose()
        next_dose = purchase.get_next_dose_number()
        doses_paid_for = purchase.calculate_doses_paid_for()

        return {
            "eligible": can_administer,
            "message": message,
            "next_dose_number": next_dose,
            "doses_administered": purchase.doses_administered,
            "doses_paid_for": doses_paid_for,
            "total_doses": purchase.total_doses,
        }
