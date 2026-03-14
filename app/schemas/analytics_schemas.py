"""
Schemas for analytics / dashboard aggregate endpoints.
All monetary values are Decimal to avoid IEEE-754 drift.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Patient counts
# ─────────────────────────────────────────────────────────────────────────────


class PatientCountsSchema(BaseModel):
    total: int
    pregnant: int
    regular: int
    active: int
    inactive: int
    postpartum: int
    completed: int
    new_this_month: int
    new_last_month: int


# ─────────────────────────────────────────────────────────────────────────────
# Revenue / financial
# ─────────────────────────────────────────────────────────────────────────────


class PaymentStatusCountsSchema(BaseModel):
    completed: int
    partial: int
    pending: int
    total_purchases: int


class FinancialSummarySchema(BaseModel):
    total_revenue: Decimal = Field(decimal_places=2)
    total_outstanding: Decimal = Field(decimal_places=2)
    month_revenue: Decimal = Field(decimal_places=2)
    last_month_revenue: Decimal = Field(decimal_places=2)
    total_doses: int
    administered_doses: int
    payment_status_counts: PaymentStatusCountsSchema


# ─────────────────────────────────────────────────────────────────────────────
# Dose completion (per vaccine)
# ─────────────────────────────────────────────────────────────────────────────


class VaccineDoseCompletionSchema(BaseModel):
    vaccine_name: str
    total_doses: int
    administered_doses: int
    completion_rate: float  # 0-100


# ─────────────────────────────────────────────────────────────────────────────
# Clinical outcomes
# ─────────────────────────────────────────────────────────────────────────────


class HepBResultCountsSchema(BaseModel):
    positive: int
    negative: int
    indeterminate: int
    untested: int


class ClinicalSummarySchema(BaseModel):
    upcoming_deliveries_30d: int
    overdue_deliveries: int
    checkups_pending: int
    checkups_completed: int
    hep_b_results: HepBResultCountsSchema


# ─────────────────────────────────────────────────────────────────────────────
# Combined summary (single endpoint for KPI strip)
# ─────────────────────────────────────────────────────────────────────────────


class DashboardSummarySchema(BaseModel):
    patients: PatientCountsSchema
    financials: FinancialSummarySchema
    dose_completion_by_vaccine: List[VaccineDoseCompletionSchema]
    clinical: ClinicalSummarySchema


# ─────────────────────────────────────────────────────────────────────────────
# Time-series points
# ─────────────────────────────────────────────────────────────────────────────


class RevenueDaySchema(BaseModel):
    date: date
    revenue: Decimal = Field(decimal_places=2)
    sales_count: int


class AcquisitionDaySchema(BaseModel):
    date: date
    pregnant: int
    regular: int
    total: int


class RevenueTrendSchema(BaseModel):
    days: int
    series: List[RevenueDaySchema]


class AcquisitionTrendSchema(BaseModel):
    days: int
    series: List[AcquisitionDaySchema]


# ─────────────────────────────────────────────────────────────────────────────
# Upcoming deliveries
# ─────────────────────────────────────────────────────────────────────────────


class UpcomingDeliverySchema(BaseModel):
    patient_id: UUID
    name: str
    phone: str
    expected_delivery_date: date
    days_until_delivery: int  # negative = overdue

    model_config = {"from_attributes": True}