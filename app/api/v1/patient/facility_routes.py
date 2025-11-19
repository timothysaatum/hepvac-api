from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_admin
from app.core.security import get_current_user
from app.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
    Paginator,
)
from app.models.user_model import User
from app.schemas.facility_schemas import (
    FacilityCreateSchema,
    FacilityUpdateSchema,
    FacilityResponseSchema,
)
from app.schemas.user_schemas import UserSchema
from app.services.facility_service import FacilityService
from app.core.utils import logger


router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.post(
    "",
    response_model=FacilityResponseSchema,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin())],
)
async def create_facility(
    facility_data: FacilityCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new facility (Admin only).

    The current user will be automatically assigned as the facility manager.

    Args:
        facility_data: Facility creation data
        db: Database session
        current_user: Current authenticated admin user

    Returns:
        FacilityResponseSchema: Created facility information

    Raises:
        HTTPException: If facility creation fails
    """
    facility_service = FacilityService(db)

    try:
        facility = await facility_service.create_facility(facility_data, current_user)

        logger.log_info(
            {
                "event": "facility_created_via_api",
                "facility_id": str(facility.id),
                "created_by": str(current_user.id),
            }
        )

        return FacilityResponseSchema.model_validate(facility, from_attributes=True)

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning(
            {
                "event": "facility_creation_validation_error",
                "error": str(e),
                "user_id": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.log_error(
            {
                "event": "facility_creation_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the facility",
        )


@router.get(
    "",
    response_model=PaginatedResponse[FacilityResponseSchema],
    dependencies=[Depends(require_admin())],
)
async def list_facilities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    pagination: PaginationParams = Depends(get_pagination_params),
    search: Optional[str] = None,
    manager_id: Optional[uuid.UUID] = None,
):
    """Get paginated list of facilities (Admin only)."""
    facility_service = FacilityService(db)
    try:
        # Get facilities and total count
        facilities, total = await facility_service.get_facilities(
            skip=pagination.skip,
            limit=pagination.limit,
            search=search,
            manager_id=manager_id,
        )

        # Convert to response schemas
        items = [
            FacilityResponseSchema.model_validate(facility, from_attributes=True)
            for facility in facilities
        ]

        # Create page info
        page_info = Paginator.create_page_info(
            total_items=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

        # Create paginated response
        result = PaginatedResponse(items=items, page_info=page_info)

        logger.log_info(
            {
                "event": "facilities_listed",
                "user_id": str(current_user.id),
                "page": pagination.page,
                "total_items": total,
                "search": search,
                "manager_id": str(manager_id) if manager_id else None,
            }
        )

        return result

    except Exception as e:
        logger.log_error(
            {
                "event": "list_facilities_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving facilities",
        )


@router.get(
    "/{facility_id}",
    response_model=FacilityResponseSchema,
    dependencies=[Depends(require_admin())],
)
async def get_facility(
    facility_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get facility by ID (Admin only).

    Args:
        facility_id: Facility UUID
        db: Database session
        current_user: Current authenticated admin user
        include_staff: Whether to include staff relationships

    Returns:
        FacilityResponseSchema: Facility information

    Raises:
        HTTPException: If facility not found
    """
    facility_service = FacilityService(db)

    try:
        facility = await facility_service.get_facility_by_id(facility_id)

        logger.log_info(
            {
                "event": "facility_retrieved",
                "facility_id": str(facility_id),
                "user_id": str(current_user.id),
            }
        )

        return FacilityResponseSchema.model_validate(facility, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_facility_error",
                "facility_id": str(facility_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the facility",
        )


@router.patch(
    "/{facility_id}",
    response_model=FacilityResponseSchema,
    dependencies=[Depends(require_admin())],
)
async def update_facility(
    facility_id: uuid.UUID,
    facility_data: FacilityUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update facility (Admin only).

    Args:
        facility_id: Facility UUID to update
        facility_data: Facility update data
        db: Database session
        current_user: Current authenticated admin user

    Returns:
        FacilityResponseSchema: Updated facility information

    Raises:
        HTTPException: If update fails or facility not found
    """
    facility_service = FacilityService(db)

    try:
        facility = await facility_service.update_facility(
            facility_id, facility_data, current_user
        )

        logger.log_info(
            {
                "event": "facility_updated_via_api",
                "facility_id": str(facility_id),
                "updated_by": str(current_user.id),
            }
        )

        return FacilityResponseSchema.model_validate(facility, from_attributes=True)

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning(
            {
                "event": "facility_update_validation_error",
                "facility_id": str(facility_id),
                "error": str(e),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.log_error(
            {
                "event": "update_facility_error",
                "facility_id": str(facility_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the facility",
        )


@router.delete(
    "/{facility_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin())],
)
async def delete_facility(
    facility_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete facility (Admin only).

    Cannot delete a facility that has staff assigned.

    Args:
        facility_id: Facility UUID to delete
        db: Database session
        current_user: Current authenticated admin user

    Raises:
        HTTPException: If delete fails or facility has staff assigned
    """
    facility_service = FacilityService(db)

    try:
        await facility_service.delete_facility(facility_id, current_user)

        logger.log_security_event(
            {
                "event_type": "facility_deleted_via_api",
                "facility_id": str(facility_id),
                "deleted_by": str(current_user.id),
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "delete_facility_error",
                "facility_id": str(facility_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the facility",
        )


# Manager Assignment Endpoints


@router.post(
    "/{facility_id}/assign-manager/{manager_id}",
    response_model=FacilityResponseSchema,
    dependencies=[Depends(require_admin())],
)
async def assign_facility_manager(
    facility_id: uuid.UUID,
    manager_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Assign or reassign a manager to a facility (Admin only).

    Args:
        facility_id: Facility UUID
        manager_id: User UUID to assign as manager
        db: Database session
        current_user: Current authenticated admin user

    Returns:
        FacilityResponseSchema: Updated facility information

    Raises:
        HTTPException: If assignment fails
    """
    facility_service = FacilityService(db)

    try:
        facility = await facility_service.assign_manager(
            facility_id, manager_id, current_user
        )

        logger.log_security_event(
            {
                "event_type": "facility_manager_assigned",
                "facility_id": str(facility_id),
                "manager_id": str(manager_id),
                "assigned_by": str(current_user.id),
            }
        )

        return FacilityResponseSchema.model_validate(facility, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "assign_manager_error",
                "facility_id": str(facility_id),
                "manager_id": str(manager_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while assigning the manager",
        )


# Staff Management Endpoints


@router.post(
    "/{facility_id}/assign-staff/{user_id}",
    response_model=UserSchema,
    dependencies=[Depends(require_admin())],
)
async def assign_staff_to_facility(
    facility_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Assign a staff member to a facility (Admin only).

    Args:
        facility_id: Facility UUID
        user_id: User UUID to assign as staff
        db: Database session
        current_user: Current authenticated admin user

    Returns:
        UserSchema: Updated user information

    Raises:
        HTTPException: If assignment fails
    """
    facility_service = FacilityService(db)

    try:
        user = await facility_service.assign_staff(facility_id, user_id, current_user)

        logger.log_info(
            {
                "event": "staff_assigned_via_api",
                "facility_id": str(facility_id),
                "user_id": str(user_id),
                "assigned_by": str(current_user.id),
            }
        )

        return UserSchema.model_validate(user, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "assign_staff_error",
                "facility_id": str(facility_id),
                "user_id": str(user_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while assigning the staff member",
        )


@router.delete(
    "/staff/{user_id}",
    response_model=UserSchema,
    dependencies=[Depends(require_admin())],
)
async def remove_staff_from_facility(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Remove a staff member from their facility (Admin only).

    Args:
        user_id: User UUID to remove from facility
        db: Database session
        current_user: Current authenticated admin user

    Returns:
        UserSchema: Updated user information

    Raises:
        HTTPException: If removal fails
    """
    facility_service = FacilityService(db)

    try:
        user = await facility_service.remove_staff(user_id, current_user)

        logger.log_info(
            {
                "event": "staff_removed_via_api",
                "user_id": str(user_id),
                "removed_by": str(current_user.id),
            }
        )

        return UserSchema.model_validate(user, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "remove_staff_error",
                "user_id": str(user_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while removing the staff member",
        )


@router.get(
    "/{facility_id}/staff",
    response_model=PaginatedResponse[UserSchema],
    dependencies=[Depends(require_admin())],
)
async def get_facility_staff(
    facility_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    pagination: PaginationParams = Depends(get_pagination_params),
):
    """
    Get all staff members for a facility (Admin only).

    Args:
        facility_id: Facility UUID
        db: Database session
        current_user: Current authenticated admin user
        pagination: Pagination parameters (page, page_size)

    Returns:
        PaginatedResponse: Paginated list of staff members

    Raises:
        HTTPException: If retrieval fails
    """
    facility_service = FacilityService(db)

    try:
        # Calculate offset
        skip = (pagination.page - 1) * pagination.page_size
        limit = pagination.page_size

        # Get staff and total count
        staff, total = await facility_service.get_facility_staff(
            facility_id, skip=skip, limit=limit
        )

        # Convert to schemas
        staff_schemas = [
            UserSchema.model_validate(user, from_attributes=True) for user in staff
        ]

        page_info = Paginator.create_page_info(
            total_items=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
        # Create paginated response
        result = PaginatedResponse(items=staff_schemas, page_info=page_info)

        logger.log_info(
            {
                "event": "facility_staff_listed",
                "facility_id": str(facility_id),
                "user_id": str(current_user.id),
                "page": pagination.page,
                "total_items": total,
            }
        )

        return result

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_facility_staff_error",
                "facility_id": str(facility_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving facility staff",
        )
