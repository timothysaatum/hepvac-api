"""
Pagination Utility

Provides reusable pagination functionality for SQLAlchemy queries.
"""

from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from math import ceil


T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination parameters for API requests."""

    page: int = Field(default=1, ge=1, description="Page number (starts at 1)")
    page_size: int = Field(default=10, ge=1, le=100, description="Items per page")

    @property
    def skip(self) -> int:
        """Calculate number of records to skip."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit value."""
        return self.page_size


class PageInfo(BaseModel):
    """Pagination metadata."""

    total_items: int = Field(description="Total number of items")
    total_pages: int = Field(description="Total number of pages")
    current_page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    has_next: bool = Field(description="Whether there is a next page")
    has_previous: bool = Field(description="Whether there is a previous page")
    next_page: Optional[int] = Field(default=None, description="Next page number")
    previous_page: Optional[int] = Field(
        default=None, description="Previous page number"
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: List[T] = Field(description="List of items for current page")
    page_info: PageInfo = Field(description="Pagination metadata")

    class Config:
        from_attributes = True


class Paginator:
    """Utility class for handling pagination in SQLAlchemy queries."""

    @staticmethod
    async def paginate(
        db: AsyncSession,
        query: Select,
        params: PaginationParams,
        schema: Optional[type[BaseModel]] = None,
    ) -> PaginatedResponse:
        """
        Paginate a SQLAlchemy query.

        Args:
            db: Database session
            query: SQLAlchemy select query (without limit/offset)
            params: Pagination parameters
            schema: Optional Pydantic schema to validate items

        Returns:
            PaginatedResponse: Paginated result with metadata

        Example:
            >>> query = select(User).where(User.is_active == True)
            >>> params = PaginationParams(page=1, page_size=10)
            >>> result = await Paginator.paginate(db, query, params, UserSchema)
        """
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total_items = total_result.scalar() or 0

        # Calculate pagination info
        total_pages = ceil(total_items / params.page_size) if total_items > 0 else 0
        has_next = params.page < total_pages
        has_previous = params.page > 1

        # Get paginated items
        paginated_query = query.offset(params.skip).limit(params.limit)
        result = await db.execute(paginated_query)
        items = result.scalars().all()

        # Convert to schema if provided
        if schema:
            items = [
                schema.model_validate(item, from_attributes=True) for item in items
            ]

        # Build page info
        page_info = PageInfo(
            total_items=total_items,
            total_pages=total_pages,
            current_page=params.page,
            page_size=params.page_size,
            has_next=has_next,
            has_previous=has_previous,
            next_page=params.page + 1 if has_next else None,
            previous_page=params.page - 1 if has_previous else None,
        )

        return PaginatedResponse(items=items, page_info=page_info)

    @staticmethod
    def create_page_info(total_items: int, page: int, page_size: int) -> PageInfo:
        """
        Create PageInfo from raw values.

        Args:
            total_items: Total number of items
            page: Current page number
            page_size: Items per page

        Returns:
            PageInfo: Pagination metadata
        """
        total_pages = ceil(total_items / page_size) if total_items > 0 else 0
        has_next = page < total_pages
        has_previous = page > 1

        return PageInfo(
            total_items=total_items,
            total_pages=total_pages,
            current_page=page,
            page_size=page_size,
            has_next=has_next,
            has_previous=has_previous,
            next_page=page + 1 if has_next else None,
            previous_page=page - 1 if has_previous else None,
        )


def get_pagination_params(page: int = 1, page_size: int = 10) -> PaginationParams:
    """
    Dependency for pagination parameters.

    Usage in route:
        @router.get("/users")
        async def list_users(
            pagination: PaginationParams = Depends(get_pagination_params)
        ):
            ...
    """
    return PaginationParams(page=page, page_size=page_size)
