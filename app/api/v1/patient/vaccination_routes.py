import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_admin, require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    VaccinationCreateSchema,
    VaccinationUpdateSchema,
    VaccinationResponseSchema,
)
from app.services.patient_service import PatientService
from app.core.utils import logger


router = APIRouter(prefix="/patient-vaccinations", tags=["patient vaccinations"])


@router.post(
    "/{patient_id}",
    response_model=VaccinationResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_vaccination(
    patient_id: uuid.UUID,
    vaccination_data: VaccinationCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """Create vaccination record for patient (Staff only)."""
    service = PatientService(db)
    try:
        # Set patient_id from URL and administered_by_id from authenticated user
        vaccination_data.patient_id = patient_id
        vaccination_data.administered_by_id = current_user.id

        vaccination = await service.create_vaccination(vaccination_data)

        logger.log_info(
            {
                "event": "vaccination_created",
                "vaccination_id": str(vaccination.id),
                "patient_id": str(patient_id),
                "dose_number": vaccination.dose_number,
                "created_by": str(current_user.id),
            }
        )

        return VaccinationResponseSchema.model_validate(
            vaccination, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "create_vaccination_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating vaccination",
        )


@router.get(
    "/{patient_id}",
    response_model=list[VaccinationResponseSchema],
)
async def list_patient_vaccinations(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """List all vaccinations for patient (Staff only)."""
    service = PatientService(db)
    try:
        vaccinations = await service.list_patient_vaccinations(patient_id)
        return [
            VaccinationResponseSchema.model_validate(v, from_attributes=True)
            for v in vaccinations
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_vaccinations_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving vaccinations",
        )


@router.patch(
    "/{vaccination_id}",
    response_model=VaccinationResponseSchema,
)
async def update_vaccination(
    vaccination_id: uuid.UUID,
    update_data: VaccinationUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """Update vaccination record (Staff only)."""
    service = PatientService(db)
    try:
        vaccination = await service.update_vaccination(vaccination_id, update_data)

        logger.log_info(
            {
                "event": "vaccination_updated",
                "vaccination_id": str(vaccination_id),
                "updated_by": str(current_user.id),
            }
        )

        return VaccinationResponseSchema.model_validate(
            vaccination, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "update_vaccination_error",
                "vaccination_id": str(vaccination_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating vaccination",
        )
