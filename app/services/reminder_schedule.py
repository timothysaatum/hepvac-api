"""
Reminder Schedule Generator
============================
Generates an escalating set of PatientReminder rows for a given due date
and event type (EDD or 6-month checkup).

Schedule (6 reminders per event):
──────────────────────────────────
  T - 30 days  →  "Due month"     — patient enters the due month
  T - 14 days  →  "2 weeks away"  — fortnight warning
  T - 7 days   →  "1 week away"   — final week begins
  T - 5 days   →  "5 days away"   — mid-week escalation
  T - 3 days   →  "3 days away"   — closing in
  T - 0 days   →  "Today"         — day-of reminder

If the due date is already within a window (e.g. updated late), only the
reminders whose scheduled_date is still in the future (or today) are created.
Past reminders are silently skipped — no backfilling.

Usage:
    from app.services.reminder_schedule import build_reminder_rows

    rows = build_reminder_rows(
        patient_id=patient.id,
        due_date=pregnancy.expected_delivery_date,
        reminder_type=ReminderType.DELIVERY_WEEK,
    )
    for row in rows:
        db.add(row)
    await db.commit()

Cancellation (call BEFORE building new rows when a date changes):
    await cancel_pending_reminders(
        db=db,
        patient_id=patient_id,
        reminder_type=ReminderType.DELIVERY_WEEK,
        child_id=None,  # pass child.id for CHILD_6MONTH_CHECKUP
    )
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_model import PatientReminder
from app.schemas.patient_schemas import ReminderStatus, ReminderType

logger = logging.getLogger(__name__)


# ============================================================================
# Schedule definition
# ============================================================================

@dataclass(frozen=True)
class _ReminderSlot:
    """A single point in the escalating schedule."""
    days_before:    int     # days before due_date
    label:          str     # short label used in message templates


# The canonical escalation ladder — same for every event type
_SCHEDULE: List[_ReminderSlot] = [
    _ReminderSlot(days_before=30, label="due_month"),
    _ReminderSlot(days_before=14, label="two_weeks"),
    _ReminderSlot(days_before=7,  label="one_week"),
    _ReminderSlot(days_before=5,  label="five_days"),
    _ReminderSlot(days_before=3,  label="three_days"),
    _ReminderSlot(days_before=0,  label="day_of"),
]


# ============================================================================
# Message templates
# ============================================================================

def _build_message(
    reminder_type: ReminderType,
    label: str,
    due_date: date,
    patient_name: str = "Dear patient",
) -> str:
    """
    Return a clear, professional SMS-length message (<160 chars where possible).

    Messages are purposely plain-language and non-alarmist — appropriate
    for clinical SMS to Ghanaian patients.
    """
    date_str = due_date.strftime("%d %B %Y")

    templates: dict[ReminderType, dict[str, str]] = {

        ReminderType.DELIVERY_WEEK: {
            "due_month": (
                f"Hello {patient_name}, you are now in your expected delivery month "
                f"({date_str}). Please stay in close contact with your us and "
                f"report any concerns immediately. — HepVac"
            ),
            "two_weeks": (
                f"Hello {patient_name}, your expected delivery date is in 2 weeks "
                f"({date_str}). Ensure your hospital bag is ready and make all arrangements for safe delivery "
                f"is informed. — HepVac"
            ),
            "one_week": (
                f"Hello {patient_name}, your expected delivery date is in 1 week "
                f"({date_str}). Please stay close to your us and be ready "
                f"to go at any time. — HepVac"
            ),
            "five_days": (
                f"Hello {patient_name}, your expected delivery date is in 5 days "
                f"({date_str}). If you experience contractions, bleeding or reduced "
                f"movement, go to your clinic immediately. — HepVac"
            ),
            "three_days": (
                f"Hello {patient_name}, your expected delivery date is in 3 days "
                f"({date_str}). Please be near your clinic and have your emergency "
                f"contact ready. — HepVac"
            ),
            "day_of": (
                f"Hello {patient_name}, today is your expected delivery date "
                f"({date_str}). If labour has not started, please contact your "
                f"clinic for guidance. — HepVac"
            ),
        },

        ReminderType.CHILD_6MONTH_CHECKUP: {
            "due_month": (
                f"Hello {patient_name}, your child's 6-month checkup is due this "
                f"month ({date_str}). Please book an appointment with us "
                f"at your earliest convenience. — HepVac"
            ),
            "two_weeks": (
                f"Hello {patient_name}, your child's 6-month checkup is in 2 weeks "
                f"({date_str}). Please make sure you don't forget, we will kep reminding you. "
                f"— HepVac"
            ),
            "one_week": (
                f"Hello {patient_name}, your child's 6-month checkup is in 1 week "
                f"({date_str}). This visit includes important vaccinations — please "
                f"do not miss it. — HepVac"
            ),
            "five_days": (
                f"Hello {patient_name}, your child's 6-month checkup is in 5 days "
                f"({date_str}). Please confirm your attendance with the clinic. "
                f"— HepVac"
            ),
            "three_days": (
                f"Hello {patient_name}, reminder: your child's 6-month checkup is "
                f"in 3 days ({date_str}). Bring your child health card. — HepVac"
            ),
            "day_of": (
                f"Hello {patient_name}, today is your child's 6-month checkup "
                f"({date_str}). Please attend your scheduled appointment. — HepVac"
            ),
        },
    }

    # Fallback for other reminder types
    default_templates: dict[str, str] = {
        "due_month":  f"Hello {patient_name}, you have an upcoming appointment this month ({date_str}). — HepVac",
        "two_weeks":  f"Hello {patient_name}, reminder: appointment in 2 weeks ({date_str}). — HepVac",
        "one_week":   f"Hello {patient_name}, reminder: appointment in 1 week ({date_str}). — HepVac",
        "five_days":  f"Hello {patient_name}, reminder: appointment in 5 days ({date_str}). — HepVac",
        "three_days": f"Hello {patient_name}, reminder: appointment in 3 days ({date_str}). — HepVac",
        "day_of":     f"Hello {patient_name}, your appointment is today ({date_str}). — HepVac",
    }

    event_templates = templates.get(reminder_type, default_templates)
    return event_templates.get(label, default_templates.get(label, ""))


# ============================================================================
# Public API
# ============================================================================

def build_reminder_rows(
    patient_id: uuid.UUID,
    due_date: date,
    reminder_type: ReminderType,
    patient_name: str = "Dear patient",
    child_id: Optional[uuid.UUID] = None,
) -> List[PatientReminder]:
    """
    Build up to 6 PatientReminder rows for the escalation schedule.

    Reminders whose scheduled_date has already passed are silently skipped
    so a late date update doesn't create orphaned past reminders.

    The caller is responsible for adding the rows to the session and committing.
    """
    today = date.today()
    rows: List[PatientReminder] = []

    for slot in _SCHEDULE:
        scheduled = due_date - timedelta(days=slot.days_before)

        # Skip reminders that are already in the past
        if scheduled < today:
            logger.debug(
                f"Skipping {reminder_type} '{slot.label}' slot — "
                f"scheduled_date {scheduled} is already past"
            )
            continue

        message = _build_message(
            reminder_type=reminder_type,
            label=slot.label,
            due_date=due_date,
            patient_name=patient_name,
        )

        rows.append(PatientReminder(
            patient_id    = patient_id,
            reminder_type = reminder_type,
            scheduled_date= scheduled,
            message       = message,
            status        = ReminderStatus.PENDING,
            child_id      = child_id,
        ))

    logger.info(
        f"Built {len(rows)} reminder(s) for patient {patient_id} "
        f"({reminder_type}, due {due_date})"
    )
    return rows


async def cancel_pending_reminders(
    db: AsyncSession,
    patient_id: uuid.UUID,
    reminder_type: ReminderType,
    child_id: Optional[uuid.UUID] = None,
) -> int:
    """
    Cancel all PENDING reminders of a given type for a patient.
    Called before regenerating reminders when a due date changes.

    Filters by child_id when provided so a second child's reminders are
    never accidentally cancelled.

    Returns the number of reminders cancelled.
    """
    from sqlalchemy import select
    from app.models.patient_model import PatientReminder

    stmt = (
        select(PatientReminder)
        .where(
            PatientReminder.patient_id   == patient_id,
            PatientReminder.reminder_type== reminder_type,
            PatientReminder.status       == ReminderStatus.PENDING,
        )
    )
    if child_id is not None:
        stmt = stmt.where(PatientReminder.child_id == child_id)

    result = await db.execute(stmt)
    reminders = list(result.scalars().all())

    for r in reminders:
        r.status = ReminderStatus.CANCELLED

    if reminders:
        await db.flush()
        logger.info(
            f"Cancelled {len(reminders)} pending {reminder_type} reminder(s) "
            f"for patient {patient_id}"
        )

    return len(reminders)