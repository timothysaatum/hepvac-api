import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    String,
    Numeric,
    func,
    Enum as SQLEnum,
)
from app.schemas.patient_schemas import PaymentStatus
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.patient_model import Vaccination, Patient, Payment


class Vaccine(Base):
    """Vaccine/Drug records"""

    __tablename__ = "vaccines"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )
    vaccine_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    price_per_dose: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(default=10, nullable=False)
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True, nullable=False
    )

    added_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    added_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[added_by_id], lazy="selectin"
    )

    # Vaccine purchases that reference this vaccine
    vaccine_purchases: Mapped[List["PatientVaccinePurchase"]] = relationship(
        "PatientVaccinePurchase", back_populates="vaccine", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return self.vaccine_name

    def is_low_on_stock(self) -> bool:
        """Check if vaccine stock is low (below 10 units)"""
        return self.quantity < 10


class PatientVaccinePurchase(Base):
    """
    PatientVaccinePurchase - Tracks vaccine purchases with installment payments.
    When a patient buys a vaccine package, this record is created.
    Payments are tracked separately, and doses are administered based on amount paid.
    """

    __tablename__ = "patient_vaccine_purchases"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        index=True,
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    vaccine_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vaccines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Vaccine package details (snapshot at time of purchase)
    vaccine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_per_dose: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    total_doses: Mapped[int] = mapped_column(
        nullable=False, default=3
    )
    total_package_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Payment tracking (installment payments)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Dose administration tracking
    doses_administered: Mapped[int] = mapped_column(default=0, nullable=False)

    # Purchase metadata
    purchase_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="vaccine_purchases",
        lazy="selectin",
    )

    vaccine: Mapped["Vaccine"] = relationship(
        "Vaccine", back_populates="vaccine_purchases", lazy="selectin"
    )

    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id], lazy="selectin"
    )
    # All payments made for this vaccine purchase
    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="vaccine_purchase",
        cascade="all, delete-orphan",
        order_by="Payment.payment_date",
    )
    # All vaccinations (doses) administered from this purchase
    vaccinations: Mapped[List["Vaccination"]] = relationship(
        "Vaccination",
        back_populates="vaccine_purchase",
        cascade="all, delete-orphan",
        order_by="Vaccination.dose_date",
    )

    # Business Logic Methods
    def calculate_doses_paid_for(self) -> int:
        """
        Calculate how many doses the patient has paid for.
        Example: If total is GHS 300 for 3 doses (GHS 100/dose)
                 and patient paid GHS 150, they've paid for 1.5 doses → 1 complete dose
        """
        if self.price_per_dose <= 0 or self.amount_paid <= 0:
            return 0

        # Calculate complete doses paid for (floor division)
        doses_paid = int(self.amount_paid / self.price_per_dose)
        return min(doses_paid, self.total_doses)  # Cap at total doses

    def get_eligible_doses(self) -> int:
        """
        Get number of doses eligible to be administered.
        This is: (doses paid for) - (doses already given)
        """
        doses_paid = self.calculate_doses_paid_for()
        eligible = doses_paid - self.doses_administered
        return max(0, eligible)  # Never negative

    def can_administer_next_dose(self) -> tuple[bool, str]:
        """
        Check if the next dose can be administered.
        Returns (can_administer, message)
        """
        eligible_doses = self.get_eligible_doses()

        if eligible_doses <= 0:
            doses_paid = self.calculate_doses_paid_for()
            if self.doses_administered >= self.total_doses:
                return False, f"All {self.total_doses} doses have been administered."
            else:
                amount_needed = (
                    self.price_per_dose * (self.doses_administered + 1)
                    - self.amount_paid
                )
                return (
                    False,
                    f"Payment required. Need GHS {amount_needed:.2f} more for next dose.",
                )

        return (
            True,
            f"Eligible for {eligible_doses} dose(s). {self.doses_administered} already given.",
        )

    def get_next_dose_number(self) -> Optional[int]:
        """Get the next dose number to administer (1, 2, or 3)"""
        if self.doses_administered >= self.total_doses:
            return None
        return self.doses_administered + 1

    def record_payment(self, amount: Decimal) -> None:
        """
        Update amounts when a payment is made.
        The Payment record itself is created separately.
        """
        self.amount_paid += amount
        self.balance = self.total_package_price - self.amount_paid

        # Update payment status
        if self.balance <= 0:
            self.payment_status = PaymentStatus.COMPLETED
        elif self.amount_paid > 0:
            self.payment_status = PaymentStatus.PARTIAL
        else:
            self.payment_status = PaymentStatus.PENDING

    def record_dose_administered(self) -> bool:
        """
        Increment doses_administered counter after vaccination.
        Returns True if successful, False if not eligible.
        """
        can_administer, _ = self.can_administer_next_dose()
        if can_administer:
            self.doses_administered += 1
            return True
        return False

    def is_completed(self) -> bool:
        """Check if all doses have been administered"""
        return self.doses_administered >= self.total_doses

    def get_payment_progress(self) -> dict:
        """Get a summary of payment and vaccination progress"""
        doses_paid = self.calculate_doses_paid_for()
        return {
            "total_price": float(self.total_package_price),
            "amount_paid": float(self.amount_paid),
            "balance": float(self.balance),
            "payment_status": self.payment_status.value,
            "total_doses": self.total_doses,
            "doses_paid_for": doses_paid,
            "doses_administered": self.doses_administered,
            "eligible_doses": self.get_eligible_doses(),
            "is_completed": self.is_completed(),
        }

    def __repr__(self) -> str:
        return (
            f"<PatientVaccinePurchase id={self.id} "
            f"patient={self.patient.name if self.patient else 'N/A'} "
            f"vaccine={self.vaccine_name} "
            f"paid={self.amount_paid}/{self.total_package_price} "
            f"doses={self.doses_administered}/{self.total_doses}>"
        )
