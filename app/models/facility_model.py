import uuid
from datetime import datetime
from app.db.base import Base
from sqlalchemy import TIMESTAMP, ForeignKey, String, func, Index
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

if TYPE_CHECKING:
    from app.models.user_model import User


class Facility(Base):

    __tablename__ = "facilities"
    
    __table_args__ = (
        Index('idx_facility_manager_created', 'facility_manager_id', 'created_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    facility_name: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=True,
    )
    address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    facility_manager_id = mapped_column(
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

    # Relationships
    facility_manager: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[facility_manager_id],
        back_populates="managed_facility",
        lazy="selectin",
    )

    staff: Mapped[List["User"]] = relationship(
        "User",
        foreign_keys="User.facility_id",
        back_populates="facility",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Facility id={self.id} name={self.facility_name}>"

    def assign_manager(self, user: "User") -> None:
        """Assign a facility manager."""
        self.facility_manager = user

    # def get_staff_count(self) -> int:
    #     """Get the total number of staff in the facility."""
    #     return len(self.staff) if self.staff else 0
    

    # Additional helper method for efficient counting (optional to use)
    @classmethod
    def get_staff_count(cls, session, facility_id: uuid.UUID) -> int:
        """
        Use this method in your API endpoints for better performance on large datasets.
        
        Example usage in your API:
            count = Facility.get_staff_count_query(db, facility_id)
        """
        from app.models.user_model import User
        return session.query(func.count(User.id)).filter(
            User.facility_id == facility_id
        ).scalar() or 0