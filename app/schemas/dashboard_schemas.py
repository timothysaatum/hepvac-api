from datetime import date
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel


# ============= Dashboard Overview Schemas =============
class DashboardOverview(BaseModel):
    """Main dashboard overview statistics."""
    
    total_patients: int
    active_patients: int
    pregnant_patients: int
    regular_patients: int
    
    total_vaccinations: int
    vaccinations_this_month: int
    vaccinations_this_year: int
    
    total_revenue: Decimal
    revenue_this_month: Decimal
    revenue_this_year: Decimal
    outstanding_balance: Decimal
    
    active_vaccine_purchases: int
    completed_vaccine_purchases: int
    
    low_stock_vaccines: int
    total_vaccines: int
    
    trusted_devices: int
    pending_devices: int
    
    model_config = {"from_attributes": True}


# ============= Vaccine Usage Schemas =============
class VaccineUsageItem(BaseModel):
    vaccine_id: Optional[str] = None
    vaccine_name: str
    total_doses_administered: Optional[int] = 0
    total_purchases: Optional[int] = 0
    total_revenue: Optional[Decimal] = Decimal('0.00')
    unique_patients: Optional[int] = 0


class VaccineUsageFilters(BaseModel):
    """Filters for vaccine usage analytics."""
    
    facility_id: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None  # 1-12
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    model_config = {"from_attributes": True}


class VaccineUsageResponse(BaseModel):
    """Response for vaccine usage analytics."""
    
    items: List[VaccineUsageItem]
    total_doses: int
    total_revenue: Decimal
    period: str  # Description of the period (e.g., "January 2024", "2024", "All Time")
    
    model_config = {"from_attributes": True}


# ============= Revenue Analytics Schemas =============
class RevenueByMonth(BaseModel):
    """Monthly revenue breakdown."""
    
    year: int
    month: int
    month_name: str
    total_revenue: Decimal
    payment_count: int
    average_payment: Decimal
    
    model_config = {"from_attributes": True}


class RevenueByYear(BaseModel):
    """Yearly revenue breakdown."""
    
    year: int
    total_revenue: Decimal
    payment_count: int
    monthly_breakdown: List[RevenueByMonth]
    
    model_config = {"from_attributes": True}


class RevenueFilters(BaseModel):
    """Filters for revenue analytics."""
    
    facility_id: Optional[str] = None
    year: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    model_config = {"from_attributes": True}


class RevenueAnalyticsResponse(BaseModel):
    """Response for revenue analytics."""
    
    total_revenue: Decimal
    yearly_breakdown: List[RevenueByYear]
    payment_methods: List[dict]  # [{"method": "cash", "total": 1000, "count": 50}]
    
    model_config = {"from_attributes": True}


# ============= Facility Performance Schemas =============
class FacilityPerformanceItem(BaseModel):
    """Individual facility performance metrics."""
    
    facility_id: str
    facility_name: str
    total_patients: int
    active_patients: int
    total_vaccinations: int
    total_revenue: Decimal
    outstanding_balance: Decimal
    average_revenue_per_patient: Decimal
    staff_count: int
    
    model_config = {"from_attributes": True}


class FacilityPerformanceResponse(BaseModel):
    """Response for facility performance analytics."""
    
    items: List[FacilityPerformanceItem]
    total_revenue_all_facilities: Decimal
    top_performing_facility: Optional[FacilityPerformanceItem] = None
    
    model_config = {"from_attributes": True}


# ============= Patient Analytics Schemas =============
class PatientGrowthItem(BaseModel):
    """Patient growth by month."""
    
    year: int
    month: int
    month_name: str
    new_patients: int
    cumulative_patients: int
    pregnant_patients: int
    regular_patients: int
    
    model_config = {"from_attributes": True}


class PatientAnalyticsResponse(BaseModel):
    """Response for patient analytics."""
    
    total_patients: int
    active_patients: int
    growth_data: List[PatientGrowthItem]
    patients_by_status: List[dict]  # [{"status": "active", "count": 100}]
    average_age: float
    
    model_config = {"from_attributes": True}


# ============= Device Analytics Schemas =============
class DeviceAnalyticsItem(BaseModel):
    """Device access statistics."""
    
    status: str  # trusted, pending, blocked, suspicious
    count: int
    
    model_config = {"from_attributes": True}


class DeviceByBrowser(BaseModel):
    """Devices grouped by browser."""
    
    browser: str
    count: int
    
    model_config = {"from_attributes": True}


class DeviceByOS(BaseModel):
    """Devices grouped by operating system."""
    
    os: str
    count: int
    
    model_config = {"from_attributes": True}


class DeviceAnalyticsResponse(BaseModel):
    """Response for device analytics."""
    
    total_devices: int
    by_status: List[DeviceAnalyticsItem]
    by_browser: List[DeviceByBrowser]
    by_os: List[DeviceByOS]
    recently_approved: int  # Last 30 days
    pending_approval: int
    
    model_config = {"from_attributes": True}


# ============= Vaccination Trends Schemas =============
class VaccinationTrendItem(BaseModel):
    """Vaccination trend by period."""
    
    year: int
    month: int
    month_name: str
    total_vaccinations: int
    first_dose: int
    second_dose: int
    third_dose: int
    unique_patients: int
    
    model_config = {"from_attributes": True}


class VaccinationTrendResponse(BaseModel):
    """Response for vaccination trends."""
    
    items: List[VaccinationTrendItem]
    total_vaccinations: int
    average_per_month: float
    
    model_config = {"from_attributes": True}