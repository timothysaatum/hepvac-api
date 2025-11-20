import traceback
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.vaccine_schemas import VaccinationCreateSchema, VaccinationResponseSchema
from app.services.vaccine_purchase_service import VaccinePurchaseService
from app.core.utils import logger


router = APIRouter(prefix="/administer", tags=["administer vaccine"])


@router.post(
    "/{purchase_id}",
    response_model=VaccinationResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def administer_vaccination(
    purchase_id: uuid.UUID,
    vaccination_data: VaccinationCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Administer a vaccination dose from a vaccine purchase.

    This checks if the patient is eligible based on payment status before administering.

    Args:
        purchase_id: Vaccine purchase UUID
        vaccination_data: Vaccination creation data
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        VaccinationResponseSchema: Created vaccination record

    Raises:
        404: Vaccine purchase not found
        402: Payment required - patient hasn't paid for next dose
        400: All doses already administered or other validation error
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        # Set vaccine_purchase_id and administered_by_id
        vaccination_data.vaccine_purchase_id = purchase_id
        vaccination_data.administered_by_id = current_user.id

        vaccination = await service.administer_vaccination(vaccination_data)

        logger.log_info(
            {
                "event": "vaccination_administered",
                "vaccination_id": str(vaccination.id),
                "purchase_id": str(purchase_id),
                "patient_id": str(vaccination.patient_id),
                "vaccine_name": vaccination.vaccine_name,
                "dose_number": vaccination.dose_number.value,
                "administered_by": str(current_user.id),
            }
        )

        return VaccinationResponseSchema.model_validate(
            vaccination, from_attributes=True
        )

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning(
            {
                "event": "vaccination_administration_failed",
                "reason": "validation_error",
                "error": str(e),
                "purchase_id": str(purchase_id),
                "administered_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.log_error(
            {
                "event": "vaccination_administration_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "purchase_id": str(purchase_id),
                "administered_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while administering vaccination",
        )


@router.get(
    "/{purchase_id}",
    response_model=List[VaccinationResponseSchema],
)
async def list_purchase_vaccinations(
    purchase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    List all vaccinations for a vaccine purchase.

    Args:
        purchase_id: Vaccine purchase UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        List[VaccinationResponseSchema]: List of vaccinations ordered by date

    Raises:
        404: Vaccine purchase not found
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        vaccinations = await service.list_purchase_vaccinations(purchase_id)

        logger.log_info(
            {
                "event": "purchase_vaccinations_listed",
                "purchase_id": str(purchase_id),
                "vaccination_count": len(vaccinations),
                "user_id": str(current_user.id),
            }
        )

        return [
            VaccinationResponseSchema.model_validate(v, from_attributes=True)
            for v in vaccinations
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_purchase_vaccinations_error",
                "purchase_id": str(purchase_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving vaccinations",
        )


@router.get(
    "/{purchase_id}/eligibility",
    response_model=dict,
)
async def check_vaccination_eligibility(
    purchase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Check if patient is eligible for next vaccination dose.

    Returns eligibility status and detailed message about payment/dose status.

    Args:
        purchase_id: Vaccine purchase UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        dict: {
            "eligible": bool,
            "message": str,
            "next_dose_number": int | None,
            "doses_administered": int,
            "doses_paid_for": int
        }

    Raises:
        404: Vaccine purchase not found
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        eligibility = await service.check_eligibility(purchase_id)

        logger.log_info(
            {
                "event": "eligibility_checked",
                "purchase_id": str(purchase_id),
                "eligible": eligibility["eligible"],
                "user_id": str(current_user.id),
            }
        )

        return eligibility

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "check_eligibility_error",
                "purchase_id": str(purchase_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while checking eligibility",
        )