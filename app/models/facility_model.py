"""
Facility model.

Represents a healthcare facility (clinic/hospital). Each facility has a manager
(a User) and a list of staff (Users). Facilities own patients.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Index, String, func, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_model import User


class Facility(Base):
    """
    Healthcare facility (clinic or hospital).

    A facility has one optional manager and zero or more staff members.
    All patients belong to a facility. Staff are Users whose `facility_id`
    points here.
    """

    __tablename__ = "facilities"

    __table_args__ = (
        # Composite index for common manager + date-range queries.
        Index("idx_facility_manager_created", "facility_manager_id", "created_at"),
        Index("idx_facility_email", "email"),
        Index("idx_facility_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    facility_name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=True,
    )
    address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    facility_manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_facility_manager_id",
        ),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    # Single object — selectin is acceptable (no N+1 risk).
    facility_manager: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[facility_manager_id],
        back_populates="managed_facility",
        lazy="selectin",
    )

    staff: Mapped[List["User"]] = relationship(
        "User",
        foreign_keys="[User.facility_id]",
        back_populates="facility",
        lazy="noload",
    )

    # -----------------------------------------------------------------------
    # Methods
    # -----------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<Facility id={self.id} name={self.facility_name}>"

    def assign_manager(self, user: "User") -> None:
        """
        Assign a facility manager.

        Sets both the ORM relationship AND the FK column so the FK is
        immediately correct before the session flushes.
        """
        self.facility_manager = user
        self.facility_manager_id = user.id

    @classmethod
    async def get_staff_count(cls, session: AsyncSession, facility_id: uuid.UUID) -> int:
        """
        Return the number of active (non-deleted) staff in a facility.

        Uses a COUNT query — safe for large facilities; avoids loading all
        User objects into memory.

        The method is ``async`` to match the application's AsyncSession
        throughout.  Calling ``session.scalar()`` directly on an AsyncSession
        would block the event loop; ``await session.scalar()`` is correct.

        Usage in a service or route:
            count = await Facility.get_staff_count(db, facility_id)
        """
        from app.models.user_model import User  # local import to avoid circular dep

        stmt = select(func.count(User.id)).where(
            User.facility_id == facility_id,
            User.is_deleted.is_(False),
        )
        return await session.scalar(stmt) or 0