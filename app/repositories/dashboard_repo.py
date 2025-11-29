from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, and_, extract, case
from decimal import Decimal

from app.models.patient_model import Patient, Vaccination, Payment
from app.models.vaccine_model import Vaccine, PatientVaccinePurchase
from app.models.user_model import User
from app.models.facility_model import Facility
from app.middlewares.device_trust import TrustedDevice


class DashboardRepository:
    """Repository for dashboard analytics queries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============= Overview Statistics =============
    async def get_overview_stats(self, facility_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        """Get dashboard overview statistics."""
        
        current_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_year_start = datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Build patient query
        patient_query = select(
            func.count(Patient.id).label('total'),
            func.sum(case((Patient.status == 'active', 1), else_=0)).label('active'),
            func.sum(case((Patient.patient_type == 'pregnant', 1), else_=0)).label('pregnant'),
            func.sum(case((Patient.patient_type == 'regular', 1), else_=0)).label('regular'),
        ).where(Patient.is_deleted == False)
        
        if facility_id:
            patient_query = patient_query.where(Patient.facility_id == facility_id)
        
        patient_result = await self.db.execute(patient_query)
        patient_stats = patient_result.first()
        
        # Vaccination stats
        vacc_query = select(
            func.count(Vaccination.id).label('total'),
            func.sum(case((Vaccination.created_at >= current_month_start, 1), else_=0)).label('this_month'),
            func.sum(case((Vaccination.created_at >= current_year_start, 1), else_=0)).label('this_year'),
        )
        
        if facility_id:
            vacc_query = vacc_query.join(Vaccination.patient).where(Patient.facility_id == facility_id)
        
        vacc_result = await self.db.execute(vacc_query)
        vacc_stats = vacc_result.first()
        
        # Revenue stats
        revenue_query = select(
            func.coalesce(func.sum(Payment.amount), 0).label('total'),
            func.coalesce(func.sum(case((Payment.created_at >= current_month_start, Payment.amount), else_=0)), 0).label('this_month'),
            func.coalesce(func.sum(case((Payment.created_at >= current_year_start, Payment.amount), else_=0)), 0).label('this_year'),
        )
        
        if facility_id:
            revenue_query = revenue_query.join(Payment.vaccine_purchase).join(PatientVaccinePurchase.patient).where(Patient.facility_id == facility_id)
        
        revenue_result = await self.db.execute(revenue_query)
        revenue_stats = revenue_result.first()
        
        # Outstanding balance
        balance_query = select(func.coalesce(func.sum(PatientVaccinePurchase.balance), 0))
        if facility_id:
            balance_query = balance_query.join(PatientVaccinePurchase.patient).where(Patient.facility_id == facility_id)
        
        balance_result = await self.db.execute(balance_query)
        outstanding_balance = balance_result.scalar() or 0
        
        # Vaccine purchases
        purchase_query = select(
            func.sum(case((PatientVaccinePurchase.is_active == True, 1), else_=0)).label('active'),
            func.sum(case((PatientVaccinePurchase.balance == 0, 1), else_=0)).label('completed'),
        )
        
        if facility_id:
            purchase_query = purchase_query.join(PatientVaccinePurchase.patient).where(Patient.facility_id == facility_id)
        
        purchase_result = await self.db.execute(purchase_query)
        purchase_stats = purchase_result.first()
        
        # Vaccine stock
        stock_query = select(
            func.count(Vaccine.id).label('total'),
            func.sum(case((Vaccine.quantity < 10, 1), else_=0)).label('low_stock'),
        )
        stock_result = await self.db.execute(stock_query)
        stock_stats = stock_result.first()
        
        # Device stats (all facilities for admin)
        device_query = select(
            func.sum(case((TrustedDevice.status == 'trusted', 1), else_=0)).label('trusted'),
            func.sum(case((TrustedDevice.status == 'pending', 1), else_=0)).label('pending'),
        )
        device_result = await self.db.execute(device_query)
        device_stats = device_result.first()
        
        return {
            'total_patients': patient_stats.total or 0,
            'active_patients': patient_stats.active or 0,
            'pregnant_patients': patient_stats.pregnant or 0,
            'regular_patients': patient_stats.regular or 0,
            'total_vaccinations': vacc_stats.total or 0,
            'vaccinations_this_month': vacc_stats.this_month or 0,
            'vaccinations_this_year': vacc_stats.this_year or 0,
            'total_revenue': revenue_stats.total or 0,
            'revenue_this_month': revenue_stats.this_month or 0,
            'revenue_this_year': revenue_stats.this_year or 0,
            'outstanding_balance': outstanding_balance,
            'active_vaccine_purchases': purchase_stats.active or 0,
            'completed_vaccine_purchases': purchase_stats.completed or 0,
            'low_stock_vaccines': stock_stats.low_stock or 0,
            'total_vaccines': stock_stats.total or 0,
            'trusted_devices': device_stats.trusted or 0,
            'pending_devices': device_stats.pending or 0,
        }

    # ============= Vaccine Usage Analytics =============
    async def get_vaccine_usage(
        self,
        facility_id: Optional[uuid.UUID] = None,
        year: Optional[int] = None,
        month: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Get vaccine usage statistics."""
        
        query = select(
            Vaccination.vaccine_name,
            func.count(Vaccination.id).label('total_doses'),
            func.count(func.distinct(Vaccination.patient_id)).label('unique_patients'),
            func.sum(Vaccination.vaccine_price).label('total_revenue'),
        ).group_by(Vaccination.vaccine_name)
        
        # Apply filters
        filters = []
        
        if facility_id:
            query = query.join(Vaccination.patient).where(Patient.facility_id == facility_id)
        
        if year:
            filters.append(extract('year', Vaccination.dose_date) == year)
        
        if month and year:
            filters.append(extract('month', Vaccination.dose_date) == month)
        
        if start_date:
            filters.append(Vaccination.dose_date >= start_date)
        
        if end_date:
            filters.append(Vaccination.dose_date <= end_date)
        
        if filters:
            query = query.where(and_(*filters))
        
        query = query.order_by(func.count(Vaccination.id).desc())
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return [
            {
                'vaccine_name': row.vaccine_name,
                'total_doses_administered': row.total_doses,
                'unique_patients': row.unique_patients,
                'total_revenue': row.total_revenue or 0,
            }
            for row in rows
        ]

    # ============= Revenue Analytics =============
    async def get_revenue_by_period(
        self,
        facility_id: Optional[uuid.UUID] = None,
        year: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get revenue breakdown by month and year."""
        
        query = select(
            extract('year', Payment.payment_date).label('year'),
            extract('month', Payment.payment_date).label('month'),
            func.sum(Payment.amount).label('total_revenue'),
            func.count(Payment.id).label('payment_count'),
        ).group_by(
            extract('year', Payment.payment_date),
            extract('month', Payment.payment_date),
        ).order_by(
            extract('year', Payment.payment_date).desc(),
            extract('month', Payment.payment_date).desc(),
        )
        
        if facility_id:
            query = query.join(Payment.vaccine_purchase).join(PatientVaccinePurchase.patient).where(Patient.facility_id == facility_id)
        
        filters = []
        if year:
            filters.append(extract('year', Payment.payment_date) == year)
        if start_date:
            filters.append(Payment.payment_date >= start_date)
        if end_date:
            filters.append(Payment.payment_date <= end_date)
        
        if filters:
            query = query.where(and_(*filters))
        
        result = await self.db.execute(query)
        rows = result.all()
        
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        return [{
                'year': int(row.year),
                'month': int(row.month),
                'month_name': month_names[int(row.month) - 1],
                'total_revenue': row.total_revenue or 0,
                'payment_count': row.payment_count,
                'average_payment': (row.total_revenue / row.payment_count) if row.payment_count > 0 else 0,
            }
            for row in rows]
        

    # ============= Facility Performance =============
    async def get_facility_performance(self) -> List[Dict[str, Any]]:
        """Get performance metrics for all facilities."""
        
        query = select(
            Facility.id,
            Facility.facility_name,
            func.count(func.distinct(Patient.id)).label('total_patients'),
            func.sum(case((Patient.status == 'active', 1), else_=0)).label('active_patients'),
            func.count(func.distinct(Vaccination.id)).label('total_vaccinations'),
            func.coalesce(func.sum(Payment.amount), 0).label('total_revenue'),
            func.coalesce(func.sum(PatientVaccinePurchase.balance), 0).label('outstanding_balance'),
            func.count(func.distinct(User.id)).label('staff_count'),
        ).outerjoin(
            Patient, Patient.facility_id == Facility.id
        ).outerjoin(
            Vaccination, Vaccination.patient_id == Patient.id
        ).outerjoin(
            PatientVaccinePurchase, PatientVaccinePurchase.patient_id == Patient.id
        ).outerjoin(
            Payment, Payment.vaccine_purchase_id == PatientVaccinePurchase.id
        ).outerjoin(
            User, User.facility_id == Facility.id
        ).group_by(
            Facility.id, Facility.facility_name
        ).order_by(
            func.coalesce(func.sum(Payment.amount), 0).desc()
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return [
            {
                'facility_id': str(row.id),
                'facility_name': row.facility_name,
                'total_patients': row.total_patients or 0,
                'active_patients': row.active_patients or 0,
                'total_vaccinations': row.total_vaccinations or 0,
                'total_revenue': row.total_revenue or 0,
                'outstanding_balance': row.outstanding_balance or 0,
                'average_revenue_per_patient': (row.total_revenue / row.total_patients) if row.total_patients > 0 else 0,
                'staff_count': row.staff_count or 0,
            }
            for row in rows
        ]

    # ============= Device Analytics =============
    async def get_device_analytics(self) -> Dict[str, Any]:
        """Get device access analytics."""
        
        # By status
        status_query = select(
            TrustedDevice.status,
            func.count(TrustedDevice.id).label('count'),
        ).group_by(TrustedDevice.status)
        
        status_result = await self.db.execute(status_query)
        by_status = [{'status': row.status, 'count': row.count} for row in status_result.all()]
        
        # By browser
        browser_query = select(
            TrustedDevice.browser,
            func.count(TrustedDevice.id).label('count'),
        ).group_by(TrustedDevice.browser).order_by(func.count(TrustedDevice.id).desc()).limit(5)
        
        browser_result = await self.db.execute(browser_query)
        by_browser = [{'browser': row.browser, 'count': row.count} for row in browser_result.all()]
        
        # By OS
        os_query = select(
            TrustedDevice.os,
            func.count(TrustedDevice.id).label('count'),
        ).group_by(TrustedDevice.os).order_by(func.count(TrustedDevice.id).desc()).limit(5)
        
        os_result = await self.db.execute(os_query)
        by_os = [{'os': row.os, 'count': row.count} for row in os_result.all()]
        
        # Recently approved (last 30 days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_query = select(func.count(TrustedDevice.id)).where(
            and_(
                TrustedDevice.approved_at >= thirty_days_ago,
                TrustedDevice.status == 'trusted'
            )
        )
        recent_result = await self.db.execute(recent_query)
        recently_approved = recent_result.scalar() or 0
        
        # Pending approval
        pending_query = select(func.count(TrustedDevice.id)).where(TrustedDevice.status == 'pending')
        pending_result = await self.db.execute(pending_query)
        pending_approval = pending_result.scalar() or 0
        
        # Total devices
        total_query = select(func.count(TrustedDevice.id))
        total_result = await self.db.execute(total_query)
        total_devices = total_result.scalar() or 0
        
        return {
            'total_devices': total_devices,
            'by_status': by_status,
            'by_browser': by_browser,
            'by_os': by_os,
            'recently_approved': recently_approved,
            'pending_approval': pending_approval,
        }

    # ============= Vaccination Trends =============
    async def get_vaccination_trends(
        self,
        facility_id: Optional[uuid.UUID] = None,
        year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get vaccination trends over time."""
        
        query = select(
            extract('year', Vaccination.dose_date).label('year'),
            extract('month', Vaccination.dose_date).label('month'),
            func.count(Vaccination.id).label('total_vaccinations'),
            func.sum(case((Vaccination.dose_number == '1st dose', 1), else_=0)).label('first_dose'),
            func.sum(case((Vaccination.dose_number == '2nd dose', 1), else_=0)).label('second_dose'),
            func.sum(case((Vaccination.dose_number == '3rd dose', 1), else_=0)).label('third_dose'),
            func.count(func.distinct(Vaccination.patient_id)).label('unique_patients'),
        ).group_by(
            extract('year', Vaccination.dose_date),
            extract('month', Vaccination.dose_date),
        ).order_by(
            extract('year', Vaccination.dose_date).desc(),
            extract('month', Vaccination.dose_date).desc(),
        )
        
        if facility_id:
            query = query.join(Vaccination.patient).where(Patient.facility_id == facility_id)
        
        if year:
            query = query.where(extract('year', Vaccination.dose_date) == year)
        
        result = await self.db.execute(query)
        rows = result.all()
        
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        return [
            {
                'year': int(row.year),
                'month': int(row.month),
                'month_name': month_names[int(row.month) - 1],
                'total_vaccinations': row.total_vaccinations,
                'first_dose': row.first_dose,
                'second_dose': row.second_dose,
                'third_dose': row.third_dose,
                'unique_patients': row.unique_patients,
            }
            for row in rows
        ]