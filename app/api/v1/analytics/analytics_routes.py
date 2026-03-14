"""
Analytics routes.

Prefix : /analytics
Auth   : staff_or_admin (same as all patient routes)

Endpoints
---------
GET /analytics/summary              → DashboardSummarySchema
GET /analytics/revenue-trend        → RevenueTrendSchema        ?days=7|30
GET /analytics/acquisition          → AcquisitionTrendSchema    ?days=7|30
GET /analytics/upcoming-deliveries  → List[UpcomingDeliverySchema] ?days_ahead=30

Registration (add to app/main.py):
    from app.api.routes.analytics_routes import router as analytics_router
    app.include_router(analytics_router, prefix="/api/v1")
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.core.utils import logger
from app.models.user_model import User
from app.schemas.analytics_schemas import (
    AcquisitionTrendSchema,
    DashboardSummarySchema,
    RevenueTrendSchema,
    UpcomingDeliverySchema,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ─────────────────────────────────────────────────────────────────────────────
# Summary  (all KPIs in one shot — used by the dashboard KPI strip)
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=DashboardSummarySchema,
    summary="Dashboard KPI summary",
    description=(
        "Returns all aggregate metrics needed for the facility dashboard: "
        "patient counts by type/status, financial totals, dose completion "
        "rates by vaccine, and clinical alerts. Runs four parallel DB queries."
    ),
)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
) -> DashboardSummarySchema:
    service = AnalyticsService(db)
    try:
        summary = await service.get_dashboard_summary()

        logger.log_info({
            "event": "analytics_summary_fetched",
            "user_id": str(current_user.id),
            "facility_id": str(current_user.facility_id),
        })

        return summary

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "analytics_summary_error",
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while computing the dashboard summary.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Revenue trend
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/revenue-trend",
    response_model=RevenueTrendSchema,
    summary="Daily revenue time series",
    description=(
        "Returns daily vaccine-purchase payment totals for the last `days` days. "
        "Only days with at least one sale are included; the frontend fills in zeros."
    ),
)
async def get_revenue_trend(
    days: int = Query(default=30, ge=7, le=365, description="Lookback window in days"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
) -> RevenueTrendSchema:
    service = AnalyticsService(db)
    try:
        return await service.get_revenue_trend(days)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "revenue_trend_error",
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching revenue trend data.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Patient acquisition trend
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/acquisition",
    response_model=AcquisitionTrendSchema,
    summary="Daily patient acquisition time series",
    description=(
        "Returns daily new patient registration counts (split by type) for the "
        "last `days` days. Only days with at least one registration are included."
    ),
)
async def get_acquisition_trend(
    days: int = Query(default=30, ge=7, le=365, description="Lookback window in days"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
) -> AcquisitionTrendSchema:
    service = AnalyticsService(db)
    try:
        return await service.get_acquisition_trend(days)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "acquisition_trend_error",
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching acquisition trend data.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Upcoming deliveries
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/upcoming-deliveries",
    response_model=List[UpcomingDeliverySchema],
    summary="Patients with deliveries due within N days (+ overdue)",
    description=(
        "Returns pregnant patients whose active pregnancy EDD falls within "
        "`days_ahead` days, plus any already-overdue patients. "
        "Ordered by EDD ascending (most urgent first)."
    ),
)
async def get_upcoming_deliveries(
    days_ahead: int = Query(
        default=30, ge=1, le=90, description="How many days ahead to look"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
) -> List[UpcomingDeliverySchema]:
    service = AnalyticsService(db)
    try:
        return await service.get_upcoming_deliveries(days_ahead)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error({
            "event": "upcoming_deliveries_error",
            "error": str(e),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching upcoming deliveries.",
        )