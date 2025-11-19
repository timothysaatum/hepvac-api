import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    String,
    Numeric,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.patient_model import Vaccination


class Vaccine(Base):
    """Drugs records"""

    __tablename__ = "vaccines"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    vaccine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(default=10, nullable=False)
    added_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    added_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[added_by_id], lazy="selectin"
    )
    vaccinations: Mapped[List["Vaccination"]] = relationship(
        "Vaccination", back_populates="vaccine", foreign_keys="[Vaccination.vaccine_id]"
    )
    # Additional Information
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return self.vaccine_name

    def is_low_on_stock(self):
        return True if self.quantity < 10 else False
