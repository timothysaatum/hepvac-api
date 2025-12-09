import traceback
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from math import ceil

from app.api.dependencies import get_db
from app.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    PageInfo,
    get_pagination_params,
)
from app.core.permission_checker import require_staff_or_admin, require_admin
from app.models.user_model import User
from app.schemas.vaccine_schemas import (
    VaccineCreateSchema,
    VaccineUpdateSchema,
    VaccineResponseSchema,
    VaccineStockUpdateSchema,
    VaccineStockInfoSchema,
    VaccinePublishSchema,
)
from app.services.vaccine_service import VaccineService
from app.core.utils import logger


router = APIRouter(prefix="/vaccines", tags=["vaccines"])


# ============= Vaccine CRUD Routes =============
@router.post(
    "",
    response_model=VaccineResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_vaccine(
    vaccine_data: VaccineCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Create a new vaccine (Admin only).

    Args:
        vaccine_data: Vaccine creation data
        db: Database session
        current_user: Authenticated admin user

    Returns:
        VaccineResponseSchema: Created vaccine information

    Raises:
        400: Vaccine with same name and batch already exists
        500: Internal server error
    """
    service = VaccineService(db)

    try:
        # Set added_by_id from authenticated user
        vaccine_data.added_by_id = current_user.id

        vaccine = await service.create_vaccine(vaccine_data)

        logger.log_info(
            {
                "event": "vaccine_created",
                "vaccine_id": str(vaccine.id),
                "vaccine_name": vaccine.vaccine_name,
                "batch_number": vaccine.batch_number,
                "quantity": vaccine.quantity,
                "price_per_dose": float(vaccine.price_per_dose),
                "created_by": str(current_user.id),
            }
        )

        return VaccineResponseSchema.model_validate(vaccine, from_attributes=True)

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning(
            {
                "event": "vaccine_creation_failed",
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
                "event": "vaccine_creation_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "created_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating vaccine",
        )


@router.get(
    "",
    response_model=PaginatedResponse[VaccineResponseSchema],
)
async def list_vaccines(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    pagination: PaginationParams = Depends(get_pagination_params),
    published_only: bool = Query(
        False, description="Filter to show only published vaccines"
    ),
    low_stock_only: bool = Query(
        False, description="Filter to show only low stock vaccines"
    ),
):
    """
    Get paginated list of vaccines with filters.

    Args:
        db: Database session
        current_user: Authenticated admin or staff user
        pagination: Pagination parameters
        published_only: Filter to show only published vaccines
        low_stock_only: Filter to show only low stock vaccines

    Returns:
        PaginatedResponse[VaccineResponseSchema]: Paginated list of vaccines
    """
    service = VaccineService(db)

    try:
        vaccines, total_count = await service.list_vaccines(
            published_only=published_only,
            low_stock_only=low_stock_only,
            page=pagination.page,
            page_size=pagination.page_size,
        )

        # Validate responses
        validated_items = [
            VaccineResponseSchema.model_validate(v, from_attributes=True)
            for v in vaccines
        ]

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

        response = PaginatedResponse(items=validated_items, page_info=page_info)

        logger.log_info(
            {
                "event": "vaccines_listed",
                "user_id": str(current_user.id),
                "page": pagination.page,
                "total_items": total_count,
                "filters": {
                    "published_only": published_only,
                    "low_stock_only": low_stock_only,
                },
            }
        )

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_vaccines_error",
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving vaccines",
        )


@router.get(
    "/search",
    response_model=PaginatedResponse[VaccineResponseSchema],
)
async def search_vaccines(
    vaccine_name: Optional[str] = Query(None, description="Search by vaccine name (partial match)"),
    batch_number: Optional[str] = Query(None, description="Search by batch number (partial match)"),
    is_published: Optional[bool] = Query(None, description="Filter by published status"),
    low_stock: Optional[bool] = Query(None, description="Filter by low stock"),
    created_from: Optional[str] = Query(None, description="Filter by creation date from (YYYY-MM-DD)"),
    created_to: Optional[str] = Query(None, description="Filter by creation date to (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
    pagination: PaginationParams = Depends(get_pagination_params),
):
    """
    Search vaccines by name or batch number with pagination and date range.
    """
    service = VaccineService(db)

    try:
        vaccines = await service.search_vaccines(
            vaccine_name=vaccine_name,
            batch_number=batch_number,
            published_only=is_published if is_published is not None else False,
            low_stock=low_stock if low_stock is not None else False,
            created_from=created_from,  # ADD THIS
            created_to=created_to,      # ADD THIS
        )

        # Apply pagination manually since search doesn't use skip/limit
        total_count = len(vaccines)
        start = (pagination.page - 1) * pagination.page_size
        end = start + pagination.page_size
        paginated_vaccines = vaccines[start:end]

        # Validate responses
        validated_items = [
            VaccineResponseSchema.model_validate(v, from_attributes=True)
            for v in paginated_vaccines
        ]

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

        response = PaginatedResponse(items=validated_items, page_info=page_info)

        logger.log_info(
            {
                "event": "vaccines_searched",
                "vaccine_name": vaccine_name,
                "batch_number": batch_number,
                "results_count": total_count,
                "is_published": is_published,
                "low_stock": low_stock,
                "created_from": created_from,
                "created_to": created_to,
                "user_id": str(current_user.id),
            }
        )

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "search_vaccines_error",
                "vaccine_name": vaccine_name,
                "batch_number": batch_number,
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching vaccines",
        )


@router.get(
    "/low-stock",
    response_model=List[VaccineResponseSchema],
)
async def get_low_stock_vaccines(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get all vaccines with low stock (quantity < 10).

    Args:
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        List[VaccineResponseSchema]: List of low stock vaccines
    """
    service = VaccineService(db)

    try:
        vaccines = await service.get_low_stock_vaccines()

        logger.log_info(
            {
                "event": "low_stock_vaccines_retrieved",
                "count": len(vaccines),
                "user_id": str(current_user.id),
            }
        )

        return [
            VaccineResponseSchema.model_validate(v, from_attributes=True)
            for v in vaccines
        ]

    except Exception as e:
        logger.log_error(
            {
                "event": "get_low_stock_vaccines_error",
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving low stock vaccines",
        )


@router.get(
    "/{vaccine_id}",
    response_model=VaccineResponseSchema,
)
async def get_vaccine(
    vaccine_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get vaccine by ID.

    Args:
        vaccine_id: Vaccine UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        VaccineResponseSchema: Vaccine information

    Raises:
        404: Vaccine not found
        500: Internal server error
    """
    service = VaccineService(db)

    try:
        vaccine = await service.get_vaccine(vaccine_id)

        return VaccineResponseSchema.model_validate(vaccine, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_vaccine_error",
                "vaccine_id": str(vaccine_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving vaccine",
        )


@router.patch(
    "/{vaccine_id}",
    response_model=VaccineResponseSchema,
)
async def update_vaccine(
    vaccine_id: uuid.UUID,
    update_data: VaccineUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Update vaccine (Admin only).

    Args:
        vaccine_id: Vaccine UUID
        update_data: Update data
        db: Database session
        current_user: Authenticated admin user

    Returns:
        VaccineResponseSchema: Updated vaccine information

    Raises:
        404: Vaccine not found
        400: Validation error or duplicate name/batch
        500: Internal server error
    """
    service = VaccineService(db)

    try:
        vaccine = await service.update_vaccine(vaccine_id, update_data)

        logger.log_info(
            {
                "event": "vaccine_updated",
                "vaccine_id": str(vaccine_id),
                "updated_by": str(current_user.id),
            }
        )

        return VaccineResponseSchema.model_validate(vaccine, from_attributes=True)

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.log_error(
            {
                "event": "update_vaccine_error",
                "vaccine_id": str(vaccine_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating vaccine",
        )


@router.delete(
    "/{vaccine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_vaccine(
    vaccine_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Delete vaccine (Admin only).

    Cannot delete if there are active purchases.

    Args:
        vaccine_id: Vaccine UUID
        db: Database session
        current_user: Authenticated admin user

    Raises:
        404: Vaccine not found
        400: Cannot delete - active purchases exist
        500: Internal server error
    """
    service = VaccineService(db)

    try:
        await service.delete_vaccine(vaccine_id)

        logger.log_security_event(
            {
                "event_type": "vaccine_deleted",
                "vaccine_id": str(vaccine_id),
                "deleted_by": str(current_user.id),
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "delete_vaccine_error",
                "vaccine_id": str(vaccine_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting vaccine",
        )


# ============= Stock Management Routes =============
@router.post(
    "/{vaccine_id}/stock",
    response_model=VaccineResponseSchema,
)
async def add_vaccine_stock(
    vaccine_id: uuid.UUID,
    stock_data: VaccineStockUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Add stock to vaccine inventory (Admin only).

    Args:
        vaccine_id: Vaccine UUID
        stock_data: Stock update data
        db: Database session
        current_user: Authenticated admin user

    Returns:
        VaccineResponseSchema: Updated vaccine information

    Raises:
        404: Vaccine not found
        400: Would exceed maximum stock limit
        500: Internal server error
    """
    service = VaccineService(db)

    try:
        vaccine = await service.add_stock(vaccine_id, stock_data)

        logger.log_info(
            {
                "event": "vaccine_stock_added",
                "vaccine_id": str(vaccine_id),
                "quantity_added": stock_data.quantity_to_add,
                "new_quantity": vaccine.quantity,
                "updated_by": str(current_user.id),
            }
        )

        return VaccineResponseSchema.model_validate(vaccine, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "add_vaccine_stock_error",
                "vaccine_id": str(vaccine_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding vaccine stock",
        )


@router.get(
    "/{vaccine_id}/stock",
    response_model=VaccineStockInfoSchema,
)
async def get_vaccine_stock_info(
    vaccine_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get detailed stock information for a vaccine.

    Includes total quantity, reserved quantity (from active purchases),
    and available quantity.

    Args:
        vaccine_id: Vaccine UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        VaccineStockInfoSchema: Stock information

    Raises:
        404: Vaccine not found
        500: Internal server error
    """
    service = VaccineService(db)

    try:
        stock_info = await service.get_stock_info(vaccine_id)

        logger.log_info(
            {
                "event": "vaccine_stock_info_retrieved",
                "vaccine_id": str(vaccine_id),
                "user_id": str(current_user.id),
            }
        )

        return VaccineStockInfoSchema.model_validate(stock_info)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_vaccine_stock_info_error",
                "vaccine_id": str(vaccine_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving vaccine stock info",
        )


# ============= Publishing Routes =============
@router.patch(
    "/{vaccine_id}/publish",
    response_model=VaccineResponseSchema,
)
async def publish_vaccine(
    vaccine_id: uuid.UUID,
    publish_data: VaccinePublishSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Publish or unpublish a vaccine (Admin only).

    Published vaccines are available for patient purchases.
    Cannot unpublish if there are active purchases.

    Args:
        vaccine_id: Vaccine UUID
        publish_data: Publish/unpublish data
        db: Database session
        current_user: Authenticated admin user

    Returns:
        VaccineResponseSchema: Updated vaccine information

    Raises:
        404: Vaccine not found
        400: Cannot unpublish - active purchases exist
        500: Internal server error
    """
    service = VaccineService(db)

    try:
        vaccine = await service.publish_vaccine(vaccine_id, publish_data)

        action = "published" if publish_data.is_published else "unpublished"

        logger.log_info(
            {
                "event": f"vaccine_{action}",
                "vaccine_id": str(vaccine_id),
                "vaccine_name": vaccine.vaccine_name,
                "updated_by": str(current_user.id),
            }
        )

        return VaccineResponseSchema.model_validate(vaccine, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "publish_vaccine_error",
                "vaccine_id": str(vaccine_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while publishing/unpublishing vaccine",
        )
