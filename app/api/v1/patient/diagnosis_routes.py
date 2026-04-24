import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    DiagnosisCreateSchema,
    DiagnosisUpdateSchema,
    DiagnosisResponseSchema,
)
from app.services.patient_service import PatientService
from app.core.utils import logger


router = APIRouter(prefix="/patient-diagnosis", tags=["patient diagnosis"])


@router.post(
    "/{patient_id}",
    response_model=DiagnosisResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_diagnosis(
    patient_id: uuid.UUID,
    diagnosis_data: DiagnosisCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Create a diagnosis record for a patient (Staff only)."""
    service = PatientService(db)
    try:
        # Set patient_id and diagnosed_by_id from URL path and current user
        diagnosis_payload = DiagnosisCreateSchema(
            patient_id=patient_id,
            diagnosed_by_id=current_user.id,
            history=diagnosis_data.history,
            preliminary_diagnosis=diagnosis_data.preliminary_diagnosis,
        )

        diagnosis = await service.create_diagnosis(diagnosis_payload)

        logger.log_info({
            "event": "diagnosis_created",
            "diagnosis_id": str(diagnosis.id),
            "patient_id": str(patient_id),
            "diagnosed_by": str(current_user.id),
        })

        return DiagnosisResponseSchema.from_diagnosis(diagnosis)

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "create_diagnosis_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the diagnosis",
        )


@router.get(
    "/{patient_id}",
    response_model=list[DiagnosisResponseSchema],
)
async def list_patient_diagnoses(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """List all diagnoses for a patient (Staff only)."""
    service = PatientService(db)
    try:
        diagnoses = await service.list_patient_diagnoses(patient_id)
        return [DiagnosisResponseSchema.from_diagnosis(d) for d in diagnoses]
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "list_diagnoses_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving diagnoses",
        )


@router.patch(
    "/record/{diagnosis_id}",
    response_model=DiagnosisResponseSchema,
)
async def update_diagnosis(
    diagnosis_id: uuid.UUID,
    update_data: DiagnosisUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Update a diagnosis record (Staff only)."""
    service = PatientService(db)
    try:
        diagnosis = await service.update_diagnosis(diagnosis_id, update_data)
        logger.log_info({
            "event": "diagnosis_updated",
            "diagnosis_id": str(diagnosis_id),
            "updated_by": str(current_user.id),
        })
        return DiagnosisResponseSchema.from_diagnosis(diagnosis)
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "update_diagnosis_error",
            "diagnosis_id": str(diagnosis_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the diagnosis",
        )


@router.delete(
    "/record/{diagnosis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_diagnosis(
    diagnosis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Soft-delete a diagnosis record (Staff only)."""
    service = PatientService(db)
    try:
        await service.delete_diagnosis(diagnosis_id)
        logger.log_info({
            "event": "diagnosis_deleted",
            "diagnosis_id": str(diagnosis_id),
            "deleted_by": str(current_user.id),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "delete_diagnosis_error",
            "diagnosis_id": str(diagnosis_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the diagnosis",
        )