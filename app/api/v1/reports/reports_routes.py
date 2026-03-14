"""
Report routes.

Prefix : /reports
Auth   : staff_or_admin

Registration (add to app/main.py or app/api/v1/__init__.py):
    from app.api.routes.report_routes import router as report_router
    app.include_router(report_router, prefix="/api/v1")

Single endpoint:
    GET /reports/export   →  application/vnd.openxmlformats…  (.xlsx download)

All filter params are query parameters so the URL is bookmarkable and
the frontend can trigger it with a plain <a href> or window.open() call.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.core.utils import logger
from app.models.user_model import User
from app.schemas.reports_schemas import ReportFilters
from app.services.reports_service import ReportService


router = APIRouter(prefix="/reports", tags=["reports"])

_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/export",
    summary="Export facility data to Excel",
    description=(
        "Builds a multi-sheet .xlsx workbook with the selected data categories "
        "and returns it as a file download.  Use the include_* flags to select "
        "which sheets appear in the export. All filters are optional — omitting "
        "them returns all records."
    ),
    responses={
        200: {
            "description": "Excel workbook download",
            "content": {_MIME: {}},
        }
    },
)
async def export_report(
    # ── Date filters ──────────────────────────────────────────────────────
    date_from: Optional[str] = Query(
        default=None,
        description="ISO date (YYYY-MM-DD). Filter records created on/after this date.",
    ),
    date_to: Optional[str] = Query(
        default=None,
        description="ISO date (YYYY-MM-DD). Filter records created on/before this date.",
    ),
    # ── Patient scope ──────────────────────────────────────────────────────
    patient_type: Optional[str] = Query(
        default=None,
        description="Filter patients by type: 'pregnant' or 'regular'.",
    ),
    patient_status: Optional[str] = Query(
        default=None,
        description="Filter patients by status: 'active', 'inactive', 'postpartum', 'completed'.",
    ),
    facility_id: Optional[UUID] = Query(
        default=None,
        description="Scope export to a specific facility UUID.",
    ),
    # ── Sheet toggles ──────────────────────────────────────────────────────
    include_patients:      bool = Query(default=True),
    include_pregnancies:   bool = Query(default=True),
    include_children:      bool = Query(default=True),
    include_transactions:  bool = Query(default=True),
    include_vaccinations:  bool = Query(default=True),
    include_prescriptions: bool = Query(default=True),
    include_medications:   bool = Query(default=True),
    include_diagnoses:     bool = Query(default=True),
    include_reminders:     bool = Query(default=True),
    include_stock:         bool = Query(default=True),
    # ── Auth / DB ─────────────────────────────────────────────────────────
    current_user: User         = Depends(require_staff_or_admin()),
db: AsyncSession = Depends(get_db),
) -> StreamingResponse:

    # ── Parse date strings ────────────────────────────────────────────────
    from datetime import date as _date

    def _parse_date(s: Optional[str], field: str) -> Optional[_date]:
        if not s:
            return None
        try:
            return _date.fromisoformat(s)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid {field}: expected YYYY-MM-DD, got '{s}'.",
            )

    parsed_from = _parse_date(date_from, "date_from")
    parsed_to   = _parse_date(date_to,   "date_to")

    if parsed_from and parsed_to and parsed_from > parsed_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from must not be later than date_to.",
        )

    # ── Build and validate filter object ─────────────────────────────────
    try:
        filters = ReportFilters(
            date_from=parsed_from,
            date_to=parsed_to,
            patient_type=patient_type,
            patient_status=patient_status,
            facility_id=facility_id,
            include_patients=include_patients,
            include_pregnancies=include_pregnancies,
            include_children=include_children,
            include_transactions=include_transactions,
            include_vaccinations=include_vaccinations,
            include_prescriptions=include_prescriptions,
            include_medications=include_medications,
            include_diagnoses=include_diagnoses,
            include_reminders=include_reminders,
            include_stock=include_stock,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # ── Generate workbook ─────────────────────────────────────────────────
    service = ReportService(db)
    try:
        buf = await service.build_workbook(filters)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        filename  = f"hepvac_report_{timestamp}.xlsx"

        logger.log_info({
            "event":      "report_exported",
            "user_id":    str(current_user.id),
            "facility_id": str(current_user.facility_id),
            "filters": {
                "date_from":     str(parsed_from) if parsed_from else None,
                "date_to":       str(parsed_to)   if parsed_to   else None,
                "patient_type":  patient_type,
                "patient_status": patient_status,
            },
        })

        return StreamingResponse(
            buf,
            media_type=_MIME,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Report-Filename":   filename,
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.log_error({
            "event":   "report_export_error",
            "error":   str(exc),
            "user_id": str(current_user.id),
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating the report.",
        )