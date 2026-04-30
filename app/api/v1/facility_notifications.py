"""Facility notification work queue endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    FacilityNotificationResponseSchema,
    FacilityNotificationUpdateSchema,
)
from app.services.patient_service import PatientService


router = APIRouter(prefix="/facility-notifications", tags=["facility notifications"])


@router.get("", response_model=list[FacilityNotificationResponseSchema])
async def list_facility_notifications(
    status_filter: Optional[str] = None,
    unresolved_only: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    service = PatientService(db, current_user)
    notifications = await service.list_facility_notifications(
        status_filter=status_filter,
        unresolved_only=unresolved_only,
        limit=limit,
    )
    return [
        FacilityNotificationResponseSchema.from_notification(notification)
        for notification in notifications
    ]


@router.patch("/{notification_id}", response_model=FacilityNotificationResponseSchema)
async def update_facility_notification(
    notification_id: uuid.UUID,
    update_data: FacilityNotificationUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    service = PatientService(db, current_user)
    notification = await service.update_facility_notification(
        notification_id,
        update_data,
    )
    return FacilityNotificationResponseSchema.from_notification(notification)
