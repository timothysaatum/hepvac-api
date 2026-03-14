"""
analytics_service.py

IMPORTANT: asyncio.gather() is intentionally NOT used here.
SQLAlchemy's AsyncSession provisions a single connection per transaction.
Concurrent coroutines sharing the same session race on that connection
and raise:
  InvalidRequestError: This session is provisioning a new connection;
  concurrent operations are not permitted.

All four repo calls must be awaited one at a time.
"""

from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics_repo import AnalyticsRepo
from app.schemas.analytics_schemas import (
    AcquisitionTrendSchema,
    DashboardSummarySchema,
    RevenueTrendSchema,
    UpcomingDeliverySchema,
)


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = AnalyticsRepo(db)

    async def get_dashboard_summary(self) -> DashboardSummarySchema:
        # Sequential — do NOT convert these to asyncio.gather()
        patients        = await self._repo.get_patient_counts()
        financials      = await self._repo.get_financial_summary()
        dose_completion = await self._repo.get_dose_completion_by_vaccine()
        clinical        = await self._repo.get_clinical_summary()

        return DashboardSummarySchema(
            patients=patients,
            financials=financials,
            dose_completion_by_vaccine=dose_completion,
            clinical=clinical,
        )

    async def get_revenue_trend(self, days: int = 30) -> RevenueTrendSchema:
        series = await self._repo.get_revenue_trend(days)
        return RevenueTrendSchema(days=days, series=series)

    async def get_acquisition_trend(self, days: int = 30) -> AcquisitionTrendSchema:
        series = await self._repo.get_acquisition_trend(days)
        return AcquisitionTrendSchema(days=days, series=series)

    async def get_upcoming_deliveries(
        self, days_ahead: int = 30
    ) -> List[UpcomingDeliverySchema]:
        return await self._repo.get_upcoming_deliveries(days_ahead)