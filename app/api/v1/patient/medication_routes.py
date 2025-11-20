import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    PrescriptionCreateSchema,
    PrescriptionUpdateSchema,
    PrescriptionResponseSchema,
)
from app.services.patient_service import PatientService
from app.core.utils import logger


router = APIRouter(prefix="/patient-medication", tags=["patient medication"])

@router.post(
    "/{patient_id}/prescriptions",
    response_model=PrescriptionResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_prescription(
    patient_id: uuid.UUID,
    prescription_data: PrescriptionCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Create prescription for patient (Staff only)."""
    service = PatientService(db)
    try:

        prescription_data.patient_id = patient_id
        prescription_data.prescribed_by_id = current_user.id

        prescription = await service.create_prescription(prescription_data)

        logger.log_info(
            {
                "event": "prescription_created",
                "prescription_id": str(prescription.id),
                "patient_id": str(patient_id),
                "prescribed_by": str(current_user.id),
            }
        )

        return PrescriptionResponseSchema.model_validate(
            prescription, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "create_prescription_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating prescription",
        )


@router.get(
    "/{patient_id}/prescriptions",
    response_model=list[PrescriptionResponseSchema],
)
async def list_patient_prescriptions(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    active_only: bool = False,
):
    """List prescriptions for patient (Staff only)."""
    service = PatientService(db)
    try:
        prescriptions = await service.list_patient_prescriptions(
            patient_id, active_only
        )
        return [
            PrescriptionResponseSchema.model_validate(p, from_attributes=True)
            for p in prescriptions
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_prescriptions_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving prescriptions",
        )


@router.patch(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponseSchema,
)
async def update_prescription(
    prescription_id: uuid.UUID,
    update_data: PrescriptionUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Update prescription (Staff only)."""
    service = PatientService(db)
    try:
        prescription = await service.update_prescription(prescription_id, update_data)

        logger.log_info(
            {
                "event": "prescription_updated",
                "prescription_id": str(prescription_id),
                "updated_by": str(current_user.id),
            }
        )

        return PrescriptionResponseSchema.model_validate(
            prescription, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "update_prescription_error",
                "prescription_id": str(prescription_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating prescription",
        )