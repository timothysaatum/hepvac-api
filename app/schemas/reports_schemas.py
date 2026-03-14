"""
Schemas for the Reports / Data Export system.

All export endpoints accept a ReportFilters query object.
The caller selects which sheets to include via include_* flags.
If all include_* are False the server returns a 400.
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, model_validator


class ReportFilters(BaseModel):
    """
    Query parameters accepted by every export endpoint.

    Date filters apply to the primary entity's created_at / purchase_date
    where appropriate.
    """

    # ── Date window ────────────────────────────────────────────────────────
    date_from: Optional[date] = None
    date_to:   Optional[date] = None

    # ── Patient scope ──────────────────────────────────────────────────────
    patient_type:   Optional[str] = None   # "pregnant" | "regular"
    patient_status: Optional[str] = None   # "active" | "inactive" | "postpartum" | "completed"
    facility_id:    Optional[UUID] = None  # future multi-facility support

    # ── Sheet toggles ──────────────────────────────────────────────────────
    # Default True so a bare GET returns everything.
    include_patients:      bool = True
    include_pregnancies:   bool = True
    include_children:      bool = True
    include_transactions:  bool = True   # vaccine purchases + payments
    include_vaccinations:  bool = True   # individual dose records
    include_prescriptions: bool = True
    include_medications:   bool = True   # medication schedules
    include_diagnoses:     bool = True
    include_reminders:     bool = True
    include_stock:         bool = True   # vaccine master / stock

    @model_validator(mode="after")
    def at_least_one_sheet(self) -> "ReportFilters":
        flags = [
            self.include_patients, self.include_pregnancies, self.include_children,
            self.include_transactions, self.include_vaccinations,
            self.include_prescriptions, self.include_medications,
            self.include_diagnoses, self.include_reminders, self.include_stock,
        ]
        if not any(flags):
            raise ValueError("At least one sheet must be included in the export.")
        return self