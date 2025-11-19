from typing import List, Optional, Tuple
import uuid
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facility_model import Facility
from app.models.user_model import User
from app.repositories.facility_repo import FacilityRepository
from app.repositories.user_repo import UserRepository
from app.schemas.facility_schemas import (
    FacilityCreateSchema,
    FacilityUpdateSchema,
)
from app.core.utils import logger


class FacilityService:
    """Service layer for facility business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = FacilityRepository(self.db)
        self.user_repo = UserRepository(self.db)

    async def create_facility(
        self, facility_data: FacilityCreateSchema, current_user: User
    ) -> Facility:
        """
        Create a new facility and assign current user as manager.

        Args:
            facility_data: FacilityCreateSchema with facility creation data
            current_user: User creating the facility (will be assigned as manager)

        Returns:
            Facility: Created ORM facility model

        Raises:
            HTTPException: If facility creation fails or validation errors occur
        """
        # Check if facility name already exists
        existing_facility = await self.repo.get_facility_by_name(
            facility_data.facility_name
        )
        if existing_facility:
            logger.log_warning(
                {
                    "event": "facility_creation_failed",
                    "reason": "duplicate_facility_name",
                    "facility_name": facility_data.facility_name,
                    "user_id": str(current_user.id),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Facility with name '{facility_data.facility_name}' already exists",
            )

        # Check if user is already managing another facility
        existing_managed_facility = await self.repo.get_manager_facility(
            current_user.id
        )
        if existing_managed_facility:
            logger.log_warning(
                {
                    "event": "facility_creation_failed",
                    "reason": "user_already_managing_facility",
                    "user_id": str(current_user.id),
                    "existing_facility_id": str(existing_managed_facility.id),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You are already managing facility '{existing_managed_facility.facility_name}'",
            )

        # Create facility dictionary
        facility_dict = facility_data.model_dump()
        facility_dict["facility_manager_id"] = current_user.id

        # Normalize email if provided
        if facility_dict.get("email"):
            facility_dict["email"] = facility_dict["email"].lower()

        # Create facility ORM instance
        db_facility = Facility(**facility_dict)

        # Save to database
        created_facility = await self.repo.create_facility(db_facility)
        current_user.facility_id = created_facility.id
        self.db.add(current_user)
        await self.db.commit()
        await self.db.refresh(current_user)
        await self.db.refresh(created_facility)
        logger.log_info(
            {
                "event": "facility_created",
                "facility_id": str(created_facility.id),
                "facility_name": created_facility.facility_name,
                "manager_id": str(current_user.id),
                "manager_username": current_user.username,
            }
        )

        return created_facility

    async def get_facility_by_id(
        self, facility_id: uuid.UUID
    ) -> Facility:
        """
        Get facility by ID.

        Args:
            facility_id: Facility's unique identifier
            include_staff: Whether to include staff relationships

        Returns:
            Facility model

        Raises:
            HTTPException: If facility not found
        """
        facility = await self.repo.get_facility_by_id(facility_id)

        if not facility:
            logger.log_warning(
                {
                    "event": "facility_not_found",
                    "facility_id": str(facility_id),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Facility with ID '{facility_id}' not found",
            )

        return facility

    async def get_facilities(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        manager_id: Optional[uuid.UUID] = None,
    ) -> Tuple[List[Facility], int]:
        """
        Get paginated list of facilities with filters.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            search: Search term for facility name or email
            manager_id: Filter by facility manager ID

        Returns:
            Tuple of (facilities list, total count)
        """
        facilities = await self.repo.get_facilities(
            skip=skip, limit=limit, search=search, manager_id=manager_id
        )
        total = await self.repo.count_facilities(search=search, manager_id=manager_id)

        return facilities, total

    async def update_facility(
        self,
        facility_id: uuid.UUID,
        facility_data: FacilityUpdateSchema,
        current_user: User,
    ) -> Facility:
        """
        Update an existing facility.

        Args:
            facility_id: Facility ID to update
            facility_data: FacilityUpdateSchema with update data
            current_user: User performing the update

        Returns:
            Updated facility model

        Raises:
            HTTPException: If facility not found or validation fails
        """
        # Get existing facility
        facility = await self.get_facility_by_id(facility_id)

        # Check for duplicate facility name (if changing)
        if (
            facility_data.facility_name
            and facility_data.facility_name != facility.facility_name
        ):
            existing_facility = await self.repo.get_facility_by_name(
                facility_data.facility_name
            )
            if existing_facility:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Facility with name '{facility_data.facility_name}' already exists",
                )

        # Check for duplicate email (if changing)
        if facility_data.email and facility_data.email != facility.email:
            existing_email = await self.repo.get_facility_by_email(facility_data.email)
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Facility with email '{facility_data.email}' already exists",
                )

        # Apply updates
        update_data = facility_data.model_dump(exclude_unset=True)

        # Normalize email if provided
        if update_data.get("email"):
            update_data["email"] = update_data["email"].lower()

        for field, value in update_data.items():
            setattr(facility, field, value)

        # Save updates
        updated_facility = await self.repo.update_facility(facility)

        logger.log_info(
            {
                "event": "facility_updated",
                "facility_id": str(facility_id),
                "facility_name": updated_facility.facility_name,
                "updated_by": str(current_user.id),
            }
        )

        return updated_facility

    async def delete_facility(self, facility_id: uuid.UUID, current_user: User) -> bool:
        """
        Delete a facility.

        Args:
            facility_id: Facility ID to delete
            current_user: User performing the deletion

        Returns:
            True if deleted successfully

        Raises:
            HTTPException: If facility not found or has staff assigned
        """
        # Get facility
        facility = await self.get_facility_by_id(facility_id)

        # Check if facility has staff assigned
        staff_count = await self.repo.count_facility_staff(facility_id)
        if staff_count > 0:
            logger.log_warning(
                {
                    "event": "facility_deletion_failed",
                    "reason": "has_staff_assigned",
                    "facility_id": str(facility_id),
                    "staff_count": staff_count,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete facility with {staff_count} staff member(s) assigned. Please reassign or remove staff first.",
            )

        # Delete facility
        deleted = await self.repo.delete_facility(facility_id)

        if deleted:
            logger.log_security_event(
                {
                    "event_type": "facility_deleted",
                    "facility_id": str(facility_id),
                    "facility_name": facility.facility_name,
                    "deleted_by": str(current_user.id),
                }
            )

        return deleted

    async def assign_manager(
        self,
        facility_id: uuid.UUID,
        manager_id: uuid.UUID,
        current_user: User,
    ) -> Facility:
        """
        Assign or reassign a manager to a facility.

        Args:
            facility_id: Facility ID
            manager_id: User ID to assign as manager
            current_user: User performing the assignment

        Returns:
            Updated facility

        Raises:
            HTTPException: If facility or user not found, or validation fails
        """
        # Verify facility exists
        facility = await self.get_facility_by_id(facility_id)

        # Verify user exists and has appropriate role
        user = await self.user_repo.get_user_by_id(manager_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID '{manager_id}' not found",
            )

        # Check if user has admin or manager role
        if not (user.has_role("admin") or user.has_role("facility_manager")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must have 'admin' or 'facility_manager' role to be assigned as facility manager",
            )

        # Check if user is already managing another facility
        existing_managed = await self.repo.get_manager_facility(manager_id)
        if existing_managed and existing_managed.id != facility_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User is already managing facility '{existing_managed.facility_name}'",
            )

        # Assign manager
        updated_facility = await self.repo.assign_manager(facility_id, manager_id)

        logger.log_info(
            {
                "event": "manager_assigned",
                "facility_id": str(facility_id),
                "manager_id": str(manager_id),
                "assigned_by": str(current_user.id),
            }
        )

        return updated_facility

    async def assign_staff(
        self,
        facility_id: uuid.UUID,
        user_id: uuid.UUID,
        current_user: User,
    ) -> User:
        """
        Assign a staff member to a facility.

        Args:
            facility_id: Facility ID
            user_id: User ID to assign as staff
            current_user: User performing the assignment

        Returns:
            Updated user

        Raises:
            HTTPException: If facility or user not found
        """
        # Verify facility exists
        await self.get_facility_by_id(facility_id)

        # Verify user exists
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID '{user_id}' not found",
            )

        # Check if user has staff role
        if not user.has_role("staff"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must have 'staff' role to be assigned to a facility",
            )

        # Assign staff
        updated_user = await self.repo.assign_staff_to_facility(facility_id, user_id)

        logger.log_info(
            {
                "event": "staff_assigned_to_facility",
                "facility_id": str(facility_id),
                "staff_id": str(user_id),
                "assigned_by": str(current_user.id),
            }
        )

        return updated_user

    async def remove_staff(self, user_id: uuid.UUID, current_user: User) -> User:
        """
        Remove a staff member from their facility.

        Args:
            user_id: User ID to remove from facility
            current_user: User performing the removal

        Returns:
            Updated user

        Raises:
            HTTPException: If user not found
        """
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID '{user_id}' not found",
            )

        if not user.facility_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not assigned to any facility",
            )

        facility_id = user.facility_id
        updated_user = await self.repo.remove_staff_from_facility(user_id)

        logger.log_info(
            {
                "event": "staff_removed_from_facility",
                "facility_id": str(facility_id),
                "staff_id": str(user_id),
                "removed_by": str(current_user.id),
            }
        )

        return updated_user

    async def get_facility_staff(
        self, facility_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Tuple[List[User], int]:
        """
        Get all staff members for a facility.

        Args:
            facility_id: Facility ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (staff list, total count)
        """
        # Verify facility exists
        await self.get_facility_by_id(facility_id)

        staff = await self.repo.get_facility_staff(facility_id, skip, limit)
        total = await self.repo.count_facility_staff(facility_id)

        return staff, total
