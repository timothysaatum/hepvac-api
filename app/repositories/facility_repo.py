from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import uuid

from app.models.facility_model import Facility
from app.models.user_model import User


class FacilityRepository:
    """Repository layer for facility data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_facility(self, facility: Facility) -> Facility:
        """
        Create a new facility in the database.

        Args:
            facility: Facility ORM model

        Returns:
            Created facility model with ID and timestamps
        """
        self.db.add(facility)
        await self.db.commit()
        await self.db.refresh(facility)
        return facility

    async def get_facility_by_id(
        self, facility_id: uuid.UUID
    ) -> Optional[Facility]:
        """
        Get facility by ID.

        Args:
            facility_id: Facility's unique identifier
            include_staff: Whether to include staff relationships

        Returns:
            Facility model or None if not found
        """
        query = select(Facility).where(Facility.id == facility_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_facility_by_name(self, facility_name: str) -> Optional[Facility]:
        """
        Get facility by name.

        Args:
            facility_name: Facility's name

        Returns:
            Facility model or None if not found
        """
        result = await self.db.execute(
            select(Facility).where(Facility.facility_name == facility_name)
        )
        return result.scalar_one_or_none()

    async def get_facility_by_email(self, email: str) -> Optional[Facility]:
        """
        Get facility by email.

        Args:
            email: Facility's email address

        Returns:
            Facility model or None if not found
        """
        result = await self.db.execute(
            select(Facility).where(Facility.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_facilities(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        manager_id: Optional[uuid.UUID] = None,
    ) -> List[Facility]:
        """
        Get paginated list of facilities with optional filters.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            search: Search term for facility name or email
            manager_id: Filter by facility manager ID

        Returns:
            List of facility models
        """
        query = select(Facility).options(
            selectinload(Facility.facility_manager),
            selectinload(Facility.staff),
        )

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Facility.facility_name.ilike(search_term),
                    Facility.email.ilike(search_term),
                    Facility.address.ilike(search_term),
                )
            )

        if manager_id:
            query = query.where(Facility.facility_manager_id == manager_id)

        query = query.order_by(Facility.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_facilities(
        self, search: Optional[str] = None, manager_id: Optional[uuid.UUID] = None
    ) -> int:
        """
        Count total facilities with optional filters.

        Args:
            search: Search term for facility name or email
            manager_id: Filter by facility manager ID

        Returns:
            Total count of facilities
        """
        query = select(func.count(Facility.id))

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Facility.facility_name.ilike(search_term),
                    Facility.email.ilike(search_term),
                    Facility.address.ilike(search_term),
                )
            )

        if manager_id:
            query = query.where(Facility.facility_manager_id == manager_id)

        result = await self.db.execute(query)
        return result.scalar_one()

    async def update_facility(self, facility: Facility) -> Facility:
        """
        Update an existing facility.

        Args:
            facility: Facility ORM model with updated values

        Returns:
            Updated facility model
        """
        facility.updated_at = datetime.now(timezone.utc)
        self.db.add(facility)
        await self.db.commit()
        await self.db.refresh(facility)
        return facility

    async def delete_facility(self, facility_id: uuid.UUID) -> bool:
        """
        Delete a facility (hard delete).

        Args:
            facility_id: Facility ID to delete

        Returns:
            True if deleted, False if not found
        """
        facility = await self.get_facility_by_id(facility_id)
        if not facility:
            return False

        await self.db.delete(facility)
        await self.db.commit()
        return True

    async def assign_manager(
        self, facility_id: uuid.UUID, manager_id: uuid.UUID
    ) -> Optional[Facility]:
        """
        Assign or reassign a manager to a facility.

        Args:
            facility_id: Facility ID
            manager_id: User ID to assign as manager

        Returns:
            Updated facility or None if not found
        """
        facility = await self.get_facility_by_id(facility_id)
        if not facility:
            return None

        # Verify user exists
        result = await self.db.execute(select(User).where(User.id == manager_id))
        user = result.scalar_one_or_none()
        if not user:
            return None

        facility.facility_manager_id = manager_id
        return await self.update_facility(facility)

    async def assign_staff_to_facility(
        self, facility_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[User]:
        """
        Assign a staff member to a facility.

        Args:
            facility_id: Facility ID
            user_id: User ID to assign

        Returns:
            Updated user or None if not found
        """
        # Verify facility exists
        facility = await self.get_facility_by_id(facility_id)
        if not facility:
            return None

        # Get and update user
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return None

        user.facility_id = facility_id
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def remove_staff_from_facility(self, user_id: uuid.UUID) -> Optional[User]:
        """
        Remove a staff member from their facility.

        Args:
            user_id: User ID to remove from facility

        Returns:
            Updated user or None if not found
        """
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return None

        user.facility_id = None
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_facility_staff(
        self, facility_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> List[User]:
        """
        Get all staff members for a facility.

        Args:
            facility_id: Facility ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of user models
        """
        query = (
            select(User)
            .where(User.facility_id == facility_id, User.is_deleted == False)
            .order_by(User.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_facility_staff(self, facility_id: uuid.UUID) -> int:
        """
        Count staff members for a facility.

        Args:
            facility_id: Facility ID

        Returns:
            Total count of staff
        """
        query = select(func.count(User.id)).where(
            User.facility_id == facility_id, User.is_deleted == False
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def get_manager_facility(self, manager_id: uuid.UUID) -> Optional[Facility]:
        """
        Get the facility managed by a specific user.

        Args:
            manager_id: User ID of the manager

        Returns:
            Facility model or None if not found
        """
        result = await self.db.execute(
            select(Facility)
            .options(
                selectinload(Facility.staff),
                selectinload(Facility.facility_manager),
            )
            .where(Facility.facility_manager_id == manager_id)
        )
        return result.scalar_one_or_none()
