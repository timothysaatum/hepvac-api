import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.core.utils import logger
from app.models.user_model import User
from app.schemas.patient_schemas import (
    PatientLabResultCreateSchema,
    PatientLabResultUpdateSchema,
    PatientLabTestCreateSchema,
    PatientLabTestResponseSchema,
    PatientLabTestUpdateSchema,
)
from app.services.patient_service import PatientService


router = APIRouter(prefix="/patient-tests", tags=["patient tests"])


@router.post(
    "/{patient_id}",
    response_model=PatientLabTestResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient_lab_test(
    patient_id: uuid.UUID,
    lab_test_data: PatientLabTestCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Create a Hep B, RFT, or LFT test for a patient."""
    service = PatientService(db, current_user)
    try:
        lab_test = await service.create_patient_lab_test(
            patient_id=patient_id,
            lab_test_data=lab_test_data,
            ordered_by_id=current_user.id,
        )

        logger.log_info({
            "event": "patient_lab_test_created",
            "lab_test_id": str(lab_test.id),
            "patient_id": str(patient_id),
            "ordered_by": str(current_user.id),
        })

        return PatientLabTestResponseSchema.from_lab_test(lab_test)

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "create_patient_lab_test_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the lab test.",
        )


@router.get(
    "/{patient_id}",
    response_model=list[PatientLabTestResponseSchema],
)
async def list_patient_lab_tests(
    patient_id: uuid.UUID,
    test_type: Optional[str] = Query(default=None, description="hep_b, rft, or lft"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """List lab tests for a patient."""
    service = PatientService(db, current_user)
    try:
        lab_tests = await service.list_patient_lab_tests(patient_id, test_type)
        return [PatientLabTestResponseSchema.from_lab_test(t) for t in lab_tests]

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "list_patient_lab_tests_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving lab tests.",
        )


@router.get(
    "/record/{lab_test_id}",
    response_model=PatientLabTestResponseSchema,
)
async def get_patient_lab_test(
    lab_test_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Get one lab test with its component results."""
    service = PatientService(db, current_user)
    try:
        lab_test = await service.get_patient_lab_test(lab_test_id)
        return PatientLabTestResponseSchema.from_lab_test(lab_test)

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "get_patient_lab_test_error",
            "lab_test_id": str(lab_test_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the lab test.",
        )


@router.patch(
    "/record/{lab_test_id}",
    response_model=PatientLabTestResponseSchema,
)
async def update_patient_lab_test(
    lab_test_id: uuid.UUID,
    update_data: PatientLabTestUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Update lab test metadata/status."""
    service = PatientService(db, current_user)
    try:
        lab_test = await service.update_patient_lab_test(
            lab_test_id=lab_test_id,
            update_data=update_data,
            reviewed_by_id=current_user.id,
        )

        logger.log_info({
            "event": "patient_lab_test_updated",
            "lab_test_id": str(lab_test_id),
            "updated_by": str(current_user.id),
        })

        return PatientLabTestResponseSchema.from_lab_test(lab_test)

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "update_patient_lab_test_error",
            "lab_test_id": str(lab_test_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the lab test.",
        )


@router.post(
    "/record/{lab_test_id}/results",
    response_model=PatientLabTestResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def add_patient_lab_result(
    lab_test_id: uuid.UUID,
    result_data: PatientLabResultCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Add a component result to a lab test."""
    service = PatientService(db, current_user)
    try:
        lab_test = await service.add_patient_lab_result(
            lab_test_id=lab_test_id,
            result_data=result_data,
            reviewed_by_id=current_user.id,
        )

        logger.log_info({
            "event": "patient_lab_result_added",
            "lab_test_id": str(lab_test_id),
            "updated_by": str(current_user.id),
        })

        return PatientLabTestResponseSchema.from_lab_test(lab_test)

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "add_patient_lab_result_error",
            "lab_test_id": str(lab_test_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding the lab result.",
        )


@router.patch(
    "/results/{lab_result_id}",
    response_model=PatientLabTestResponseSchema,
)
async def update_patient_lab_result(
    lab_result_id: uuid.UUID,
    update_data: PatientLabResultUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Update one component result and recalculate its abnormal indicator."""
    service = PatientService(db, current_user)
    try:
        lab_test = await service.update_patient_lab_result(
            lab_result_id=lab_result_id,
            update_data=update_data,
            reviewed_by_id=current_user.id,
        )

        logger.log_info({
            "event": "patient_lab_result_updated",
            "lab_result_id": str(lab_result_id),
            "updated_by": str(current_user.id),
        })

        return PatientLabTestResponseSchema.from_lab_test(lab_test)

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error({
            "event": "update_patient_lab_result_error",
            "lab_result_id": str(lab_result_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the lab result.",
        )
