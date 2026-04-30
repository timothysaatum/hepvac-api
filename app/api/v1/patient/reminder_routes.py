import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.core.pagination import PaginationParams, PaginatedResponse, get_pagination_params
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
    service = PatientService(db, current_user)
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
    """List reminders for patient (Staff only). Use /paginated for large lists."""
    service = PatientService(db, current_user)
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


@router.get(
    "/{patient_id}/paginated",
    response_model=PaginatedResponse[PatientReminderResponseSchema],
)
async def list_patient_reminders_paginated(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    pagination: PaginationParams = Depends(get_pagination_params),
    status_filter: Optional[str] = None,
    upcoming_only: bool = False,
):
    """
    List reminders for patient with pagination.
    
    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 10, max: 100)
    - status_filter: Filter by status (PENDING, SENT, FAILED, CANCELLED)
    - upcoming_only: Show only reminders with scheduled_date >= today (default: false)
    
    Smart Ordering: Pending reminders appear first, sorted by scheduled_date.
    """
    service = PatientService(db, current_user)
    try:
        result = await service.list_patient_reminders_paginated(
            patient_id=patient_id,
            pagination=pagination,
            status_filter=status_filter,
            upcoming_only=upcoming_only,
        )
        
        # Convert items to response schema
        return PaginatedResponse(
            items=[
                PatientReminderResponseSchema.model_validate(item, from_attributes=True)
                for item in result.items
            ],
            page_info=result.page_info,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_reminders_paginated_error",
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
    service = PatientService(db, current_user)
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
