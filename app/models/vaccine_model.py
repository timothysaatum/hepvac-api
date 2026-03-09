"""
Vaccine and PatientVaccinePurchase models.

Vaccine       — the vaccine/drug master record (stock management).
PatientVaccinePurchase — a patient's purchase of a vaccine package,
                         with installment payment and dose administration tracking.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.schemas.patient_schemas import PaymentStatus

if TYPE_CHECKING:
    from app.models.patient_model import Patient, Payment, Vaccination
    from app.models.user_model import User


# ---------------------------------------------------------------------------
# Vaccine
# ---------------------------------------------------------------------------


class Vaccine(Base):
    """
    Vaccine / drug master record.

    Tracks stock levels, pricing, and batch information. Purchases reference
    this record but snapshot price/batch at purchase time to preserve history.
    """

    __tablename__ = "vaccines"

    __table_args__ = (
        # DB-level guard: reserved can never exceed total stock.
        CheckConstraint(
            "reserved_quantity <= quantity",
            name="ck_reserved_lte_quantity",
        ),
        # DB-level guard: stock counts must be non-negative.
        CheckConstraint("quantity >= 0", name="ck_quantity_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="ck_reserved_non_negative"),
    )

    # The quantity below which a stock replenishment alert should be raised.
    LOW_STOCK_THRESHOLD: int = 10

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    vaccine_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    price_per_dose: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(default=10, nullable=False)

    # Doses committed to active purchases but not yet administered.
    # Maintained by the service layer:
    #   +total_doses  when a purchase is created
    #   -1            when a dose is administered
    #   -(total_doses - doses_administered)  when a purchase is deactivated
    # Never update this directly — always go through the service methods.
    reserved_quantity: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    batch_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        nullable=False,
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

    added_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[added_by_id],
        lazy="selectin",
    )
    vaccine_purchases: Mapped[List["PatientVaccinePurchase"]] = relationship(
        "PatientVaccinePurchase",
        back_populates="vaccine",
        cascade="all, delete-orphan",
        # Never load this collection eagerly. Query explicitly in the service layer
        # when a list of purchases for a vaccine is actually needed.
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Vaccine id={self.id} name={self.vaccine_name}>"

    @hybrid_property
    def available_quantity(self) -> int:
        """
        Doses available for new purchases (total stock minus reserved).

        Always use this — not ``quantity`` — when deciding whether a new
        purchase can be fulfilled. ``quantity`` includes doses already
        committed to active purchases that haven't been administered yet.
        """
        return self.quantity - self.reserved_quantity

    def is_low_on_stock(self) -> bool:
        """
        Return True if available (unreserved) quantity is below LOW_STOCK_THRESHOLD.

        Checks available_quantity, not quantity, so reserved doses don't
        mask a genuine low-stock situation.
        """
        return self.available_quantity < self.LOW_STOCK_THRESHOLD


# ---------------------------------------------------------------------------
# PatientVaccinePurchase
# ---------------------------------------------------------------------------


class PatientVaccinePurchase(Base):
    """
    Tracks a patient's purchase of a vaccine package with installment payments.

    When a patient buys a vaccine package, one record is created here.
    Subsequent payments are recorded in Payment. Doses are administered
    (Vaccination records) only when sufficient payment has been received.

    Payment flow:
        1. Purchase created → total_package_price set, amount_paid = 0
        2. Patient makes payment → record_payment(amount) called
        3. System checks can_administer_next_dose() before each vaccination
        4. Vaccination recorded → record_dose_administered() called
    """

    __tablename__ = "patient_vaccine_purchases"

    __table_args__ = (
        # PARTIAL UNIQUE INDEX: only one *active* purchase per patient+vaccine.
        # This replaces the previous UniqueConstraint("patient_id", "vaccine_id",
        # "is_active") which was broken — PostgreSQL allows multiple rows with the
        # same (patient_id, vaccine_id, TRUE) through concurrent inserts because a
        # regular unique constraint has no predicate filtering. A partial index with
        # WHERE is_active = TRUE is the correct, race-safe approach, and mirrors
        # the pattern used on pregnancies(is_active = TRUE).
        Index(
            "uix_one_active_purchase_per_patient_vaccine",
            "patient_id",
            "vaccine_id",
            unique=True,
            postgresql_where="is_active = TRUE",
        ),
        # DB-level guard: total_doses must be a positive integer.
        CheckConstraint("total_doses > 0", name="ck_total_doses_positive"),
        # DB-level guard: price_per_dose must be non-negative.
        CheckConstraint("price_per_dose >= 0", name="ck_price_per_dose_non_negative"),
        # DB-level guard: amount_paid cannot exceed total_package_price.
        CheckConstraint(
            "amount_paid <= total_package_price",
            name="ck_amount_paid_lte_total",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
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

    # Snapshot of vaccine details at time of purchase — preserves history
    # even if the Vaccine master record is updated later.
    vaccine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_per_dose: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    total_doses: Mapped[int] = mapped_column(nullable=False, default=3)
    total_package_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Installment payment tracking
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    # balance is derived — not stored — to prevent drift if amount_paid or
    # total_package_price is ever patched directly (migration, admin fix).
    # Use purchase.balance anywhere you need the outstanding amount.
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
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    # object is rarely needed in payment/dose logic. Load explicitly when required.
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="vaccine_purchases",
        lazy="noload",
    )

    # `vaccine` kept as selectin — price/batch info frequently needed together
    # with the purchase record.
    vaccine: Mapped["Vaccine"] = relationship(
        "Vaccine",
        back_populates="vaccine_purchases",
        lazy="selectin",
    )

    # not needed in payment/dosing hot paths.
    created_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by_id],
        lazy="noload",
    )

    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="vaccine_purchase",
        cascade="all, delete-orphan",
        order_by="Payment.payment_date",
        lazy="noload",
    )
    vaccinations: Mapped[List["Vaccination"]] = relationship(
        "Vaccination",
        back_populates="vaccine_purchase",
        cascade="all, delete-orphan",
        order_by="Vaccination.dose_date",
        lazy="noload",
    )

    # -----------------------------------------------------------------------
    # Computed properties
    # -----------------------------------------------------------------------

    @hybrid_property
    def balance(self) -> Decimal:
        """
        Outstanding balance, computed from total_package_price − amount_paid.

        Not stored as a column to prevent drift when either component is
        patched directly (e.g. admin corrections, data migrations).
        Always authoritative — no sync required.
        """
        return self.total_package_price - self.amount_paid

    # -----------------------------------------------------------------------
    # Business logic
    # -----------------------------------------------------------------------

    def calculate_doses_paid_for(self) -> int:
        """
        Calculate how many complete doses the patient has paid for.

        Example: total GHS 300 / 3 doses = GHS 100/dose.
                 Paid GHS 150 → 1 complete dose paid.

        Returns 0 if price_per_dose is 0 or no payment has been made.
        """
        # FIX: guard against ZeroDivisionError when price_per_dose is 0.
        if self.price_per_dose <= 0 or self.amount_paid <= 0:
            return 0
        doses_paid = int(self.amount_paid / self.price_per_dose)
        return min(doses_paid, self.total_doses)

    def get_eligible_doses(self) -> int:
        """
        Return the number of doses eligible to be administered right now.

        = doses_paid_for − doses_already_administered (minimum 0).
        """
        eligible = self.calculate_doses_paid_for() - self.doses_administered
        return max(0, eligible)

    def can_administer_next_dose(self) -> Tuple[bool, str]:
        """
        Check whether the next dose may be administered.

        Returns (True, message) if eligible, (False, reason) otherwise.
        """
        eligible_doses = self.get_eligible_doses()

        if eligible_doses > 0:
            return (
                True,
                f"Eligible for {eligible_doses} dose(s). "
                f"{self.doses_administered} already administered.",
            )

        if self.doses_administered >= self.total_doses:
            return False, f"All {self.total_doses} doses have been administered."

        amount_needed = (
            self.price_per_dose * (self.doses_administered + 1) - self.amount_paid
        )
        return (
            False,
            f"Payment required. Need GHS {amount_needed:.2f} more for next dose.",
        )

    def get_next_dose_number(self) -> Optional[int]:
        """Return the next dose number (1-based) or None if all doses given."""
        if self.doses_administered >= self.total_doses:
            return None
        return self.doses_administered + 1

    def record_payment(self, amount: Decimal) -> None:
        """
        Apply a payment to this purchase and update running totals.

        The corresponding Payment record must be created separately by the
        caller (service layer). This method only updates the in-memory totals
        on the already-loaded ORM object.

        .. warning:: Concurrency — use ``SELECT ... FOR UPDATE`` at the service layer.
            In a concurrent system, two simultaneous payment requests can both
            read the same ``amount_paid`` value before either write completes,
            causing both to compute the wrong new total (lost-update anomaly).

            The service layer **must** lock the row before calling this method::

                # SQLAlchemy async example
                stmt = (
                    select(PatientVaccinePurchase)
                    .where(PatientVaccinePurchase.id == purchase_id)
                    .with_for_update()
                )
                result = await session.execute(stmt)
                purchase = result.scalar_one()
                purchase.record_payment(amount)
                await session.flush()

            Alternatively use a SQL-expression UPDATE with ``RETURNING`` to
            avoid loading the row at all.

        Raises:
            ValueError: if amount is not a positive value.
        """
        if amount <= Decimal("0.00"):
            raise ValueError(
                f"Payment amount must be positive; received {amount}."
            )

        # Cap amount_paid so overpayments don't corrupt the balance.
        self.amount_paid = min(
            self.amount_paid + amount,
            self.total_package_price,
        )
        # balance is now a computed property — no assignment needed.

        # Derive status from the updated totals.
        if self.balance <= Decimal("0.00"):
            self.payment_status = PaymentStatus.COMPLETED
        elif self.amount_paid > Decimal("0.00"):
            self.payment_status = PaymentStatus.PARTIAL
        else:
            self.payment_status = PaymentStatus.PENDING

    def record_dose_administered(self) -> bool:
        """
        Increment doses_administered after a successful vaccination.

        Returns True if the dose was recorded, False if not eligible.
        """
        can_administer, _ = self.can_administer_next_dose()
        if can_administer:
            self.doses_administered += 1
            return True
        return False

    def is_completed(self) -> bool:
        """Return True if all doses in this package have been administered."""
        return self.doses_administered >= self.total_doses

    def get_payment_progress(self) -> Dict[str, object]:
        """
        Return a summary of payment and vaccination progress.

        FIX: monetary values returned as str rather than float to avoid
        IEEE 754 precision loss. Callers should use Decimal(value) or
        rely on Pydantic's Decimal parsing.
        """
        doses_paid = self.calculate_doses_paid_for()
        return {
            "total_price": str(self.total_package_price),
            "amount_paid": str(self.amount_paid),
            "balance": str(self.balance),  # computed property — always accurate
            "payment_status": self.payment_status.value,
            "total_doses": self.total_doses,
            "doses_paid_for": doses_paid,
            "doses_administered": self.doses_administered,
            "eligible_doses": self.get_eligible_doses(),
            "is_completed": self.is_completed(),
        }

    def __repr__(self) -> str:
        # when the relationship is not loaded. Use patient_id instead.
        return (
            f"<PatientVaccinePurchase id={self.id} "
            f"patient_id={self.patient_id} "
            f"vaccine={self.vaccine_name} "
            f"paid={self.amount_paid}/{self.total_package_price} "
            f"doses={self.doses_administered}/{self.total_doses}>"
        )