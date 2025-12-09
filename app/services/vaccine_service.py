from typing import List, Optional
import uuid
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vaccine_model import Vaccine
from app.schemas.vaccine_schemas import (
    VaccineCreateSchema,
    VaccineUpdateSchema,
    VaccineStockUpdateSchema,
    VaccinePublishSchema,
)
from app.repositories.vaccine_repo import VaccineRepository


class VaccineService:
    """Service layer for vaccine business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = VaccineRepository(self.db)

    # ============= Vaccine CRUD Services =============
    async def create_vaccine(self, vaccine_data: VaccineCreateSchema) -> Vaccine:
        """Create a new vaccine."""

        # Check if vaccine with same name and batch already exists
        existing = await self.repo.get_vaccine_by_name_and_batch(
            vaccine_data.vaccine_name, vaccine_data.batch_number
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vaccine '{vaccine_data.vaccine_name}' with batch number '{vaccine_data.batch_number}' already exists",
            )

        vaccine_dict = vaccine_data.model_dump()
        vaccine = Vaccine(**vaccine_dict)
        return await self.repo.create_vaccine(vaccine)

    async def get_vaccine(self, vaccine_id: uuid.UUID) -> Vaccine:
        """Get vaccine by ID."""
        vaccine = await self.repo.get_vaccine_by_id(vaccine_id)
        if not vaccine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine not found",
            )
        return vaccine

    async def list_vaccines(
        self,
        published_only: bool = False,
        low_stock_only: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[Vaccine], int]:
        """
        List vaccines with filters and pagination.

        Args:
            published_only: Filter to show only published vaccines
            low_stock_only: Filter to show only low stock vaccines
            page: Page number (starts at 1)
            page_size: Items per page

        Returns:
            Tuple of (list of vaccines, total count)
        """
        # Validate pagination parameters
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page number must be greater than 0",
            )

        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page size must be between 1 and 100",
            )

        # Calculate skip
        skip = (page - 1) * page_size

        return await self.repo.get_vaccines(
            published_only=published_only,
            low_stock_only=low_stock_only,
            skip=skip,
            limit=page_size,
        )

    async def update_vaccine(
        self, vaccine_id: uuid.UUID, update_data: VaccineUpdateSchema
    ) -> Vaccine:
        """Update vaccine."""
        vaccine = await self.repo.get_vaccine_by_id(vaccine_id)
        if not vaccine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine not found",
            )

        # Check if updating to duplicate name and batch
        update_dict = update_data.model_dump(exclude_unset=True)
        if "vaccine_name" in update_dict or "batch_number" in update_dict:
            new_name = update_dict.get("vaccine_name", vaccine.vaccine_name)
            new_batch = update_dict.get("batch_number", vaccine.batch_number)

            # Only check if name or batch is actually changing
            if new_name != vaccine.vaccine_name or new_batch != vaccine.batch_number:
                existing = await self.repo.get_vaccine_by_name_and_batch(
                    new_name, new_batch
                )
                if existing and existing.id != vaccine_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Vaccine '{new_name}' with batch number '{new_batch}' already exists",
                    )

        for field, value in update_dict.items():
            setattr(vaccine, field, value)

        return await self.repo.update_vaccine(vaccine)

    async def delete_vaccine(self, vaccine_id: uuid.UUID) -> bool:
        """Delete vaccine."""
        vaccine = await self.repo.get_vaccine_by_id(vaccine_id)
        if not vaccine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine not found",
            )

        # Check if vaccine has active purchases
        if vaccine.vaccine_purchases:
            active_purchases = [
                p
                for p in vaccine.vaccine_purchases
                if p.is_active and not p.is_completed()
            ]
            if active_purchases:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot delete vaccine. {len(active_purchases)} active purchase(s) exist.",
                )

        await self.repo.delete_vaccine(vaccine)
        return True

    # ============= Stock Management Services =============
    async def add_stock(
        self, vaccine_id: uuid.UUID, stock_data: VaccineStockUpdateSchema
    ) -> Vaccine:
        """Add stock to vaccine inventory."""
        vaccine = await self.repo.get_vaccine_by_id(vaccine_id)
        if not vaccine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine not found",
            )

        # Validate that adding won't exceed maximum
        new_quantity = vaccine.quantity + stock_data.quantity_to_add
        if new_quantity > 100000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Adding this quantity would exceed maximum stock limit of 100,000",
            )

        vaccine.quantity += stock_data.quantity_to_add
        return await self.repo.update_vaccine(vaccine)

    async def get_stock_info(self, vaccine_id: uuid.UUID) -> dict:
        """Get detailed stock information for a vaccine."""
        vaccine = await self.repo.get_vaccine_by_id(vaccine_id)
        if not vaccine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine not found",
            )

        # Calculate reserved quantity from active purchases
        reserved_quantity = await self.repo.get_vaccine_reserved_quantity(vaccine_id)
        available_quantity = vaccine.quantity - reserved_quantity

        return {
            "id": vaccine.id,
            "vaccine_name": vaccine.vaccine_name,
            "quantity": vaccine.quantity,
            "is_low_stock": vaccine.is_low_on_stock(),
            "reserved_quantity": reserved_quantity,
            "available_quantity": max(0, available_quantity),
            "batch_number": vaccine.batch_number,
        }

    async def get_low_stock_vaccines(self) -> List[Vaccine]:
        """Get all vaccines with low stock."""
        return await self.repo.get_low_stock_vaccines()

    # ============= Publishing Services =============
    async def publish_vaccine(
        self, vaccine_id: uuid.UUID, publish_data: VaccinePublishSchema
    ) -> Vaccine:
        """Publish or unpublish a vaccine."""
        vaccine = await self.repo.get_vaccine_by_id(vaccine_id)
        if not vaccine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vaccine not found",
            )

        # Don't allow unpublishing if there are active purchases
        if not publish_data.is_published and vaccine.is_published:
            if vaccine.vaccine_purchases:
                active_purchases = [
                    p
                    for p in vaccine.vaccine_purchases
                    if p.is_active and not p.is_completed()
                ]
                if active_purchases:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Cannot unpublish vaccine. {len(active_purchases)} active purchase(s) exist.",
                    )

        vaccine.is_published = publish_data.is_published
        return await self.repo.update_vaccine(vaccine)

    # ============= Search Services =============
    async def search_vaccines(
        self,
        vaccine_name: str | None,
        batch_number: str | None,
        published_only: bool = False,
        low_stock: bool = False,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> List[Vaccine]:
        """Search vaccines by name, batch number, and date range."""

        return await self.repo.search_vaccines(
            vaccine_name.strip() if vaccine_name else None,
            batch_number.strip() if batch_number else None,
            published_only,
            low_stock,
            created_from,
            created_to,
        )