import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    ChildCreateSchema,
    ChildUpdateSchema,
    ChildResponseSchema,
)
from app.services.patient_service import PatientService
from app.core.utils import logger


router = APIRouter(prefix="/pregnant-patient-child", tags=["pregnant patient child"])

@router.post(
    "/{mother_id}/children",
    response_model=ChildResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_child(
    mother_id: uuid.UUID,
    child_data: ChildCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Create child record for mother (Staff only)."""
    service = PatientService(db)
    try:
        child_data.mother_id = mother_id
        child = await service.create_child(child_data)

        logger.log_info(
            {
                "event": "child_created",
                "child_id": str(child.id),
                "mother_id": str(mother_id),
                "created_by": str(current_user.id),
            }
        )

        return ChildResponseSchema.model_validate(child, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "create_child_error",
                "mother_id": str(mother_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating child record",
        )


@router.get("/{mother_id}/children", response_model=list[ChildResponseSchema])
async def list_mother_children(
    mother_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """List all children for mother (Staff only)."""
    service = PatientService(db)
    try:
        children = await service.list_mother_children(mother_id)
        return [
            ChildResponseSchema.model_validate(c, from_attributes=True)
            for c in children
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_children_error",
                "mother_id": str(mother_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving children",
        )


@router.patch("/children/{child_id}", response_model=ChildResponseSchema)
async def update_child(
    child_id: uuid.UUID,
    update_data: ChildUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Update child record (Staff only)."""
    service = PatientService(db)
    try:
        child = await service.update_child(child_id, update_data)

        logger.log_info(
            {
                "event": "child_updated",
                "child_id": str(child_id),
                "updated_by": str(current_user.id),
            }
        )

        return ChildResponseSchema.model_validate(child, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "update_child_error",
                "child_id": str(child_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating child",
        )
