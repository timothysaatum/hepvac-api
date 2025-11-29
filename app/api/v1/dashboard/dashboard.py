import traceback
import uuid
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.dashboard_schemas import (
    DashboardOverview,
    VaccineUsageResponse,
    VaccineUsageItem,
    RevenueAnalyticsResponse,
    RevenueByMonth,
    RevenueByYear,
    FacilityPerformanceResponse,
    FacilityPerformanceItem,
    DeviceAnalyticsResponse,
    VaccinationTrendResponse,
    VaccinationTrendItem,
)
from app.repositories.dashboard_repo import DashboardRepository
from app.core.utils import logger


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ============= Dashboard Overview =============
@router.get(
    "/overview",
    response_model=DashboardOverview,
)
async def get_dashboard_overview(
    facility_id: Optional[uuid.UUID] = Query(None, description="Filter by facility (admin only)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get dashboard overview statistics.
    
    Returns key metrics including:
    - Patient counts (total, active, by type)
    - Vaccination statistics
    - Revenue metrics
    - Vaccine purchases status
    - Stock levels
    - Device access stats
    """
    repo = DashboardRepository(db)
    
    try:
        # Non-admin users can only see their facility
        if not any(role.name.lower() == 'admin' for role in current_user.roles):
            facility_id = current_user.facility_id
        
        stats = await repo.get_overview_stats(facility_id)
        
        logger.log_info({
            "event": "dashboard_overview_fetched",
            "facility_id": str(facility_id) if facility_id else "all",
            "user_id": str(current_user.id),
        })
        
        return DashboardOverview(**stats)
    
    except Exception as e:
        logger.log_error({
            "event": "dashboard_overview_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "user_id": str(current_user.id),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching dashboard overview",
        )


# ============= Vaccine Usage Analytics =============
@router.get(
    "/vaccine-usage",
    response_model=VaccineUsageResponse,
)
async def get_vaccine_usage(
    facility_id: Optional[uuid.UUID] = Query(None),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get vaccine usage analytics.
    
    Shows which vaccines are most commonly administered,
    with filtering by time period and facility.
    """
    repo = DashboardRepository(db)
    
    try:
        # Non-admin users can only see their facility
        if not any(role.name.lower() == 'admin' for role in current_user.roles):
            facility_id = current_user.facility_id
        
        items = await repo.get_vaccine_usage(facility_id, year, month, start_date, end_date)
        
        # Calculate totals
        total_doses = sum(item['total_doses_administered'] for item in items)
        total_revenue = sum(item['total_revenue'] for item in items)
        
        # Determine period description
        if year and month:
            month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                          'July', 'August', 'September', 'October', 'November', 'December']
            period = f"{month_names[month-1]} {year}"
        elif year:
            period = str(year)
        elif start_date and end_date:
            period = f"{start_date} to {end_date}"
        else:
            period = "All Time"
        
        logger.log_info({
            "event": "vaccine_usage_fetched",
            "period": period,
            "total_doses": total_doses,
            "user_id": str(current_user.id),
        })
        
        return VaccineUsageResponse(
            items=[VaccineUsageItem(**item) for item in items],
            total_doses=total_doses,
            total_revenue=total_revenue,
            period=period,
        )
    
    except Exception as e:
        logger.log_error({
            "event": "vaccine_usage_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching vaccine usage data",
        )


# ============= Revenue Analytics =============
@router.get(
    "/revenue",
    response_model=RevenueAnalyticsResponse,
)
async def get_revenue_analytics(
    facility_id: Optional[uuid.UUID] = Query(None),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get revenue analytics with monthly breakdown.
    
    Can be filtered by facility, year, or date range.
    """
    repo = DashboardRepository(db)
    
    try:
        # Non-admin users can only see their facility
        if not any(role.name.lower() == 'admin' for role in current_user.roles):
            facility_id = current_user.facility_id
        
        monthly_data = await repo.get_revenue_by_period(facility_id, year, start_date, end_date)
        
        # Group by year
        yearly_breakdown = {}
        for item in monthly_data:
            year_key = item['year']
            if year_key not in yearly_breakdown:
                yearly_breakdown[year_key] = {
                    'year': year_key,
                    'total_revenue': 0,
                    'payment_count': 0,
                    'monthly_breakdown': []
                }
            
            yearly_breakdown[year_key]['total_revenue'] += item['total_revenue']
            yearly_breakdown[year_key]['payment_count'] += item['payment_count']
            yearly_breakdown[year_key]['monthly_breakdown'].append(RevenueByMonth(**item))
        
        total_revenue = sum(y['total_revenue'] for y in yearly_breakdown.values())
        
        logger.log_info({
            "event": "revenue_analytics_fetched",
            "total_revenue": float(total_revenue),
            "user_id": str(current_user.id),
        })
        
        return RevenueAnalyticsResponse(
            total_revenue=total_revenue,
            yearly_breakdown=[RevenueByYear(**y) for y in yearly_breakdown.values()],
            payment_methods=[],  # Can be extended later
        )
    
    except Exception as e:
        logger.log_error({
            "event": "revenue_analytics_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching revenue analytics",
        )


# ============= Facility Performance =============
@router.get(
    "/facility-performance",
    response_model=FacilityPerformanceResponse,
)
async def get_facility_performance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get performance metrics for all facilities.
    
    Admin only. Shows which facilities are performing best.
    """
    repo = DashboardRepository(db)
    
    try:
        # Only admins can see all facilities
        if not any(role.name.lower() == 'admin' for role in current_user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can view facility performance",
            )
        
        items = await repo.get_facility_performance()
        
        total_revenue = sum(item['total_revenue'] for item in items)
        top_facility = items[0] if items else None
        
        logger.log_info({
            "event": "facility_performance_fetched",
            "facility_count": len(items),
            "user_id": str(current_user.id),
        })
        
        return FacilityPerformanceResponse(
            items=[FacilityPerformanceItem(**item) for item in items],
            total_revenue_all_facilities=total_revenue,
            top_performing_facility=FacilityPerformanceItem(**top_facility) if top_facility else None,
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.log_error({
            "event": "facility_performance_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching facility performance",
        )


# ============= Device Analytics =============
@router.get(
    "/devices",
    response_model=DeviceAnalyticsResponse,
)
async def get_device_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get device access analytics.
    
    Shows device status, browsers, and operating systems.
    """
    repo = DashboardRepository(db)
    
    try:
        data = await repo.get_device_analytics()
        
        logger.log_info({
            "event": "device_analytics_fetched",
            "total_devices": data['total_devices'],
            "user_id": str(current_user.id),
        })
        
        return DeviceAnalyticsResponse(**data)
    
    except Exception as e:
        logger.log_error({
            "event": "device_analytics_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching device analytics",
        )


# ============= Vaccination Trends =============
@router.get(
    "/vaccination-trends",
    response_model=VaccinationTrendResponse,
)
async def get_vaccination_trends(
    facility_id: Optional[uuid.UUID] = Query(None),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get vaccination trends over time.
    
    Shows monthly vaccination counts with dose breakdown.
    """
    repo = DashboardRepository(db)
    
    try:
        # Non-admin users can only see their facility
        if not any(role.name.lower() == 'admin' for role in current_user.roles):
            facility_id = current_user.facility_id
        
        items = await repo.get_vaccination_trends(facility_id, year)
        
        total_vaccinations = sum(item['total_vaccinations'] for item in items)
        average_per_month = total_vaccinations / len(items) if items else 0
        
        logger.log_info({
            "event": "vaccination_trends_fetched",
            "total_vaccinations": total_vaccinations,
            "user_id": str(current_user.id),
        })
        
        return VaccinationTrendResponse(
            items=[VaccinationTrendItem(**item) for item in items],
            total_vaccinations=total_vaccinations,
            average_per_month=average_per_month,
        )
    
    except Exception as e:
        logger.log_error({
            "event": "vaccination_trends_error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching vaccination trends",
        )