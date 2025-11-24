from typing import Optional
import uuid
from sqlalchemy import Boolean, Text
from app.db.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    send_to_all_patients: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    send_to_only_pregant: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    send_to_only_mothers: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    send_to_only_regular: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    send_to_only_staff: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    set_reminder_interval: Mapped[int] = mapped_column(
        default=3,
        nullable=False
    )
    set_refresh_rate: Mapped[int] = mapped_column(
        default=30,
        nullable=False
    )
    suspend_system: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
        )
    on_maintance: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
        )
    lock_system: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
        )
    reminder_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
        )
