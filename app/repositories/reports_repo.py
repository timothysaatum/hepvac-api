"""
Report repository — raw SQL throughout.

Why raw SQL instead of ORM joins?
  Patient uses joined-table inheritance (patients + pregnant_patients /
  regular_patients).  Whenever an ORM query references PregnantPatient,
  SQLAlchemy automatically emits a `patients JOIN pregnant_patients` clause.
  Adding any further explicit join back to patients (or selecting Patient
  columns alongside Pregnancy columns) causes PostgreSQL to reject the
  query with DuplicateAliasError: "table name 'patients' specified more
  than once".

  Raw text() queries give us full control over aliases and avoid the issue
  entirely.  All methods return plain Row objects — the service layer reads
  attributes by name.
"""

from __future__ import annotations

from typing import Any, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.reports_schemas import ReportFilters


# ─────────────────────────────────────────────────────────────────────────────
# Filter helpers
# ─────────────────────────────────────────────────────────────────────────────

def _patient_where(filters: ReportFilters, alias: str = "p") -> tuple[str, dict]:
    """
    Build the WHERE fragment and params dict for patient-scoped filters.
    `alias` is the SQL alias used for the patients table in the calling query.
    """
    clauses = [f"{alias}.is_deleted = FALSE"]
    params: dict[str, Any] = {}

    if filters.patient_type:
        clauses.append(f"{alias}.patient_type = :patient_type")
        params["patient_type"] = filters.patient_type

    if filters.patient_status:
        clauses.append(f"{alias}.status = :patient_status")
        params["patient_status"] = filters.patient_status

    if filters.facility_id:
        clauses.append(f"{alias}.facility_id = :facility_id")
        params["facility_id"] = str(filters.facility_id)

    if filters.date_from:
        clauses.append(f"{alias}.created_at::date >= :date_from")
        params["date_from"] = filters.date_from

    if filters.date_to:
        clauses.append(f"{alias}.created_at::date <= :date_to")
        params["date_to"] = filters.date_to

    return " AND ".join(clauses), params


class ReportRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─────────────────────────────────────────────────────────────────────────
    # Patients
    # ─────────────────────────────────────────────────────────────────────────

    async def get_patients(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")
        sql = text(f"""
            SELECT
                p.id,
                p.name,
                p.phone,
                p.sex,
                p.date_of_birth,
                p.patient_type,
                p.status         AS patient_status,
                p.created_at,
                p.accepts_messaging,
                f.facility_name,
                -- pregnant-specific
                pp.gravida,
                pp.para,
                -- regular-specific
                rp.diagnosis_date,
                rp.treatment_start_date,
                rp.treatment_regimen,
                rp.viral_load,
                rp.last_viral_load_date,
                rp.medical_history,
                rp.allergies
            FROM patients p
            LEFT JOIN facilities f          ON f.id  = p.facility_id
            LEFT JOIN pregnant_patients pp  ON pp.id = p.id
            LEFT JOIN regular_patients  rp  ON rp.id = p.id
            WHERE {where}
            ORDER BY p.created_at
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Pregnancies
    # ─────────────────────────────────────────────────────────────────────────

    async def get_pregnancies(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")
        sql = text(f"""
            SELECT
                pr.id,
                pr.patient_id,
                p.name              AS patient_name,
                pr.pregnancy_number,
                pr.lmp_date,
                pr.expected_delivery_date,
                pr.actual_delivery_date,
                pr.gestational_age_weeks,
                pr.is_active,
                pr.outcome,
                pr.risk_factors,
                pr.notes,
                pr.created_at
            FROM pregnancies pr
            JOIN pregnant_patients pp ON pp.id = pr.patient_id
            JOIN patients p           ON p.id  = pp.id
            WHERE {where}
            ORDER BY pr.created_at
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Children
    # ─────────────────────────────────────────────────────────────────────────

    async def get_children(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")
        sql = text(f"""
            SELECT
                c.id,
                c.name,
                c.sex,
                c.date_of_birth,
                pr.patient_id       AS mother_patient_id,
                p.name              AS mother_name,
                c.pregnancy_id,
                c.six_month_checkup_date,
                c.six_month_checkup_completed,
                c.hep_b_antibody_test_result,
                c.test_date,
                c.notes
            FROM children c
            JOIN pregnancies pr        ON pr.id = c.pregnancy_id
            JOIN pregnant_patients pp  ON pp.id = pr.patient_id
            JOIN patients p            ON p.id  = pp.id
            WHERE {where}
            ORDER BY c.date_of_birth
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Vaccine purchases (transactions)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_purchases(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")

        date_clauses = []
        if filters.date_from:
            date_clauses.append("pvp.purchase_date::date >= :date_from")
        if filters.date_to:
            date_clauses.append("pvp.purchase_date::date <= :date_to")
        if date_clauses:
            where += " AND " + " AND ".join(date_clauses)

        sql = text(f"""
            SELECT
                pvp.id,
                pvp.patient_id,
                p.name              AS patient_name,
                p.phone             AS patient_phone,
                pvp.vaccine_name,
                pvp.batch_number,
                pvp.total_doses,
                pvp.price_per_dose,
                pvp.total_package_price,
                pvp.amount_paid,
                (pvp.total_package_price - pvp.amount_paid) AS balance,
                pvp.payment_status,
                pvp.doses_administered,
                pvp.purchase_date,
                pvp.is_active
            FROM patient_vaccine_purchases pvp
            JOIN patients p ON p.id = pvp.patient_id
            WHERE {where}
            ORDER BY pvp.purchase_date
        """)
        return (await self.db.execute(sql, params)).all()

    async def get_payments(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")

        date_clauses = []
        if filters.date_from:
            date_clauses.append("pay.payment_date >= :date_from")
        if filters.date_to:
            date_clauses.append("pay.payment_date <= :date_to")
        if date_clauses:
            where += " AND " + " AND ".join(date_clauses)

        sql = text(f"""
            SELECT
                pay.id,
                pay.patient_id,
                p.name          AS patient_name,
                pay.amount,
                pay.payment_date,
                pay.payment_method,
                pay.reference_number,
                pay.vaccine_purchase_id
            FROM payments pay
            JOIN patients p ON p.id = pay.patient_id
            WHERE {where}
            ORDER BY pay.payment_date
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Vaccinations (administered doses)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_vaccinations(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")

        date_clauses = []
        if filters.date_from:
            date_clauses.append("v.dose_date >= :date_from")
        if filters.date_to:
            date_clauses.append("v.dose_date <= :date_to")
        if date_clauses:
            where += " AND " + " AND ".join(date_clauses)

        sql = text(f"""
            SELECT
                v.id,
                v.patient_id,
                p.name              AS patient_name,
                v.vaccine_name,
                v.dose_number,
                v.dose_date,
                v.batch_number,
                v.vaccine_price,
                u.full_name         AS administered_by,
                v.notes
            FROM vaccinations v
            JOIN patients p         ON p.id = v.patient_id
            LEFT JOIN users u       ON u.id = v.administered_by_id
            WHERE {where}
            ORDER BY v.dose_date
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Prescriptions
    # ─────────────────────────────────────────────────────────────────────────

    async def get_prescriptions(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")
        sql = text(f"""
            SELECT
                rx.id,
                rx.patient_id,
                p.name              AS patient_name,
                rx.medication_name,
                rx.dosage,
                rx.frequency,
                rx.duration_months,
                rx.prescription_date,
                rx.start_date,
                rx.end_date,
                rx.is_active,
                rx.instructions,
                u.full_name         AS prescribed_by
            FROM prescriptions rx
            JOIN patients p         ON p.id = rx.patient_id
            LEFT JOIN users u       ON u.id = rx.prescribed_by_id
            WHERE {where}
            ORDER BY rx.prescription_date
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Medication schedules
    # ─────────────────────────────────────────────────────────────────────────

    async def get_medication_schedules(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")
        sql = text(f"""
            SELECT
                ms.id,
                ms.patient_id,
                p.name              AS patient_name,
                ms.medication_name,
                ms.scheduled_date,
                ms.quantity_purchased,
                ms.months_supply,
                ms.next_dose_due_date,
                ms.is_completed,
                ms.completed_date,
                ms.lab_review_scheduled,
                ms.lab_review_date,
                ms.lab_review_completed,
                ms.notes
            FROM medication_schedules ms
            JOIN patients p ON p.id = ms.patient_id
            WHERE {where}
            ORDER BY ms.scheduled_date
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Diagnoses
    # ─────────────────────────────────────────────────────────────────────────

    async def get_diagnoses(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")
        sql = text(f"""
            SELECT
                d.id,
                d.patient_id,
                p.name              AS patient_name,
                d.history,
                d.preliminary_diagnosis,
                d.actual_diagnosis,
                d.diagnosed_on,
                u.full_name         AS diagnosed_by
            FROM diagnoses d
            JOIN patients p         ON p.id = d.patient_id
            LEFT JOIN users u       ON u.id = d.diagnosed_by_id
            WHERE d.is_deleted = FALSE
              AND {where}
            ORDER BY d.diagnosed_on
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Reminders
    # ─────────────────────────────────────────────────────────────────────────

    async def get_reminders(self, filters: ReportFilters) -> List[Any]:
        where, params = _patient_where(filters, "p")
        sql = text(f"""
            SELECT
                r.id,
                r.patient_id,
                p.name          AS patient_name,
                p.phone         AS patient_phone,
                r.reminder_type,
                r.scheduled_date,
                r.status,
                r.sent_at,
                r.message
            FROM patient_reminders r
            JOIN patients p ON p.id = r.patient_id
            WHERE {where}
            ORDER BY r.scheduled_date
        """)
        return (await self.db.execute(sql, params)).all()

    # ─────────────────────────────────────────────────────────────────────────
    # Vaccine stock
    # ─────────────────────────────────────────────────────────────────────────

    async def get_vaccines(self) -> List[Any]:
        sql = text("""
            SELECT
                id,
                vaccine_name,
                price_per_dose,
                quantity,
                reserved_quantity,
                (quantity - reserved_quantity)  AS available_quantity,
                batch_number,
                is_published,
                created_at
            FROM vaccines
            ORDER BY vaccine_name
        """)
        return (await self.db.execute(sql)).all()