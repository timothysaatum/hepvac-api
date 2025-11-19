import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    MedicationScheduleCreateSchema,
    MedicationScheduleUpdateSchema,
    MedicationScheduleResponseSchema,
)
from app.services.patient_service import PatientService
from app.core.utils import logger


router = APIRouter(prefix="/patient-medication-schedules", tags=["patient schedules"])

@router.post(
    "/{patient_id}",
    response_model=MedicationScheduleResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_medication_schedule(
    patient_id: uuid.UUID,
    schedule_data: MedicationScheduleCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Create medication schedule for patient (Staff only)."""
    service = PatientService(db)
    try:
        schedule_data.patient_id = patient_id
        schedule = await service.create_medication_schedule(schedule_data)

        logger.log_info(
            {
                "event": "medication_schedule_created",
                "schedule_id": str(schedule.id),
                "patient_id": str(patient_id),
                "created_by": str(current_user.id),
            }
        )

        return MedicationScheduleResponseSchema.model_validate(
            schedule, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "create_medication_schedule_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating medication schedule",
        )


@router.get(
    "/{patient_id}",
    response_model=list[MedicationScheduleResponseSchema],
)
async def list_patient_medication_schedules(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    active_only: bool = False,
):
    """List medication schedules for patient (Staff only)."""
    service = PatientService(db)
    try:
        schedules = await service.list_patient_medication_schedules(
            patient_id, active_only
        )
        return [
            MedicationScheduleResponseSchema.model_validate(s, from_attributes=True)
            for s in schedules
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_medication_schedules_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving medication schedules",
        )


@router.patch(
    "/{schedule_id}",
    response_model=MedicationScheduleResponseSchema,
)
async def update_medication_schedule(
    schedule_id: uuid.UUID,
    update_data: MedicationScheduleUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Update medication schedule (Staff only)."""
    service = PatientService(db)
    try:
        schedule = await service.update_medication_schedule(schedule_id, update_data)

        logger.log_info(
            {
                "event": "medication_schedule_updated",
                "schedule_id": str(schedule_id),
                "updated_by": str(current_user.id),
            }
        )

        return MedicationScheduleResponseSchema.model_validate(
            schedule, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "update_medication_schedule_error",
                "schedule_id": str(schedule_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating medication schedule",
        )
