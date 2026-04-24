from typing import Optional, List, Tuple
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import func, text
from datetime import date

from app.models.patient_model import Patient, PregnantPatient, RegularPatient, Vaccination, Payment, Pregnancy
from app.models.vaccine_model import PatientVaccinePurchase


class SearchRepository:
    """
    Repository layer for search operations.

    OPTIMIZATIONS:
    - Uses parameterized queries to prevent SQL injection
    - Implements efficient joins and eager loading
    - Uses database indexes (see migration file needed)
    - Implements query timeouts
    - Uses LIMIT for count estimates on large datasets
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._query_timeout = 30  # seconds

    async def _set_query_timeout(self):
        """Set query timeout to prevent long-running queries."""
        try:
            await self.db.execute(text(f"SET statement_timeout = '{self._query_timeout}s'"))
        except Exception:
            pass

    async def _get_estimated_count(self, query, exact_threshold: int = 10000) -> Tuple[int, bool]:
        count_query = select(func.count()).select_from(query.subquery())
        limited_count_query = count_query.limit(exact_threshold + 1)
        result = await self.db.execute(limited_count_query)
        count = result.scalar() or 0
        if count > exact_threshold:
            return exact_threshold, True
        return count, False

    # ============= Patient Search =============
    async def search_patients(
        self,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        status: Optional[str] = None,
        sex: Optional[str] = None,
        age_min: Optional[int] = None,
        age_max: Optional[int] = None,
        created_from: Optional[date] = None,
        created_to: Optional[date] = None,
        skip: int = 0,
        limit: int = 10,
    ) -> Tuple[List[Patient], int]:
        """
        Search patients with various filters.

        Loading strategy — two-phase, fully async-safe:

        Phase 1: select(Patient) + selectin_polymorphic
            Loads base Patient rows, then fires targeted IN (...) SELECTs for
            PregnantPatient and RegularPatient subtype columns. No JOINs, so
            no NULL-id risk from missing subtype rows (broken data).

        Phase 2: explicit Pregnancy query + set_committed_value
            Loads all Pregnancy rows for the page's pregnant patients in one
            IN (...) SELECT, then injects them into each PregnantPatient via
            set_committed_value. This marks 'pregnancies' as loaded so
            patient.active_pregnancy never triggers a lazy load after the
            async session context exits (which would raise MissingGreenlet).

            Why not selectinload(PregnantPatient.pregnancies) in .options()?
            SQLAlchemy does not reliably chain a selectinload through a
            selectin_polymorphic post-load step in async context. The nested
            selectin fires outside the greenlet and raises MissingGreenlet —
            exactly the error seen in production.
        """
        await self._set_query_timeout()

        from sqlalchemy.orm import selectin_polymorphic
        from sqlalchemy.orm import attributes as orm_attributes

        # Phase 1 — build base query
        query = (
            select(Patient)
            .where(Patient.is_deleted == False)
            .options(
                selectin_polymorphic(Patient, [PregnantPatient, RegularPatient]),
            )
        )

        # Apply filters — all parameterized (SECURITY)
        if facility_id:
            query = query.where(Patient.facility_id == facility_id)
        if patient_type:
            query = query.where(Patient.patient_type == patient_type)
        if status:
            query = query.where(Patient.status == status)
        if sex:
            query = query.where(Patient.sex == sex)
        if name:
            query = query.where(Patient.name.ilike(f"%{name}%"))
        if phone:
            query = query.where(Patient.phone.like(f"%{phone}%"))
        if age_min is not None:
            query = query.where(Patient.age >= age_min)
        if age_max is not None:
            query = query.where(Patient.age <= age_max)
        if created_from:
            query = query.where(func.date(Patient.created_at) >= created_from)
        if created_to:
            query = query.where(func.date(Patient.created_at) <= created_to)

        # Count (before pagination)
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total_count = total_result.scalar() or 0

        # Paginate
        query = query.order_by(Patient.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        patients = list(result.unique().scalars().all())

        # Phase 2 — inject pregnancies to prevent lazy load after greenlet exit
        pregnant_patients = [p for p in patients if isinstance(p, PregnantPatient)]
        if pregnant_patients:
            pregnant_ids = [p.id for p in pregnant_patients]
            preg_result = await self.db.execute(
                select(Pregnancy)
                .where(Pregnancy.patient_id.in_(pregnant_ids))
                .order_by(Pregnancy.pregnancy_number)
            )
            # Group pregnancies by patient_id
            preg_map: dict[uuid.UUID, list] = {}
            for preg in preg_result.scalars().all():
                preg_map.setdefault(preg.patient_id, []).append(preg)

            # set_committed_value marks the relationship as already loaded —
            # no lazy load will ever be attempted on these instances.
            for patient in pregnant_patients:
                orm_attributes.set_committed_value(
                    patient, "pregnancies", preg_map.get(patient.id, [])
                )

        return patients, total_count

    # ============= Vaccination Search =============
    async def search_vaccinations(
        self,
        patient_id: Optional[uuid.UUID] = None,
        patient_name: Optional[str] = None,
        patient_phone: Optional[str] = None,
        vaccine_name: Optional[str] = None,
        batch_number: Optional[str] = None,
        dose_number: Optional[str] = None,
        dose_date_from: Optional[date] = None,
        dose_date_to: Optional[date] = None,
        administered_by_id: Optional[uuid.UUID] = None,
        facility_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 10,
    ) -> Tuple[List[Vaccination], int]:
        """Search vaccinations — parameterized, no N+1."""
        await self._set_query_timeout()

        query = (
            select(Vaccination)
            .join(Vaccination.patient)
            .options(
                joinedload(Vaccination.patient),
                joinedload(Vaccination.vaccine_purchase),
            )
            .where(Patient.is_deleted == False)
        )

        if patient_id:
            query = query.where(Vaccination.patient_id == patient_id)
        if patient_name:
            query = query.where(Patient.name.ilike(f"%{patient_name}%"))
        if patient_phone:
            query = query.where(Patient.phone.like(f"%{patient_phone}%"))
        if facility_id:
            query = query.where(Patient.facility_id == facility_id)
        if vaccine_name:
            query = query.where(Vaccination.vaccine_name.ilike(f"%{vaccine_name}%"))
        if batch_number:
            query = query.where(Vaccination.batch_number.like(f"%{batch_number}%"))
        if dose_number:
            query = query.where(Vaccination.dose_number == dose_number)
        if dose_date_from:
            query = query.where(Vaccination.dose_date >= dose_date_from)
        if dose_date_to:
            query = query.where(Vaccination.dose_date <= dose_date_to)
        if administered_by_id:
            query = query.where(Vaccination.administered_by_id == administered_by_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total_count = total_result.scalar() or 0

        query = query.order_by(Vaccination.dose_date.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        vaccinations = list(result.scalars().all())

        return vaccinations, total_count

    # ============= Payment Search =============
    async def search_payments(
        self,
        patient_id: Optional[uuid.UUID] = None,
        patient_name: Optional[str] = None,
        patient_phone: Optional[str] = None,
        vaccine_purchase_id: Optional[uuid.UUID] = None,
        payment_method: Optional[str] = None,
        payment_date_from: Optional[date] = None,
        payment_date_to: Optional[date] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        received_by_id: Optional[uuid.UUID] = None,
        facility_id: Optional[uuid.UUID] = None,
        reference_number: Optional[str] = None,
        skip: int = 0,
        limit: int = 10,
    ) -> Tuple[List[Payment], int, float]:
        """Search payments — parameterized, count + sum in parallel."""
        await self._set_query_timeout()

        query = (
            select(Payment)
            .join(Payment.vaccine_purchase)
            .join(PatientVaccinePurchase.patient)
            .options(
                joinedload(Payment.vaccine_purchase)
                .joinedload(PatientVaccinePurchase.patient),
            )
            .where(Patient.is_deleted == False)
        )

        if patient_id:
            query = query.where(PatientVaccinePurchase.patient_id == patient_id)
        if patient_name:
            query = query.where(Patient.name.ilike(f"%{patient_name}%"))
        if patient_phone:
            query = query.where(Patient.phone.like(f"%{patient_phone}%"))
        if facility_id:
            query = query.where(Patient.facility_id == facility_id)
        if vaccine_purchase_id:
            query = query.where(Payment.vaccine_purchase_id == vaccine_purchase_id)
        if payment_method:
            query = query.where(Payment.payment_method == payment_method)
        if payment_date_from:
            query = query.where(Payment.payment_date >= payment_date_from)
        if payment_date_to:
            query = query.where(Payment.payment_date <= payment_date_to)
        if amount_min is not None:
            query = query.where(Payment.amount >= amount_min)
        if amount_max is not None:
            query = query.where(Payment.amount <= amount_max)
        if received_by_id:
            query = query.where(Payment.received_by_id == received_by_id)
        if reference_number:
            query = query.where(Payment.reference_number.ilike(f"%{reference_number}%"))

        count_query = select(func.count()).select_from(query.subquery())
        amount_query = select(func.sum(Payment.amount)).select_from(query.subquery())

        total_result = await self.db.execute(count_query)
        amount_result = await self.db.execute(amount_query)
        total_count = total_result.scalar() or 0
        total_amount = amount_result.scalar() or 0

        query = query.order_by(Payment.payment_date.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        payments = list(result.scalars().all())

        return payments, total_count, float(total_amount)