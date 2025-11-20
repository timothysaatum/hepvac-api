import traceback
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
)
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    PregnantPatientCreateSchema,
    PregnantPatientUpdateSchema,
    PregnantPatientResponseSchema,
    RegularPatientCreateSchema,
    RegularPatientUpdateSchema,
    RegularPatientResponseSchema,
    ConvertToRegularPatientSchema,
)
from app.services.patient_service import PatientService
from app.core.utils import logger


router = APIRouter(prefix="/patients", tags=["patients"])


# ============= Pregnant Patient Routes =============
@router.post(
    "/pregnant",
    response_model=PregnantPatientResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_pregnant_patient(
    patient_data: PregnantPatientCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Create a new pregnant patient.

    Args:
        patient_data: Pregnant patient creation data
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        PregnantPatientResponseSchema: Created patient information
    """
    service = PatientService(db)
    try:
        # Set facility_id and created_by_id from authenticated user
        patient_data.facility_id = current_user.facility_id
        patient_data.created_by_id = current_user.id
        patient = await service.create_pregnant_patient(patient_data)

        logger.log_info(
            {
                "event": "pregnant_patient_created",
                "patient_id": str(patient.id),
                "created_by": str(current_user.id),
                "facility_id": str(patient.facility_id),
            }
        )

        return PregnantPatientResponseSchema.from_patient(
            patient
        )

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning(
            {
                "event": "pregnant_patient_creation_failed",
                "reason": "validation_error",
                "error": str(e),
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
                "event": "pregnant_patient_creation_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "created_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating patient",
        )


@router.get("/pregnant/{patient_id}", response_model=PregnantPatientResponseSchema)
async def get_pregnant_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get pregnant patient by ID.

    Args:
        patient_id: Patient UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        PregnantPatientResponseSchema: Patient information
    """
    service = PatientService(db)
    try:
        patient = await service.get_pregnant_patient(patient_id)
        return PregnantPatientResponseSchema.from_patient(
            patient
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_pregnant_patient_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving patient",
        )


@router.patch("/pregnant/{patient_id}", response_model=PregnantPatientResponseSchema)
async def update_pregnant_patient(
    patient_id: uuid.UUID,
    update_data: PregnantPatientUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Update pregnant patient (Staff only).

    Args:
        patient_id: Patient UUID
        update_data: Update data
        db: Database session
        current_user: Authenticated staff user

    Returns:
        PregnantPatientResponseSchema: Updated patient information
    """
    service = PatientService(db)
    updated_by_id = current_user.id
    try:
        patient = await service.update_pregnant_patient(
            updated_by_id, patient_id, update_data
        )

        logger.log_info(
            {
                "event": "pregnant_patient_updated",
                "patient_id": str(patient_id),
                "updated_by": str(current_user.id),
            }
        )

        return PregnantPatientResponseSchema.from_patient(
            patient
        )

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.log_error(
            {
                "event": "update_pregnant_patient_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating patient",
        )


@router.post(
    "/pregnant/{patient_id}/convert",
    response_model=RegularPatientResponseSchema,
)
async def convert_to_regular_patient(
    patient_id: uuid.UUID,
    conversion_data: ConvertToRegularPatientSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Convert pregnant patient to regular patient after delivery (Staff only).

    Args:
        patient_id: Patient UUID
        conversion_data: Conversion data
        db: Database session
        current_user: Authenticated staff user

    Returns:
        RegularPatientResponseSchema: Converted patient information
    """
    service = PatientService(db)
    try:
        user_id = current_user.id
        patient = await service.convert_to_regular_patient(user_id, patient_id, conversion_data)

        logger.log_info(
            {
                "event": "patient_converted_to_regular",
                "pregnant_patient_id": str(patient_id),
                "regular_patient_id": str(patient.id),
                "converted_by": str(current_user.id),
            }
        )

        return RegularPatientResponseSchema.from_patient(
            patient
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "patient_conversion_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during patient conversion",
        )


# ============= Regular Patient Routes =============
@router.post(
    "/regular",
    response_model=RegularPatientResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_regular_patient(
    patient_data: RegularPatientCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Create a new regular patient.

    Args:
        patient_data: Regular patient creation data
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        RegularPatientResponseSchema: Created patient information
    """
    service = PatientService(db)
    try:
        # Set facility_id and created_by_id from authenticated user
        patient_data.facility_id = current_user.facility_id
        patient_data.created_by_id = current_user.id

        patient = await service.create_regular_patient(patient_data)

        logger.log_info(
            {
                "event": "regular_patient_created",
                "patient_id": str(patient.id),
                "created_by": str(current_user.id),
                "facility_id": str(patient.facility_id),
            }
        )

        return RegularPatientResponseSchema.from_patient(
            patient
        )

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning(
            {
                "event": "regular_patient_creation_failed",
                "reason": "validation_error",
                "error": str(e),
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
                "event": "regular_patient_creation_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "created_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating patient",
        )


@router.get("/regular/{patient_id}", response_model=RegularPatientResponseSchema)
async def get_regular_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get regular patient by ID (Staff only).

    Args:
        patient_id: Patient UUID
        db: Database session
        current_user: Authenticated staff user

    Returns:
        RegularPatientResponseSchema: Patient information
    """
    service = PatientService(db)
    try:
        patient = await service.get_regular_patient(patient_id)
        return PregnantPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_regular_patient_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving patient",
        )


@router.patch("/regular/{patient_id}", response_model=RegularPatientResponseSchema)
async def update_regular_patient(
    patient_id: uuid.UUID,
    update_data: RegularPatientUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Update regular patient (Staff only).

    Args:
        patient_id: Patient UUID
        update_data: Update data
        db: Database session
        current_user: Authenticated staff user

    Returns:
        RegularPatientResponseSchema: Updated patient information
    """
    service = PatientService(db)
    updated_by_id = current_user.id

    try:
        patient = await service.update_regular_patient(updated_by_id, patient_id, update_data)

        logger.log_info(
            {
                "event": "regular_patient_updated",
                "patient_id": str(patient_id),
                "updated_by": str(current_user.id),
            }
        )

        return RegularPatientResponseSchema.from_patient(
            patient
        )

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.log_error(
            {
                "event": "update_regular_patient_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating patient",
        )


# ============= Common Patient Routes =============
@router.get(
    "",
    response_model=PaginatedResponse[
        PregnantPatientResponseSchema | RegularPatientResponseSchema
    ],
)
async def list_patients(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    pagination: PaginationParams = Depends(get_pagination_params),
    facility_id: Optional[uuid.UUID] = None,
    patient_type: Optional[str] = None,
    patient_status: Optional[str] = None,
):
    """
    Get paginated list of patients with filters (Staff only).

    Args:
        db: Database session
        current_user: Authenticated staff user
        pagination: Pagination parameters
        facility_id: Filter by facility
        patient_type: Filter by patient type (pregnant/regular)
        patient_status: Filter by patient status

    Returns:
        PaginatedResponse: Paginated list of patients
    """
    try:
        from app.services.patient_service import PatientService
        from app.schemas.patient_schemas import (
            PregnantPatientResponseSchema,
            RegularPatientResponseSchema,
        )
        from app.core.pagination import PageInfo, PaginatedResponse
        from math import ceil

        # Initialize service
        patient_service = PatientService(db)

        # Get paginated patients from service
        patients, total_count = await patient_service.list_patients_paginated(
            facility_id=facility_id,
            patient_type=patient_type,
            patient_status=patient_status,
            page=pagination.page,
            page_size=pagination.page_size,
        )

        # Convert each patient to appropriate schema based on patient_type
        validated_items = []
        for patient in patients:
            if patient.patient_type == "pregnant":
                validated_items.append(
                    PregnantPatientResponseSchema.from_patient(patient)
                )
            else:
                validated_items.append(
                    RegularPatientResponseSchema.from_patient(
                        patient
                    )
                )

        # Build pagination metadata
        total_pages = ceil(total_count / pagination.page_size) if total_count > 0 else 0
        has_next = pagination.page < total_pages
        has_previous = pagination.page > 1

        page_info = PageInfo(
            total_items=total_count,
            total_pages=total_pages,
            current_page=pagination.page,
            page_size=pagination.page_size,
            has_next=has_next,
            has_previous=has_previous,
            next_page=pagination.page + 1 if has_next else None,
            previous_page=pagination.page - 1 if has_previous else None,
        )

        # Create response
        response = PaginatedResponse(items=validated_items, page_info=page_info)

        logger.log_info(
            {
                "event": "patients_listed",
                "user_id": str(current_user.id),
                "page": pagination.page,
                "total_items": total_count,
                "filters": {
                    "facility_id": str(facility_id) if facility_id else None,
                    "patient_type": patient_type,
                    "patient_status": patient_status,
                },
            }
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error(
            {
                "event": "list_patients_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving patients",
        )


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Soft delete a patient (Staff only).

    Args:
        patient_id: Patient UUID
        db: Database session
        current_user: Authenticated staff user
    """
    service = PatientService(db)
    try:
        await service.delete_patient(patient_id)

        logger.log_security_event(
            {
                "event_type": "patient_deleted",
                "patient_id": str(patient_id),
                "deleted_by": str(current_user.id),
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "delete_patient_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting patient",
        )