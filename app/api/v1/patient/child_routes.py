"""
Child routes.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.core.utils import logger
from app.models.user_model import User
from app.schemas.patient_schemas import (
    ChildCreateSchema,
    ChildResponseSchema,
    ChildUpdateSchema,
)
from app.services.patient_service import PatientService


router = APIRouter(tags=["children"])


# =============================================================================
# Children scoped to a pregnancy episode
# =============================================================================

@router.post(
    "/pregnancies/{pregnancy_id}/children",
    response_model=ChildResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_child(
    pregnancy_id: uuid.UUID,
    child_data: ChildCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Create a child record linked to a specific pregnancy episode.

    The six-month checkup date is automatically calculated from date_of_birth.
    `pregnancy_id` is taken from the URL path — do not include it in the body.
    """
    service = PatientService(db, current_user)
    try:
        # Inject the path param so the service has it.
        child_data.pregnancy_id = pregnancy_id

        child = await service.create_child(child_data)

        logger.log_info({
            "event": "child_created",
            "child_id": str(child.id),
            "pregnancy_id": str(pregnancy_id),
            "created_by": str(current_user.id),
        })

        return ChildResponseSchema.from_child(child)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "create_child_error",
            "pregnancy_id": str(pregnancy_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the child record.",
        )


@router.get(
    "/pregnancies/{pregnancy_id}/children",
    response_model=list[ChildResponseSchema],
)
async def list_pregnancy_children(
    pregnancy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    List all children born from a specific pregnancy episode.

    For multiples (twins, triplets) all children of the same pregnancy are
    returned here. To list all children across a mother's entire history,
    use GET /patients/pregnant/{patient_id}/children.
    """
    service = PatientService(db, current_user)
    try:
        children = await service.list_pregnancy_children(pregnancy_id)
        return [ChildResponseSchema.from_child(c) for c in children]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "list_pregnancy_children_error",
            "pregnancy_id": str(pregnancy_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving children.",
        )


# =============================================================================
# Children scoped to a mother (all pregnancies)
# =============================================================================

@router.get(
    "/patients/pregnant/{patient_id}/children",
    response_model=list[ChildResponseSchema],
)
async def list_mother_children(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    List all children for a mother across ALL her pregnancy episodes.

    Useful for a full lifetime view of a patient's children. For children
    from a specific pregnancy, use GET /pregnancies/{pregnancy_id}/children.
    """
    service = PatientService(db, current_user)
    try:
        children = await service.list_mother_children(patient_id)
        return [ChildResponseSchema.from_child(c) for c in children]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "list_mother_children_error",
            "patient_id": str(patient_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving children.",
        )


# =============================================================================
# Child record management
# =============================================================================

@router.patch("/children/{child_id}", response_model=ChildResponseSchema)
async def update_child(
    child_id: uuid.UUID,
    update_data: ChildUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Update monitoring fields on a child record.

    Used to record six-month checkup completion, Hep B antibody test results,
    and other post-birth follow-up data.
    """
    service = PatientService(db, current_user)
    try:
        child = await service.update_child(
            child_id,
            update_data,
            updated_by_id=current_user.id,
        )

        logger.log_info({
            "event": "child_updated",
            "child_id": str(child_id),
            "updated_by": str(current_user.id),
        })

        return ChildResponseSchema.from_child(child)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "update_child_error",
            "child_id": str(child_id),
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the child record.",
        )
