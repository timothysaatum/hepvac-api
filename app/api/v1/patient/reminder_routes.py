import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    PatientReminderCreateSchema,
    PatientReminderUpdateSchema,
    PatientReminderResponseSchema,
)
from app.services.patient_service import PatientService
from app.core.utils import logger


router = APIRouter(prefix="/patient-reminders", tags=["patient reminders"])

@router.post(
    "/{patient_id}",
    response_model=PatientReminderResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_reminder(
    patient_id: uuid.UUID,
    reminder_data: PatientReminderCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Create reminder for patient (Staff only)."""
    service = PatientService(db)
    try:
        reminder_data.patient_id = patient_id
        reminder = await service.create_reminder(reminder_data)

        logger.log_info(
            {
                "event": "reminder_created",
                "reminder_id": str(reminder.id),
                "patient_id": str(patient_id),
                "reminder_type": reminder.reminder_type,
                "created_by": str(current_user.id),
            }
        )

        return PatientReminderResponseSchema.model_validate(
            reminder, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "create_reminder_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating reminder",
        )


@router.get(
    "/{patient_id}",
    response_model=list[PatientReminderResponseSchema],
)
async def list_patient_reminders(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    pending_only: bool = False,
):
    """List reminders for patient (Staff only)."""
    service = PatientService(db)
    try:
        reminders = await service.list_patient_reminders(patient_id, pending_only)
        return [
            PatientReminderResponseSchema.model_validate(r, from_attributes=True)
            for r in reminders
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_reminders_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving reminders",
        )


@router.patch(
    "/{reminder_id}",
    response_model=PatientReminderResponseSchema,
)
async def update_reminder(
    reminder_id: uuid.UUID,
    update_data: PatientReminderUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Update reminder (Staff only)."""
    service = PatientService(db)
    try:
        reminder = await service.update_reminder(reminder_id, update_data)

        logger.log_info(
            {
                "event": "reminder_updated",
                "reminder_id": str(reminder_id),
                "updated_by": str(current_user.id),
            }
        )

        return PatientReminderResponseSchema.model_validate(
            reminder, from_attributes=True
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "update_reminder_error",
                "reminder_id": str(reminder_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating reminder",
        )
