"""
Patient routes.
"""

import traceback
import uuid
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.pagination import (
    PageInfo,
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
)
from app.core.permission_checker import require_staff_or_admin
from app.core.utils import logger
from app.models.user_model import User
from app.schemas.patient_schemas import (
    ConvertToRegularPatientSchema,
    ReRegisterAsPregnantSchema,
    PatientType,
    PregnancyCloseSchema,
    PregnancyCreateSchema,
    PregnancyResponseSchema,
    PregnancyUpdateSchema,
    PregnantPatientCreateSchema,
    PregnantPatientResponseSchema,
    PregnantPatientUpdateSchema,
    RegularPatientCreateSchema,
    RegularPatientResponseSchema,
    RegularPatientUpdateSchema,
)
from app.services.patient_service import PatientService


router = APIRouter(prefix="/patients", tags=["patients"])


# =============================================================================
# Pregnant patient
# =============================================================================

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
    Register a new pregnant patient together with her first pregnancy episode.

    `facility_id` and `created_by_id` are set automatically from the
    authenticated user — do not include them in the request body.
    """
    service = PatientService(db)
    try:
        patient_data.facility_id = current_user.facility_id
        patient_data.created_by_id = current_user.id
        patient_data.first_pregnancy.patient_id = None  # will be set after insert

        patient = await service.create_pregnant_patient(patient_data)

        logger.log_info({
            "event": "pregnant_patient_created",
            "patient_id": str(patient.id),
            "created_by": str(current_user.id),
            "facility_id": str(patient.facility_id),
        })

        return PregnantPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning({
            "event": "pregnant_patient_creation_failed",
            "reason": "validation_error",
            "error": str(e),
            "created_by": str(current_user.id),
        })
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.log_error({
            "event": "pregnant_patient_creation_error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "created_by": str(current_user.id),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the patient.",
        )


@router.get("/pregnant/{patient_id}", response_model=PregnantPatientResponseSchema)
async def get_pregnant_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Get a pregnant patient by ID."""
    service = PatientService(db)
    try:
        patient = await service.get_pregnant_patient(patient_id)
        return PregnantPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "get_pregnant_patient_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the patient.",
        )


@router.patch("/pregnant/{patient_id}", response_model=PregnantPatientResponseSchema)
async def update_pregnant_patient(
    patient_id: uuid.UUID,
    update_data: PregnantPatientUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Update patient-level fields on a pregnant patient.

    To update pregnancy clinical data (dates, gestational age, risk factors)
    use PATCH /pregnancies/{pregnancy_id} instead.
    """
    service = PatientService(db)
    try:
        patient = await service.update_pregnant_patient(
            current_user.id, patient_id, update_data
        )

        logger.log_info({
            "event": "pregnant_patient_updated",
            "patient_id": str(patient_id),
            "updated_by": str(current_user.id),
        })

        return PregnantPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.log_error({
            "event": "update_pregnant_patient_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the patient.",
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
    Convert a pregnant patient to a regular patient after delivery.

    Closes the active pregnancy with the provided outcome, then transitions
    the patient into the long-term HIV treatment pathway.
    """
    service = PatientService(db)
    user_id = current_user.id
    try:
        patient = await service.convert_to_regular_patient(
            user_id, patient_id, conversion_data
        )

        logger.log_info({
            "event": "patient_converted_to_regular",
            "patient_id": str(patient_id),
            "converted_by": str(user_id),
        })

        return RegularPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "patient_conversion_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(user_id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during patient conversion.",
        )


# =============================================================================
# Pregnancy episodes  (nested under /patients/pregnant and standalone)
# =============================================================================

@router.post(
    "/pregnant/{patient_id}/pregnancies",
    response_model=PregnancyResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def open_pregnancy(
    patient_id: uuid.UUID,
    pregnancy_data: PregnancyCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Open a new pregnancy episode for a returning pregnant patient.

    Used when a patient who has previously delivered becomes pregnant again.
    Returns 400 if she already has an active pregnancy.
    """
    service = PatientService(db)
    try:
        pregnancy_data.patient_id = patient_id
        pregnancy = await service.open_pregnancy(
            patient_id, pregnancy_data, current_user.id
        )

        logger.log_info({
            "event": "pregnancy_opened",
            "pregnancy_id": str(pregnancy.id),
            "patient_id": str(patient_id),
            "created_by": str(current_user.id),
        })

        return PregnancyResponseSchema.model_validate(pregnancy)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "open_pregnancy_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while opening the pregnancy.",
        )


@router.get(
    "/pregnant/{patient_id}/pregnancies",
    response_model=list[PregnancyResponseSchema],
)
async def list_patient_pregnancies(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """List all pregnancy episodes for a patient, ordered chronologically."""
    service = PatientService(db)
    try:
        pregnancies = await service.list_patient_pregnancies(patient_id)
        return [PregnancyResponseSchema.model_validate(p) for p in pregnancies]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "list_pregnancies_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving pregnancies.",
        )


@router.get("/pregnancies/{pregnancy_id}", response_model=PregnancyResponseSchema)
async def get_pregnancy(
    pregnancy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Get a single pregnancy episode by ID."""
    service = PatientService(db)
    try:
        pregnancy = await service.get_pregnancy(pregnancy_id)
        return PregnancyResponseSchema.model_validate(pregnancy)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "get_pregnancy_error",
            "pregnancy_id": str(pregnancy_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the pregnancy.",
        )


@router.patch("/pregnancies/{pregnancy_id}", response_model=PregnancyResponseSchema)
async def update_pregnancy(
    pregnancy_id: uuid.UUID,
    update_data: PregnancyUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Update clinical data on an active pregnancy episode.

    Returns 400 if the pregnancy is already closed.
    """
    service = PatientService(db)
    try:
        pregnancy = await service.update_pregnancy(pregnancy_id, update_data)

        logger.log_info({
            "event": "pregnancy_updated",
            "pregnancy_id": str(pregnancy_id),
            "updated_by": str(current_user.id),
        })

        return PregnancyResponseSchema.model_validate(pregnancy)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "update_pregnancy_error",
            "pregnancy_id": str(pregnancy_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the pregnancy.",
        )


@router.post("/pregnancies/{pregnancy_id}/close", response_model=PregnancyResponseSchema)
async def close_pregnancy(
    pregnancy_id: uuid.UUID,
    close_data: PregnancyCloseSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Close an active pregnancy with a clinical outcome.

    Records the outcome (LIVE_BIRTH, STILLBIRTH, MISCARRIAGE, ABORTION, ECTOPIC)
    and delivery date. Increments `para` on the patient when appropriate.
    Returns 400 if the pregnancy is already closed.
    """
    service = PatientService(db)
    try:
        pregnancy = await service.close_pregnancy(
            pregnancy_id, close_data, current_user.id
        )

        logger.log_info({
            "event": "pregnancy_closed",
            "pregnancy_id": str(pregnancy_id),
            "outcome": close_data.outcome.value,
            "closed_by": str(current_user.id),
        })

        return PregnancyResponseSchema.model_validate(pregnancy)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "close_pregnancy_error",
            "pregnancy_id": str(pregnancy_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while closing the pregnancy.",
        )


# =============================================================================
# Regular patient
# =============================================================================

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
    Register a new regular (non-pregnant) patient.

    `facility_id` and `created_by_id` are set automatically from the
    authenticated user.
    """
    service = PatientService(db)
    try:
        patient_data.facility_id = current_user.facility_id
        patient_data.created_by_id = current_user.id

        patient = await service.create_regular_patient(patient_data)

        logger.log_info({
            "event": "regular_patient_created",
            "patient_id": str(patient.id),
            "created_by": str(current_user.id),
            "facility_id": str(patient.facility_id),
        })

        return RegularPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning({
            "event": "regular_patient_creation_failed",
            "reason": "validation_error",
            "error": str(e),
            "created_by": str(current_user.id),
        })
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.log_error({
            "event": "regular_patient_creation_error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "created_by": str(current_user.id),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the patient.",
        )


@router.get("/regular/{patient_id}", response_model=RegularPatientResponseSchema)
async def get_regular_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Get a regular patient by ID."""
    service = PatientService(db)
    try:
        patient = await service.get_regular_patient(patient_id)
        # FIX: original incorrectly returned PregnantPatientResponseSchema here.
        return RegularPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "get_regular_patient_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the patient.",
        )


@router.patch("/regular/{patient_id}", response_model=RegularPatientResponseSchema)
async def update_regular_patient(
    patient_id: uuid.UUID,
    update_data: RegularPatientUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Update a regular patient."""
    service = PatientService(db)
    try:
        patient = await service.update_regular_patient(
            current_user.id, patient_id, update_data
        )

        logger.log_info({
            "event": "regular_patient_updated",
            "patient_id": str(patient_id),
            "updated_by": str(current_user.id),
        })

        return RegularPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.log_error({
            "event": "update_regular_patient_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the patient.",
        )


# =============================================================================
# Common patient
# =============================================================================

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
    """Paginated list of patients with optional filters."""
    try:
        patient_service = PatientService(db)

        patients, total_count = await patient_service.list_patients_paginated(
            facility_id=facility_id,
            patient_type=patient_type,
            patient_status=patient_status,
            page=pagination.page,
            page_size=pagination.page_size,
        )

        validated_items = []
        for patient in patients:
            if patient.patient_type == PatientType.PREGNANT:
                validated_items.append(
                    PregnantPatientResponseSchema.from_patient(patient)
                )
            else:
                validated_items.append(
                    RegularPatientResponseSchema.from_patient(patient)
                )

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

        logger.log_info({
            "event": "patients_listed",
            "user_id": str(current_user.id),
            "page": pagination.page,
            "total_items": total_count,
            "filters": {
                "facility_id": str(facility_id) if facility_id else None,
                "patient_type": patient_type,
                "patient_status": patient_status,
            },
        })

        return PaginatedResponse(items=validated_items, page_info=page_info)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "list_patients_error",
            "error": str(e),
            "error_type": type(e).__name__,
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving patients.",
        )



# =============================================================================
# Re-register as pregnant
# =============================================================================

@router.post(
    "/regular/{patient_id}/re-register-pregnant",
    response_model=PregnantPatientResponseSchema,
    status_code=status.HTTP_200_OK,
)
async def re_register_as_pregnant(
    patient_id: uuid.UUID,
    pregnancy_data: ReRegisterAsPregnantSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Re-register a regular patient as pregnant (second or later pregnancy).

    Flips the patient_type discriminator back to PREGNANT, then opens a new
    Pregnancy episode on the existing pregnant_patients row.  All historical
    data (previous pregnancies, children, vaccines, prescriptions) stays intact.
    """
    service = PatientService(db)
    user_id = current_user.id
    try:
        patient = await service.re_register_as_pregnant(
            user_id, patient_id, pregnancy_data
        )

        logger.log_info({
            "event": "patient_re_registered_as_pregnant",
            "patient_id": str(patient_id),
            "re_registered_by": str(user_id),
        })

        return PregnantPatientResponseSchema.from_patient(patient)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "re_register_pregnant_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(user_id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while re-registering the patient.",
        )


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Soft delete a patient."""
    service = PatientService(db)
    try:
        await service.delete_patient(patient_id)

        logger.log_security_event({
            "event_type": "patient_deleted",
            "patient_id": str(patient_id),
            "deleted_by": str(current_user.id),
        })

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "delete_patient_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the patient.",
        )