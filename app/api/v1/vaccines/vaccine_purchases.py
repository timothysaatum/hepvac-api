import traceback
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.vaccine_schemas import (
    PatientVaccinePurchaseCreateSchema,
    PatientVaccinePurchaseProgressSchema,
    PatientVaccinePurchaseResponseSchema,
    PatientVaccinePurchaseUpdateSchema,
)
from app.services.vaccine_purchase_service import VaccinePurchaseService
from app.core.utils import logger


router = APIRouter(prefix="/purchase-vaccine", tags=["vaccine purchases"])


# ============= Vaccine Purchase Routes =============
@router.post(
    "/{patient_id}",
    response_model=PatientVaccinePurchaseResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_vaccine_purchase(
    patient_id: uuid.UUID,
    purchase_data: PatientVaccinePurchaseCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Create a new vaccine purchase for a patient.

    This creates a vaccine package purchase record where the patient can pay in installments.

    Args:
        patient_id: Patient UUID
        purchase_data: Vaccine purchase creation data
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        PatientVaccinePurchaseResponseSchema: Created vaccine purchase information

    Raises:
        404: Patient or vaccine not found
        400: Validation error or patient already has active purchase for this vaccine
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        # Set patient_id and created_by_id from path and authenticated user
        purchase_data.patient_id = patient_id
        purchase_data.created_by_id = current_user.id

        purchase = await service.create_vaccine_purchase(purchase_data)

        logger.log_info(
            {
                "event": "vaccine_purchase_created",
                "purchase_id": str(purchase.id),
                "patient_id": str(patient_id),
                "vaccine_id": str(purchase.vaccine_id),
                "vaccine_name": purchase.vaccine_name,
                "total_price": float(purchase.total_package_price),
                "total_doses": purchase.total_doses,
                "created_by": str(current_user.id),
            }
        )

        return PatientVaccinePurchaseResponseSchema.model_validate(
            purchase, from_attributes=True
        )

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning(
            {
                "event": "vaccine_purchase_creation_failed",
                "reason": "validation_error",
                "error": str(e),
                "patient_id": str(patient_id),
                "created_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.log_error(
            {
                "event": "vaccine_purchase_creation_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "patient_id": str(patient_id),
                "created_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating vaccine purchase",
        )


@router.get(
    "/{purchase_id}",
    response_model=PatientVaccinePurchaseResponseSchema,
)
async def get_vaccine_purchase(
    purchase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get vaccine purchase by ID.

    Args:
        purchase_id: Vaccine purchase UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        PatientVaccinePurchaseResponseSchema: Vaccine purchase information

    Raises:
        404: Vaccine purchase not found
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        purchase = await service.get_vaccine_purchase(purchase_id)

        return PatientVaccinePurchaseResponseSchema.model_validate(
            purchase, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_vaccine_purchase_error",
                "purchase_id": str(purchase_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving vaccine purchase",
        )


@router.get(
    "/{purchase_id}/progress",
    response_model=PatientVaccinePurchaseProgressSchema,
)
async def get_vaccine_purchase_progress(
    purchase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get detailed progress information for a vaccine purchase.

    This includes payment progress, doses paid for, doses administered, and eligibility status.

    Args:
        purchase_id: Vaccine purchase UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        PatientVaccinePurchaseProgressSchema: Progress information

    Raises:
        404: Vaccine purchase not found
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        progress = await service.get_purchase_progress(purchase_id)

        logger.log_info(
            {
                "event": "vaccine_purchase_progress_checked",
                "purchase_id": str(purchase_id),
                "doses_paid_for": progress["doses_paid_for"],
                "doses_administered": progress["doses_administered"],
                "eligible_doses": progress["eligible_doses"],
                "user_id": str(current_user.id),
            }
        )

        return PatientVaccinePurchaseProgressSchema.model_validate(progress)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_purchase_progress_error",
                "purchase_id": str(purchase_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving purchase progress",
        )


@router.get(
    "/{patient_id}/vaccines",
    response_model=List[PatientVaccinePurchaseResponseSchema],
)
async def list_patient_vaccine_purchases(
    patient_id: uuid.UUID,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    List all vaccine purchases for a patient.

    Args:
        patient_id: Patient UUID
        active_only: Filter to show only active purchases
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        List[PatientVaccinePurchaseResponseSchema]: List of vaccine purchases

    Raises:
        404: Patient not found
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        purchases = await service.list_patient_purchases(patient_id, active_only)

        logger.log_info(
            {
                "event": "patient_purchases_listed",
                "patient_id": str(patient_id),
                "purchase_count": len(purchases),
                "active_only": active_only,
                "user_id": str(current_user.id),
            }
        )

        return [
            PatientVaccinePurchaseResponseSchema.model_validate(p, from_attributes=True)
            for p in purchases
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_patient_purchases_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving patient purchases",
        )


@router.patch(
    "/{purchase_id}",
    response_model=PatientVaccinePurchaseResponseSchema,
)
async def update_vaccine_purchase(
    purchase_id: uuid.UUID,
    update_data: PatientVaccinePurchaseUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Update vaccine purchase.

    Only notes and is_active status can be updated.
    Payment amounts and dose counts are managed through payments and vaccinations.

    Args:
        purchase_id: Vaccine purchase UUID
        update_data: Update data
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        PatientVaccinePurchaseResponseSchema: Updated vaccine purchase

    Raises:
        404: Vaccine purchase not found
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        purchase = await service.update_vaccine_purchase(purchase_id, update_data)

        logger.log_info(
            {
                "event": "vaccine_purchase_updated",
                "purchase_id": str(purchase_id),
                "updated_by": str(current_user.id),
            }
        )

        return PatientVaccinePurchaseResponseSchema.model_validate(
            purchase, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "update_vaccine_purchase_error",
                "purchase_id": str(purchase_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating vaccine purchase",
        )
