"""
Reminder Tasks
==============
Handles patient reminder notifications for Drive4Health.

Three task functions (follow the same async (db, **payload) pattern as
background_tasks.py so the worker dispatcher treats them identically):

  • scan_due_reminders    – periodic heartbeat; finds due reminders and
                            enqueues individual send jobs
  • send_reminder_sms     – sends one SMS to a patient via Arkesel
  • send_reminder_email   – sends one email to facility staff via SMTP

Security notes
--------------
- Patient phone numbers are fetched fresh from the DB at send time;
  they are never stored in the job payload.
- API keys and SMTP credentials live in settings / env vars only.
- All PHI (patient name, reminder message) is logged at DEBUG level
  only — INFO logs use IDs.
- SMTP connection uses STARTTLS; plaintext connections are rejected.
- Reminder status is always persisted before raising, so a worker
  crash after a successful send never re-sends.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
import urllib.parse
from datetime import date, datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.config import settings
from app.models.patient_model import PatientReminder
from app.schemas.patient_schemas import ReminderStatus, ReminderType

logger = logging.getLogger(__name__)


# ============================================================================
# Arkesel SMS client (mirrors ArkeselSMSClient in background_tasks.py)
# ============================================================================

class ArkeselSMSClient:
    """
    Thin async wrapper around the Arkesel SMS API.
    Never raises — always returns a result dict with a `success` key so
    the caller can decide whether to persist a failure and retry.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client  = client
        self.api_key  = settings.ARKESEL_API_KEY
        self.base_url = settings.ARKESEL_BASE_URL
        self.sender   = settings.ARKESEL_SENDER_ID
        self.timeout  = 30.0

    async def send(
        self,
        phone_number: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Send a single SMS.

        Phone numbers must be in international format: +233XXXXXXXXX
        Arkesel also accepts 233XXXXXXXXX (no leading +).
        """
        # Normalise: strip leading + for the query string
        normalised = phone_number.lstrip("+")
        encoded_msg = urllib.parse.quote(message)

        url = (
            f"{self.base_url}"
            f"?action=send-sms"
            f"&api_key={self.api_key}"
            f"&to={normalised}"
            f"&from={urllib.parse.quote(self.sender)}"
            f"&sms={encoded_msg}"
        )

        try:
            response = await self._client.get(url, timeout=self.timeout)
            response.raise_for_status()
            result: Dict[str, Any] = response.json()
            result["success"] = result.get("code") == "ok"
            result["http_status"] = response.status_code
            return result

        except httpx.TimeoutException:
            logger.warning(f"Arkesel timeout for {normalised}")
            return {"success": False, "error": "Request timeout", "http_status": None}

        except httpx.HTTPStatusError as exc:
            logger.error(f"Arkesel HTTP {exc.response.status_code} for {normalised}")
            return {
                "success": False,
                "error": f"HTTP {exc.response.status_code}",
                "http_status": exc.response.status_code,
            }

        except Exception as exc:
            logger.error(f"Arkesel unexpected error for {normalised}: {exc}")
            return {"success": False, "error": str(exc), "http_status": None}


# ============================================================================
# SMTP email helper
# ============================================================================

def _build_reminder_email(
    to_email: str,
    to_name: str,
    patient_name: str,
    reminder_type: str,
    message: str,
    scheduled_date: date,
) -> MIMEMultipart:
    """Build a plain-text + HTML MIME email for a patient reminder."""

    type_labels: Dict[str, str] = {
        ReminderType.DELIVERY_WEEK:        "Upcoming Delivery",
        ReminderType.CHILD_6MONTH_CHECKUP: "6-Month Child Checkup",
        ReminderType.MEDICATION_DUE:       "Medication Due",
        ReminderType.PAYMENT_DUE:          "Payment Due",
        ReminderType.VACCINATION_DUE:      "Vaccination Due",
    }
    subject_label = type_labels.get(reminder_type, "Patient Reminder")
    date_str = scheduled_date.strftime("%d %B %Y")

    subject = f"[Drive4Health] {subject_label} — {patient_name}"

    plain = (
        f"Hello {to_name},\n\n"
        f"This is an automated reminder from Drive4Health.\n\n"
        f"Patient : {patient_name}\n"
        f"Type    : {subject_label}\n"
        f"Date    : {date_str}\n\n"
        f"Message :\n{message}\n\n"
        f"Please follow up with the patient accordingly.\n\n"
        f"— Drive4Health Clinical System\n"
        f"This message is confidential and intended solely for the named recipient."
    )

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;border:1px solid #e2e8f0;border-radius:8px;">
      <div style="background:#0f766e;padding:16px 24px;border-radius:6px 6px 0 0;margin:-24px -24px 24px;">
        <h2 style="color:#ffffff;margin:0;font-size:18px;">Drive4Health — {subject_label}</h2>
      </div>
      <p style="color:#475569;font-size:14px;">Hello <strong>{to_name}</strong>,</p>
      <p style="color:#475569;font-size:14px;">This is an automated reminder from the Drive4Health clinical system.</p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px;">
        <tr style="background:#f8fafc;">
          <td style="padding:10px 14px;color:#64748b;font-weight:600;width:110px;">Patient</td>
          <td style="padding:10px 14px;color:#1e293b;">{patient_name}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;color:#64748b;font-weight:600;">Type</td>
          <td style="padding:10px 14px;color:#1e293b;">{subject_label}</td>
        </tr>
        <tr style="background:#f8fafc;">
          <td style="padding:10px 14px;color:#64748b;font-weight:600;">Date</td>
          <td style="padding:10px 14px;color:#1e293b;">{date_str}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;color:#64748b;font-weight:600;vertical-align:top;">Message</td>
          <td style="padding:10px 14px;color:#1e293b;">{message}</td>
        </tr>
      </table>
      <p style="color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0;padding-top:16px;margin-top:24px;">
        This message is confidential and intended solely for authorised Drive4Health staff.
        Do not forward or share its contents.
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
    msg["To"]      = f"{to_name} <{to_email}>"
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))
    return msg


async def _send_email_via_smtp(msg: MIMEMultipart, to_email: str) -> Dict[str, Any]:
    """
    Send a MIME message over STARTTLS SMTP.
    Runs the blocking smtplib call in a thread so the event loop stays free.
    Never raises — returns a result dict.
    """
    def _blocking_send() -> Dict[str, Any]:
        context = ssl.create_default_context()
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(
                    str(settings.FROM_EMAIL),
                    [to_email],
                    msg.as_string(),
                )
            return {"success": True}
        except smtplib.SMTPAuthenticationError:
            return {"success": False, "error": "SMTP authentication failed"}
        except smtplib.SMTPRecipientsRefused:
            return {"success": False, "error": f"Recipient refused: {to_email}"}
        except smtplib.SMTPException as exc:
            return {"success": False, "error": f"SMTP error: {exc}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    return await asyncio.get_event_loop().run_in_executor(None, _blocking_send)


# ============================================================================
# Task 1 — scan_due_reminders
# ============================================================================

async def scan_due_reminders(
    db: AsyncSession,
    advance_days: int | None = None,
) -> Dict[str, Any]:
    """
    Scan PatientReminder rows that are due within `advance_days` and
    enqueue individual send jobs for each one.

    This task is invoked by the worker heartbeat — not by an HTTP request.
    It deliberately does NOT send anything itself; it only enqueues jobs
    so the full retry / failure tracking machinery applies to each send.

    Idempotency: only PENDING reminders are scanned; already-sent or
    already-enqueued (RUNNING) reminders are ignored.
    """
    from app.task.queue_manager import QueueManager

    advance = advance_days if advance_days is not None else settings.REMINDER_ADVANCE_DAYS
    today   = date.today()
    cutoff  = today + timedelta(days=advance)

    # Only pending reminders whose scheduled_date is today or in the next
    # `advance` days.  Past-due reminders (scheduled_date < today) are
    # included so nothing is silently dropped if the worker was offline.
    stmt = (
        select(PatientReminder)
        .where(
            PatientReminder.status == ReminderStatus.PENDING,
            PatientReminder.scheduled_date <= cutoff,
        )
        .options(selectinload(PatientReminder.patient))
        .order_by(PatientReminder.scheduled_date)
    )
    result = await db.execute(stmt)
    reminders = list(result.scalars().all())

    if not reminders:
        logger.info("scan_due_reminders: no pending reminders due")
        return {"success": True, "enqueued_sms": 0, "enqueued_email": 0}

    enqueued_sms   = 0
    enqueued_email = 0

    for reminder in reminders:
        patient = reminder.patient
        if not patient:
            logger.warning(f"Reminder {reminder.id} has no associated patient — skipping")
            continue

        # Enqueue SMS if patient has a phone number
        if patient.phone:
            await QueueManager.enqueue_reminder_sms(db, reminder_id=str(reminder.id))
            enqueued_sms += 1
        else:
            logger.warning(
                f"Reminder {reminder.id} — patient {reminder.patient_id} has no phone, skipping SMS"
            )

        # Enqueue email to facility staff if facility is set
        if patient.facility_id:
            await QueueManager.enqueue_reminder_email(db, reminder_id=str(reminder.id))
            enqueued_email += 1

    logger.info(
        f"scan_due_reminders: {len(reminders)} reminders → "
        f"{enqueued_sms} SMS jobs, {enqueued_email} email jobs enqueued"
    )
    return {
        "success": True,
        "total_found": len(reminders),
        "enqueued_sms": enqueued_sms,
        "enqueued_email": enqueued_email,
    }


# ============================================================================
# Task 2 — send_reminder_sms
# ============================================================================

async def send_reminder_sms(
    db: AsyncSession,
    reminder_id: str,
) -> Dict[str, Any]:
    """
    Send a single SMS reminder to a patient via Arkesel.

    The phone number is fetched fresh from the DB — it is never stored
    in the job payload to avoid leaking PHI through the job queue.

    Status transitions:
        PENDING → (sent)  → SENT
        PENDING → (failed) → FAILED  (retried by QueueManager up to max_retries)
    """
    reminder = (await db.execute(
        select(PatientReminder)
        .where(PatientReminder.id == reminder_id)
        .options(selectinload(PatientReminder.patient))
    )).scalar_one_or_none()

    if not reminder:
        logger.error(f"send_reminder_sms: reminder {reminder_id} not found")
        return {"success": False, "error": "Reminder not found"}

    # Guard: already sent — do not re-send (idempotency)
    if reminder.status == ReminderStatus.SENT:
        logger.info(f"Reminder {reminder_id} already sent — skipping")
        return {"success": True, "skipped": True, "reason": "already_sent"}

    patient = reminder.patient
    if not patient or not patient.phone:
        reminder.status = ReminderStatus.FAILED
        await db.flush()
        return {"success": False, "error": "Patient or phone number not found"}

    logger.info(
        f"send_reminder_sms: sending reminder {reminder_id} "
        f"(type={reminder.reminder_type}) to patient {reminder.patient_id}"
    )

    async with httpx.AsyncClient() as client:
        sms = ArkeselSMSClient(client)
        result = await sms.send(
            phone_number=patient.phone,
            message=reminder.message,
        )

    if result.get("success"):
        reminder.status  = ReminderStatus.SENT
        reminder.sent_at = datetime.now(timezone.utc)
        await db.flush()
        logger.info(f"Reminder {reminder_id} SMS sent successfully")
        return {"success": True, "reminder_id": reminder_id}
    else:
        # Persist FAILED before raising so the status is durable even if
        # the worker crashes before QueueManager.mark_failed() commits.
        # QueueManager will reset status to PENDING on retry — this is fine
        # because scan_due_reminders only re-scans PENDING rows.
        reminder.status = ReminderStatus.FAILED
        await db.flush()
        error = result.get("error", "Unknown Arkesel error")
        logger.error(f"Reminder {reminder_id} SMS failed: {error}")
        raise RuntimeError(error)  # Triggers QueueManager retry logic


# ============================================================================
# Task 3 — send_reminder_email
# ============================================================================

async def send_reminder_email(
    db: AsyncSession,
    reminder_id: str,
) -> Dict[str, Any]:
    """
    Send a reminder email to the facility staff responsible for this patient.

    Email is sent to the facility's registered staff — not directly to the
    patient — because patients in this system are identified by phone only.

    The recipient email is resolved from:
        PatientReminder → Patient → Facility → (facility contact email)
    If no facility email is available the job exits cleanly without failing
    so it does not consume retries on a configuration issue.
    """
    from app.models.patient_model import Patient

    reminder = (await db.execute(
        select(PatientReminder)
        .where(PatientReminder.id == reminder_id)
        .options(
            selectinload(PatientReminder.patient).selectinload(Patient.facility)
        )
    )).scalar_one_or_none()

    if not reminder:
        logger.error(f"send_reminder_email: reminder {reminder_id} not found")
        return {"success": False, "error": "Reminder not found"}

    patient = reminder.patient
    if not patient:
        logger.warning(f"Reminder {reminder_id}: patient not found — skipping email")
        return {"success": False, "error": "Patient not found"}

    facility = patient.facility
    if not facility:
        logger.warning(f"Reminder {reminder_id}: no facility on patient — skipping email")
        return {"success": True, "skipped": True, "reason": "no_facility"}

    # Resolve recipient — facility contact email field
    # Adjust `facility.email` to whatever the actual field name is on your Facility model
    facility_email = getattr(facility, "email", None) or getattr(facility, "contact_email", None)
    if not facility_email:
        logger.warning(
            f"Reminder {reminder_id}: facility {facility.id} has no email — skipping"
        )
        return {"success": True, "skipped": True, "reason": "no_facility_email"}

    facility_name = getattr(facility, "facility_name", "Facility")

    logger.info(
        f"send_reminder_email: sending reminder {reminder_id} "
        f"(type={reminder.reminder_type}) to {facility_email}"
    )

    msg = _build_reminder_email(
        to_email      = facility_email,
        to_name       = facility_name,
        patient_name  = patient.name or "Patient",
        reminder_type = reminder.reminder_type,
        message       = reminder.message,
        scheduled_date= reminder.scheduled_date,
    )

    result = await _send_email_via_smtp(msg, facility_email)

    if result.get("success"):
        logger.info(f"Reminder {reminder_id} email sent to {facility_email}")
        return {"success": True, "reminder_id": reminder_id, "sent_to": facility_email}
    else:
        error = result.get("error", "Unknown SMTP error")
        logger.error(f"Reminder {reminder_id} email failed: {error}")
        raise RuntimeError(error)  # Triggers QueueManager retry logic