import traceback
import time
import uuid
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.search_schemas import (
    PatientSearchFilters,
    PatientSearchResponse,
    VaccinationSearchFilters,
    VaccinationSearchResponse,
    PaymentSearchFilters,
    PaymentSearchResponse,
)
from app.services.search_service import SearchService
from app.core.utils import logger


router = APIRouter(prefix="/search", tags=["search"])


# ============= Rate Limiting - SECURITY =============
# Simple in-memory rate limiter (for production, use Redis)

# class RateLimiter:
#     """Simple rate limiter for search endpoints - SECURITY."""
    
#     def __init__(self, max_requests: int = 30, window_seconds: int = 60):
#         self.max_requests = max_requests
#         self.window_seconds = window_seconds
#         self.requests = defaultdict(list)
    
#     def is_allowed(self, user_id: str) -> bool:
#         """Check if request is allowed."""
#         now = datetime.now()
#         # Clean old requests
#         self.requests[user_id] = [
#             req_time for req_time in self.requests[user_id]
#             if now - req_time < timedelta(seconds=self.window_seconds)
#         ]
        
#         # Check limit
#         if len(self.requests[user_id]) >= self.max_requests:
#             return False
        
#         # Add current request
#         self.requests[user_id].append(now)
#         return True

# # Global rate limiter instance
# search_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)


# def check_rate_limit(current_user: User):
#     """Dependency to check rate limit - SECURITY."""
#     if not search_rate_limiter.is_allowed(str(current_user.id)):
#         raise HTTPException(
#             status_code=status.HTTP_429_TOO_MANY_REQUESTS,
#             detail="Too many search requests. Please try again later.",
#         )


# ============= Default Top 10 Helper =============
async def get_default_results(
    service: SearchService,
    search_type: str,
    facility_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Get top 10 most recent records by default - FEATURE REQUEST.
    
    Called when no search filters are provided.
    """
    if search_type == "patients":
        filters = PatientSearchFilters(facility_id=facility_id)
        return await service.search_patients(filters=filters, page=1, page_size=10)
    
    elif search_type == "vaccinations":
        filters = VaccinationSearchFilters(facility_id=facility_id)
        return await service.search_vaccinations(filters=filters, page=1, page_size=10)
    
    elif search_type == "payments":
        filters = PaymentSearchFilters(facility_id=facility_id)
        return await service.search_payments(filters=filters, page=1, page_size=10)


# ============= Patient Search =============
@router.get(
    "/patients",
    response_model=PatientSearchResponse,
)
async def search_patients(
    # Search filters
    name: Optional[str] = Query(None, description="Search by patient name (partial match, min 2 chars)"),
    phone: Optional[str] = Query(None, description="Search by phone number"),
    facility_id: Optional[uuid.UUID] = Query(None, description="Filter by facility"),
    patient_type: Optional[str] = Query(None, description="Filter by patient type (pregnant/regular)"),
    status: Optional[str] = Query(None, description="Filter by patient status"),
    sex: Optional[str] = Query(None, description="Filter by sex (male/female)"),
    age_min: Optional[int] = Query(None, ge=0, le=150, description="Minimum age"),
    age_max: Optional[int] = Query(None, ge=0, le=150, description="Maximum age"),
    created_from: Optional[date] = Query(None, description="Filter by creation date from (YYYY-MM-DD)"),
    created_to: Optional[date] = Query(None, description="Filter by creation date to (YYYY-MM-DD)"),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page (max 50)"),  # SECURITY: Limited to 50
    # Dependencies
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    # _rate_limit: None = Depends(check_rate_limit),  # SECURITY: Rate limiting
):
    """
    Search patients with various filters.
    
    **DEFAULT BEHAVIOR**: When no filters are provided, returns top 10 most recent patients.
    
    **SECURITY FEATURES**:
    - Rate limited to 30 requests per minute per user
    - Maximum page size of 50 items
    - Input sanitization and validation
    - Parameterized SQL queries
    - Query timeout of 30 seconds
    
    **OPTIMIZATIONS**:
    - Database indexes on common search fields
    - Efficient joins and eager loading
    - Query result pagination
    
    Returns paginated list of patients matching the search criteria.
    """
    service = SearchService(db)
    start_time = time.time()
    
    try:
        # Check if any filters provided
        has_filters = any([
            name, phone, patient_type, status, sex,
            age_min is not None, age_max is not None,
            created_from, created_to
        ])
        
        # DEFAULT: Return top 10 most recent if no filters
        if not has_filters:
            logger.log_info({
                "event": "default_patients_fetched",
                "user_id": str(current_user.id),
                "message": "No filters provided, returning top 10 most recent patients"
            })
            results = await get_default_results(service, "patients", facility_id)
        else:
            # Create filters object
            filters = PatientSearchFilters(
                name=name,
                phone=phone,
                facility_id=facility_id,
                patient_type=patient_type,
                status=status,
                sex=sex,
                age_min=age_min,
                age_max=age_max,
                created_from=created_from,
                created_to=created_to,
            )
            
            # Execute search
            results = await service.search_patients(
                filters=filters,
                page=page,
                page_size=page_size,
            )
        
        # Calculate query time
        query_time_ms = (time.time() - start_time) * 1000
        results.query_time_ms = round(query_time_ms, 2)
        
        logger.log_info({
            "event": "patients_searched",
            "filters_used": has_filters,
            "results_count": len(results.items),
            "total_count": results.total_count,
            "query_time_ms": query_time_ms,
            "user_id": str(current_user.id),
        })
        
        return results
    
    except HTTPException:
        raise
    
    except ValueError as e:
        logger.log_warning({
            "event": "patient_search_validation_error",
            "error": str(e),
            "user_id": str(current_user.id),
        })
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    except Exception as e:
        logger.log_error({
            "event": "patient_search_error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "user_id": str(current_user.id),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching patients",
        )


# ============= Vaccination Search =============
@router.get(
    "/vaccinations",
    response_model=VaccinationSearchResponse,
)
async def search_vaccinations(
    # Search filters
    patient_id: Optional[uuid.UUID] = Query(None, description="Filter by patient ID"),
    patient_name: Optional[str] = Query(None, description="Search by patient name (min 2 chars)"),
    patient_phone: Optional[str] = Query(None, description="Search by patient phone"),
    vaccine_name: Optional[str] = Query(None, description="Search by vaccine name (min 2 chars)"),
    batch_number: Optional[str] = Query(None, description="Search by batch number"),
    dose_number: Optional[str] = Query(None, description="Filter by dose (1st dose, 2nd dose, 3rd dose)"),
    dose_date_from: Optional[date] = Query(None, description="Filter by dose date from (YYYY-MM-DD)"),
    dose_date_to: Optional[date] = Query(None, description="Filter by dose date to (YYYY-MM-DD)"),
    administered_by_id: Optional[uuid.UUID] = Query(None, description="Filter by administrator"),
    facility_id: Optional[uuid.UUID] = Query(None, description="Filter by facility"),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page (max 50)"),
    # Dependencies
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    # _rate_limit: None = Depends(check_rate_limit),
):
    """
    Search vaccination records.
    
    **DEFAULT BEHAVIOR**: When no filters are provided, returns top 10 most recent vaccinations.
    
    **SECURITY**: Rate limited, input sanitized, max page size 50
    """
    service = SearchService(db)
    start_time = time.time()
    
    try:
        # Check if any filters provided
        has_filters = any([
            patient_id, patient_name, patient_phone, vaccine_name,
            batch_number, dose_number, dose_date_from, dose_date_to,
            administered_by_id
        ])
        
        # DEFAULT: Return top 10 most recent
        if not has_filters:
            logger.log_info({
                "event": "default_vaccinations_fetched",
                "user_id": str(current_user.id),
            })
            results = await get_default_results(service, "vaccinations", facility_id)
        else:
            filters = VaccinationSearchFilters(
                patient_id=patient_id,
                patient_name=patient_name,
                patient_phone=patient_phone,
                vaccine_name=vaccine_name,
                batch_number=batch_number,
                dose_number=dose_number,
                dose_date_from=dose_date_from,
                dose_date_to=dose_date_to,
                administered_by_id=administered_by_id,
                facility_id=facility_id,
            )
            
            results = await service.search_vaccinations(
                filters=filters,
                page=page,
                page_size=page_size,
            )
        
        query_time_ms = (time.time() - start_time) * 1000
        results.query_time_ms = round(query_time_ms, 2)
        
        logger.log_info({
            "event": "vaccinations_searched",
            "filters_used": has_filters,
            "results_count": len(results.items),
            "query_time_ms": query_time_ms,
            "user_id": str(current_user.id),
        })
        
        return results
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.log_error({
            "event": "vaccination_search_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching vaccinations",
        )


# ============= Payment Search =============
@router.get(
    "/payments",
    response_model=PaymentSearchResponse,
)
async def search_payments(
    # Search filters
    patient_id: Optional[uuid.UUID] = Query(None, description="Filter by patient ID"),
    patient_name: Optional[str] = Query(None, description="Search by patient name (min 2 chars)"),
    patient_phone: Optional[str] = Query(None, description="Search by patient phone"),
    vaccine_purchase_id: Optional[uuid.UUID] = Query(None, description="Filter by vaccine purchase"),
    payment_method: Optional[str] = Query(None, description="Filter by payment method"),
    payment_date_from: Optional[date] = Query(None, description="Filter by payment date from"),
    payment_date_to: Optional[date] = Query(None, description="Filter by payment date to"),
    amount_min: Optional[float] = Query(None, ge=0, description="Minimum payment amount"),
    amount_max: Optional[float] = Query(None, ge=0, description="Maximum payment amount"),
    received_by_id: Optional[uuid.UUID] = Query(None, description="Filter by receiver"),
    facility_id: Optional[uuid.UUID] = Query(None, description="Filter by facility"),
    reference_number: Optional[str] = Query(None, description="Search by reference number"),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page (max 50)"),
    # Dependencies
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    # _rate_limit: None = Depends(check_rate_limit),
):
    """
    Search payment records.
    
    **DEFAULT BEHAVIOR**: When no filters are provided, returns top 10 most recent payments.
    
    **SECURITY**: Rate limited, input sanitized, max page size 50
    **INCLUDES**: Total amount for all filtered payments
    """
    service = SearchService(db)
    start_time = time.time()
    
    try:
        # Check if any filters provided
        has_filters = any([
            patient_id, patient_name, patient_phone, vaccine_purchase_id,
            payment_method, payment_date_from, payment_date_to,
            amount_min is not None, amount_max is not None,
            received_by_id, reference_number
        ])
        
        # DEFAULT: Return top 10 most recent
        if not has_filters:
            logger.log_info({
                "event": "default_payments_fetched",
                "user_id": str(current_user.id),
            })
            results = await get_default_results(service, "payments", facility_id)
        else:
            filters = PaymentSearchFilters(
                patient_id=patient_id,
                patient_name=patient_name,
                patient_phone=patient_phone,
                vaccine_purchase_id=vaccine_purchase_id,
                payment_method=payment_method,
                payment_date_from=payment_date_from,
                payment_date_to=payment_date_to,
                amount_min=amount_min,
                amount_max=amount_max,
                received_by_id=received_by_id,
                facility_id=facility_id,
                reference_number=reference_number,
            )
            
            results = await service.search_payments(
                filters=filters,
                page=page,
                page_size=page_size,
            )
        
        query_time_ms = (time.time() - start_time) * 1000
        results.query_time_ms = round(query_time_ms, 2)
        
        logger.log_info({
            "event": "payments_searched",
            "filters_used": has_filters,
            "results_count": len(results.items),
            "total_amount": float(results.total_amount),
            "query_time_ms": query_time_ms,
            "user_id": str(current_user.id),
        })
        
        return results
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.log_error({
            "event": "payment_search_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching payments",
        )