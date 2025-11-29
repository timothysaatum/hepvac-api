import math
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.search_repo import SearchRepository
from app.schemas.search_schemas import (
    PatientSearchFilters,
    PatientSearchResult,
    PatientSearchResponse,
    VaccinationSearchFilters,
    VaccinationSearchResult,
    VaccinationSearchResponse,
    PaymentSearchFilters,
    PaymentSearchResult,
    PaymentSearchResponse,
)
from app.models.patient_model import Patient, Vaccination, Payment


class SearchService:
    """Service layer for search operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SearchRepository(self.db)

    # ============= Patient Search =============
    async def search_patients(
        self,
        filters: PatientSearchFilters,
        page: int = 1,
        page_size: int = 10,
    ) -> PatientSearchResponse:
        """
        Search patients with pagination.
        
        Args:
            filters: Patient search filters
            page: Page number (starts at 1)
            page_size: Items per page
            
        Returns:
            PatientSearchResponse with paginated results
        """
        # Validate pagination
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
        
        # Calculate skip
        skip = (page - 1) * page_size
        
        # Search patients
        patients, total_count = await self.repo.search_patients(
            name=filters.name,
            phone=filters.phone,
            facility_id=filters.facility_id,
            patient_type=filters.patient_type,
            status=filters.status.value if filters.status else None,
            sex=filters.sex.value if filters.sex else None,
            age_min=filters.age_min,
            age_max=filters.age_max,
            created_from=filters.created_from,
            created_to=filters.created_to,
            skip=skip,
            limit=page_size,
        )
        
        # Convert to response models
        items = [self._patient_to_search_result(p) for p in patients]
        
        # Calculate pagination info
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
        has_next = page < total_pages
        has_previous = page > 1
        
        return PatientSearchResponse(
            items=items,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
        )
    
    def _patient_to_search_result(self, patient: Patient) -> PatientSearchResult:
        """Convert Patient model to PatientSearchResult."""
        result_dict = {
            "id": patient.id,
            "name": patient.name,
            "phone": patient.phone,
            "age": patient.age,
            "sex": patient.sex,
            "patient_type": patient.patient_type,
            "status": patient.status,
            "facility_id": patient.facility_id,
            "created_at": patient.created_at,
        }
        
        # Add type-specific fields
        if patient.patient_type == "pregnant":
            result_dict["expected_delivery_date"] = patient.expected_delivery_date
            result_dict["actual_delivery_date"] = patient.actual_delivery_date
        elif patient.patient_type == "regular":
            result_dict["diagnosis_date"] = patient.diagnosis_date
            result_dict["treatment_start_date"] = patient.treatment_start_date
            result_dict["viral_load"] = patient.viral_load
        
        return PatientSearchResult(**result_dict)

    # ============= Vaccination Search =============
    async def search_vaccinations(
        self,
        filters: VaccinationSearchFilters,
        page: int = 1,
        page_size: int = 10,
    ) -> VaccinationSearchResponse:
        """
        Search vaccinations with pagination.
        
        Args:
            filters: Vaccination search filters
            page: Page number (starts at 1)
            page_size: Items per page
            
        Returns:
            VaccinationSearchResponse with paginated results
        """
        # Validate pagination
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
        
        # Calculate skip
        skip = (page - 1) * page_size
        
        # Search vaccinations
        vaccinations, total_count = await self.repo.search_vaccinations(
            patient_id=filters.patient_id,
            patient_name=filters.patient_name,
            patient_phone=filters.patient_phone,
            vaccine_name=filters.vaccine_name,
            batch_number=filters.batch_number,
            dose_number=filters.dose_number.value if filters.dose_number else None,
            dose_date_from=filters.dose_date_from,
            dose_date_to=filters.dose_date_to,
            administered_by_id=filters.administered_by_id,
            facility_id=filters.facility_id,
            skip=skip,
            limit=page_size,
        )
        
        # Convert to response models
        items = [self._vaccination_to_search_result(v) for v in vaccinations]
        
        # Calculate pagination info
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
        has_next = page < total_pages
        has_previous = page > 1
        
        return VaccinationSearchResponse(
            items=items,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
        )
    
    def _vaccination_to_search_result(self, vaccination: Vaccination) -> VaccinationSearchResult:
        """Convert Vaccination model to VaccinationSearchResult."""
        return VaccinationSearchResult(
            id=vaccination.id,
            patient_id=vaccination.patient_id,
            patient_name=vaccination.patient.name,
            patient_phone=vaccination.patient.phone,
            vaccine_purchase_id=vaccination.vaccine_purchase_id,
            vaccine_name=vaccination.vaccine_name,
            dose_number=vaccination.dose_number,
            dose_date=vaccination.dose_date,
            batch_number=vaccination.batch_number,
            vaccine_price=vaccination.vaccine_price,
            administered_by_id=vaccination.administered_by_id,
            notes=vaccination.notes,
            created_at=vaccination.created_at,
        )

    # ============= Payment Search =============
    async def search_payments(
        self,
        filters: PaymentSearchFilters,
        page: int = 1,
        page_size: int = 10,
    ) -> PaymentSearchResponse:
        """
        Search payments with pagination.
        
        Args:
            filters: Payment search filters
            page: Page number (starts at 1)
            page_size: Items per page
            
        Returns:
            PaymentSearchResponse with paginated results
        """
        # Validate pagination
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
        
        # Calculate skip
        skip = (page - 1) * page_size
        
        # Search payments
        payments, total_count, total_amount = await self.repo.search_payments(
            patient_id=filters.patient_id,
            patient_name=filters.patient_name,
            patient_phone=filters.patient_phone,
            vaccine_purchase_id=filters.vaccine_purchase_id,
            payment_method=filters.payment_method,
            payment_date_from=filters.payment_date_from,
            payment_date_to=filters.payment_date_to,
            amount_min=float(filters.amount_min) if filters.amount_min else None,
            amount_max=float(filters.amount_max) if filters.amount_max else None,
            received_by_id=filters.received_by_id,
            facility_id=filters.facility_id,
            reference_number=filters.reference_number,
            skip=skip,
            limit=page_size,
        )
        
        # Convert to response models
        items = [self._payment_to_search_result(p) for p in payments]
        
        # Calculate pagination info
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
        has_next = page < total_pages
        has_previous = page > 1
        
        return PaymentSearchResponse(
            items=items,
            total_count=total_count,
            total_amount=total_amount,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
        )
    
    def _payment_to_search_result(self, payment: Payment) -> PaymentSearchResult:
        """Convert Payment model to PaymentSearchResult."""
        return PaymentSearchResult(
            id=payment.id,
            patient_id=payment.vaccine_purchase.patient_id,
            patient_name=payment.vaccine_purchase.patient.name,
            patient_phone=payment.vaccine_purchase.patient.phone,
            vaccine_purchase_id=payment.vaccine_purchase_id,
            vaccine_name=payment.vaccine_purchase.vaccine_name,
            amount=payment.amount,
            payment_date=payment.payment_date,
            payment_method=payment.payment_method,
            reference_number=payment.reference_number,
            received_by_id=payment.received_by_id,
            notes=payment.notes,
            created_at=payment.created_at,
        )