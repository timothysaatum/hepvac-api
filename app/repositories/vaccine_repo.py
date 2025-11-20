from typing import Optional, List
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from app.models.vaccine_model import Vaccine, PatientVaccinePurchase


class VaccineRepository:
    """Repository layer for vaccine data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============= Vaccine CRUD Operations =============
    async def create_vaccine(self, vaccine: Vaccine) -> Vaccine:
        """Create a new vaccine."""
        self.db.add(vaccine)
        await self.db.commit()
        await self.db.refresh(vaccine)
        return vaccine

    async def get_vaccine_by_id(self, vaccine_id: uuid.UUID) -> Optional[Vaccine]:
        """Get vaccine by ID with relationships."""
        result = await self.db.execute(
            select(Vaccine)
            .options(selectinload(Vaccine.added_by))
            .options(selectinload(Vaccine.vaccine_purchases))
            .where(Vaccine.id == vaccine_id)
        )
        return result.scalars().first()

    async def get_vaccine_by_name_and_batch(
        self, vaccine_name: str, batch_number: str
    ) -> Optional[Vaccine]:
        """Get vaccine by name and batch number."""
        result = await self.db.execute(
            select(Vaccine).where(
                Vaccine.vaccine_name == vaccine_name,
                Vaccine.batch_number == batch_number,
            )
        )
        return result.scalars().first()

    async def get_vaccines(
        self,
        published_only: bool = False,
        low_stock_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[Vaccine], int]:
        """
        Get list of vaccines with filters and pagination.

        Args:
            published_only: Filter to show only published vaccines
            low_stock_only: Filter to show only low stock vaccines
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            Tuple of (list of vaccines, total count)
        """
        # Base query
        query = select(Vaccine).options(selectinload(Vaccine.added_by))

        # Apply filters
        if published_only:
            query = query.where(Vaccine.is_published == True)

        if low_stock_only:
            query = query.where(Vaccine.quantity < 10)

        # Order by creation date (newest first)
        query = query.order_by(Vaccine.created_at.desc())

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total_count = total_result.scalar() or 0

        # Get paginated results
        paginated_query = query.offset(skip).limit(limit)
        result = await self.db.execute(paginated_query)
        vaccines = result.scalars().all()

        return vaccines, total_count

    async def update_vaccine(self, vaccine: Vaccine) -> Vaccine:
        """Update vaccine."""
        self.db.add(vaccine)
        await self.db.commit()
        await self.db.refresh(vaccine)
        return vaccine

    async def delete_vaccine(self, vaccine: Vaccine) -> None:
        """Delete vaccine."""
        await self.db.delete(vaccine)
        await self.db.commit()

    # ============= Stock Management Operations =============
    async def get_low_stock_vaccines(self, threshold: int = 10) -> List[Vaccine]:
        """Get all vaccines with stock below threshold."""
        result = await self.db.execute(
            select(Vaccine)
            .where(Vaccine.quantity < threshold, Vaccine.is_published == True)
            .order_by(Vaccine.quantity.asc())
        )
        return result.scalars().all()

    async def get_vaccine_reserved_quantity(self, vaccine_id: uuid.UUID) -> int:
        """Calculate total reserved quantity from active purchases."""
        result = await self.db.execute(
            select(func.sum(PatientVaccinePurchase.total_doses)).where(
                PatientVaccinePurchase.vaccine_id == vaccine_id,
                PatientVaccinePurchase.is_active == True,
            )
        )
        reserved = result.scalar()
        return reserved or 0

    # ============= Search Operations =============
    async def search_vaccines(
        self, search_term: str, published_only: bool = False
    ) -> List[Vaccine]:
        """Search vaccines by name or batch number."""
        search_pattern = f"%{search_term}%"

        query = (
            select(Vaccine)
            .options(selectinload(Vaccine.added_by))
            .where(
                (Vaccine.vaccine_name.ilike(search_pattern))
                | (Vaccine.batch_number.ilike(search_pattern))
            )
        )

        if published_only:
            query = query.where(Vaccine.is_published == True)

        query = query.order_by(Vaccine.vaccine_name.asc())

        result = await self.db.execute(query)
        return result.scalars().all()
