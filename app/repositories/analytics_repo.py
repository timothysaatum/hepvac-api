"""
Analytics repository.

All queries are pure aggregates — no ORM object hydration, no N+1 risk.
Uses SQLAlchemy Core expressions so the DB does all the heavy lifting.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Tuple

from sqlalchemy import (
    Date,
    Integer,
    Numeric,
    cast,
    func,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_model import Child, Patient, PregnantPatient, Pregnancy
from app.models.vaccine_model import PatientVaccinePurchase
from app.schemas.analytics_schemas import (
    AcquisitionDaySchema,
    ClinicalSummarySchema,
    FinancialSummarySchema,
    HepBResultCountsSchema,
    PatientCountsSchema,
    PaymentStatusCountsSchema,
    RevenueDaySchema,
    UpcomingDeliverySchema,
    VaccineDoseCompletionSchema,
)


_ZERO = Decimal("0.00")


class AnalyticsRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─────────────────────────────────────────────────────────────────────────
    # Patient counts
    # ─────────────────────────────────────────────────────────────────────────

    async def get_patient_counts(self) -> PatientCountsSchema:
        """
        Single aggregate query over the patients table.
        Uses FILTER (WHERE ...) — PostgreSQL 9.4+, perfectly safe here.
        """
        this_month_start = func.date_trunc("month", func.now())
        last_month_start = func.date_trunc(
            "month", func.now() - text("INTERVAL '1 month'")
        )
        next_month_start = func.date_trunc(
            "month", func.now() + text("INTERVAL '1 month'")
        )

        stmt = select(
            # totals by type
            func.count().filter(Patient.patient_type == "pregnant").label("pregnant"),
            func.count().filter(Patient.patient_type == "regular").label("regular"),
            # totals by status
            func.count().filter(Patient.status == "active").label("active"),
            func.count().filter(Patient.status == "inactive").label("inactive"),
            func.count().filter(Patient.status == "postpartum").label("postpartum"),
            func.count().filter(Patient.status == "completed").label("completed"),
            # acquisition
            func.count()
            .filter(Patient.created_at >= this_month_start)
            .filter(Patient.created_at < next_month_start)
            .label("new_this_month"),
            func.count()
            .filter(Patient.created_at >= last_month_start)
            .filter(Patient.created_at < this_month_start)
            .label("new_last_month"),
            func.count().label("total"),
        ).where(Patient.is_deleted == False)  # noqa: E712

        row = (await self.db.execute(stmt)).one()

        return PatientCountsSchema(
            total=row.total,
            pregnant=row.pregnant,
            regular=row.regular,
            active=row.active,
            inactive=row.inactive,
            postpartum=row.postpartum,
            completed=row.completed,
            new_this_month=row.new_this_month,
            new_last_month=row.new_last_month,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Financial summary
    # ─────────────────────────────────────────────────────────────────────────

    async def get_financial_summary(self) -> FinancialSummarySchema:
        """
        Single aggregate query over patient_vaccine_purchases.
        balance = total_package_price - amount_paid (not stored, computed here).
        """
        this_month_start = func.date_trunc("month", func.now())
        last_month_start = func.date_trunc(
            "month", func.now() - text("INTERVAL '1 month'")
        )
        next_month_start = func.date_trunc(
            "month", func.now() + text("INTERVAL '1 month'")
        )

        p = PatientVaccinePurchase

        stmt = select(
            func.coalesce(func.sum(p.amount_paid), _ZERO).label("total_revenue"),
            func.coalesce(
                func.sum(p.total_package_price - p.amount_paid), _ZERO
            ).label("total_outstanding"),
            func.coalesce(
                func.sum(p.amount_paid).filter(
                    p.purchase_date >= this_month_start,
                    p.purchase_date < next_month_start,
                ),
                _ZERO,
            ).label("month_revenue"),
            func.coalesce(
                func.sum(p.amount_paid).filter(
                    p.purchase_date >= last_month_start,
                    p.purchase_date < this_month_start,
                ),
                _ZERO,
            ).label("last_month_revenue"),
            func.coalesce(func.sum(p.total_doses), 0).label("total_doses"),
            func.coalesce(func.sum(p.doses_administered), 0).label("administered_doses"),
            func.count().filter(p.payment_status == "completed").label("cnt_completed"),
            func.count().filter(p.payment_status == "partial").label("cnt_partial"),
            func.count().filter(p.payment_status == "pending").label("cnt_pending"),
            func.count().label("total_purchases"),
        )

        row = (await self.db.execute(stmt)).one()

        return FinancialSummarySchema(
            total_revenue=row.total_revenue,
            total_outstanding=row.total_outstanding,
            month_revenue=row.month_revenue,
            last_month_revenue=row.last_month_revenue,
            total_doses=row.total_doses,
            administered_doses=row.administered_doses,
            payment_status_counts=PaymentStatusCountsSchema(
                completed=row.cnt_completed,
                partial=row.cnt_partial,
                pending=row.cnt_pending,
                total_purchases=row.total_purchases,
            ),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Dose completion per vaccine
    # ─────────────────────────────────────────────────────────────────────────

    async def get_dose_completion_by_vaccine(
        self,
    ) -> List[VaccineDoseCompletionSchema]:
        """Aggregate doses purchased vs administered, grouped by vaccine name."""
        p = PatientVaccinePurchase

        stmt = (
            select(
                p.vaccine_name,
                func.sum(p.total_doses).label("total_doses"),
                func.sum(p.doses_administered).label("administered_doses"),
            )
            .group_by(p.vaccine_name)
            .order_by(func.sum(p.total_doses).desc())
        )

        rows = (await self.db.execute(stmt)).all()

        result = []
        for row in rows:
            total = row.total_doses or 0
            administered = row.administered_doses or 0
            rate = round((administered / total) * 100, 1) if total > 0 else 0.0
            result.append(
                VaccineDoseCompletionSchema(
                    vaccine_name=row.vaccine_name,
                    total_doses=total,
                    administered_doses=administered,
                    completion_rate=rate,
                )
            )
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Clinical summary
    # ─────────────────────────────────────────────────────────────────────────

    async def get_clinical_summary(self) -> ClinicalSummarySchema:
        """
        Aggregate clinical metrics:
          - Upcoming / overdue deliveries
          - Six-month checkup completion
          - Hep B antibody test results
        """
        today = date.today()
        window_end = today + timedelta(days=30)

        # ── Deliveries ──────────────────────────────────────────────────────
        delivery_stmt = select(
            func.count()
            .filter(
                Pregnancy.expected_delivery_date >= today,
                Pregnancy.expected_delivery_date <= window_end,
            )
            .label("upcoming"),
            func.count()
            .filter(Pregnancy.expected_delivery_date < today)
            .label("overdue"),
        ).where(
            Pregnancy.is_active == True,  # noqa: E712
            Pregnancy.expected_delivery_date.is_not(None),
        )

        delivery_row = (await self.db.execute(delivery_stmt)).one()

        # ── Checkups ─────────────────────────────────────────────────────────
        checkup_stmt = select(
            func.count()
            .filter(Child.six_month_checkup_completed == False)  # noqa: E712
            .label("pending"),
            func.count()
            .filter(Child.six_month_checkup_completed == True)  # noqa: E712
            .label("completed"),
        )

        checkup_row = (await self.db.execute(checkup_stmt)).one()

        # ── Hep B results ────────────────────────────────────────────────────
        hepb_stmt = select(
            func.count()
            .filter(Child.hep_b_antibody_test_result == "positive")
            .label("positive"),
            func.count()
            .filter(Child.hep_b_antibody_test_result == "negative")
            .label("negative"),
            func.count()
            .filter(Child.hep_b_antibody_test_result == "indeterminate")
            .label("indeterminate"),
            func.count()
            .filter(Child.hep_b_antibody_test_result.is_(None))
            .label("untested"),
        )

        hepb_row = (await self.db.execute(hepb_stmt)).one()

        return ClinicalSummarySchema(
            upcoming_deliveries_30d=delivery_row.upcoming,
            overdue_deliveries=delivery_row.overdue,
            checkups_pending=checkup_row.pending,
            checkups_completed=checkup_row.completed,
            hep_b_results=HepBResultCountsSchema(
                positive=hepb_row.positive,
                negative=hepb_row.negative,
                indeterminate=hepb_row.indeterminate,
                untested=hepb_row.untested,
            ),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Revenue trend (time series)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_revenue_trend(self, days: int) -> List[RevenueDaySchema]:
        """
        Daily revenue and sale count for the last `days` days.
        Returns one row per day that had at least one purchase.
        The frontend fills in zero-days itself (avoids transferring 30 empty rows).
        """
        since = date.today() - timedelta(days=days - 1)
        p = PatientVaccinePurchase

        stmt = (
            select(
                cast(p.purchase_date, Date).label("day"),
                func.coalesce(func.sum(p.amount_paid), _ZERO).label("revenue"),
                func.count().label("sales_count"),
            )
            .where(cast(p.purchase_date, Date) >= since)
            .group_by(cast(p.purchase_date, Date))
            .order_by(cast(p.purchase_date, Date))
        )

        rows = (await self.db.execute(stmt)).all()

        return [
            RevenueDaySchema(
                date=row.day,
                revenue=row.revenue,
                sales_count=row.sales_count,
            )
            for row in rows
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Acquisition trend (time series)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_acquisition_trend(self, days: int) -> List[AcquisitionDaySchema]:
        """
        Daily new patient registrations (split by type) for last `days` days.
        """
        since = date.today() - timedelta(days=days - 1)

        stmt = (
            select(
                cast(Patient.created_at, Date).label("day"),
                func.count()
                .filter(Patient.patient_type == "pregnant")
                .label("pregnant"),
                func.count()
                .filter(Patient.patient_type == "regular")
                .label("regular"),
                func.count().label("total"),
            )
            .where(
                cast(Patient.created_at, Date) >= since,
                Patient.is_deleted == False,  # noqa: E712
            )
            .group_by(cast(Patient.created_at, Date))
            .order_by(cast(Patient.created_at, Date))
        )

        rows = (await self.db.execute(stmt)).all()

        return [
            AcquisitionDaySchema(
                date=row.day,
                pregnant=row.pregnant,
                regular=row.regular,
                total=row.total,
            )
            for row in rows
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Upcoming deliveries detail
    # ─────────────────────────────────────────────────────────────────────────

    async def get_upcoming_deliveries(
        self, days_ahead: int = 30
    ) -> List[UpcomingDeliverySchema]:
        """
        Patients whose active pregnancy EDD is within the next `days_ahead`
        days, plus any that are already overdue.

        Uses raw SQL instead of ORM joins because SQLAlchemy's joined-table
        inheritance for Patient/PregnantPatient automatically emits a
        `patients JOIN pregnant_patients` clause whenever PregnantPatient
        appears in a join — adding an explicit .join(Patient) on top of that
        causes a DuplicateAliasError ("table name 'patients' specified more
        than once").  A text() query sidesteps the ORM entirely.
        """
        from sqlalchemy import text

        today = date.today()
        window_end = today + timedelta(days=days_ahead)

        sql = text("""
            SELECT
                p.id            AS patient_id,
                p.name          AS name,
                p.phone         AS phone,
                pr.expected_delivery_date
            FROM pregnancies pr
            JOIN pregnant_patients pp ON pp.id = pr.patient_id
            JOIN patients p           ON p.id  = pp.id
            WHERE pr.is_active = TRUE
              AND pr.expected_delivery_date IS NOT NULL
              AND pr.expected_delivery_date <= :window_end
              AND p.is_deleted = FALSE
            ORDER BY pr.expected_delivery_date
        """)

        rows = (await self.db.execute(sql, {"window_end": window_end})).all()

        result = []
        for row in rows:
            days_until = (row.expected_delivery_date - today).days
            result.append(
                UpcomingDeliverySchema(
                    patient_id=row.patient_id,
                    name=row.name,
                    phone=row.phone,
                    expected_delivery_date=row.expected_delivery_date,
                    days_until_delivery=days_until,
                )
            )
        return result