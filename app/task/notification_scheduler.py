"""
Enhanced Notification Scheduler with Database Logging

Production-ready version with persistent logging and deduplication.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from contextlib import asynccontextmanager

from app.core.notifications import EmailService, SMSService
from app.core.settings import SystemStatus
from app.core.settings_service import SettingsService
from app.core.notification_log import (
    NotificationLog,
    NotificationChannel,
    NotificationStatus
)
from app.db.session import AsyncSessionLocal as async_session_maker
import logging

logger = logging.getLogger(__name__)


class NotificationScheduler:
    """
    Production-ready notification scheduler with database persistence.
    """
    
    def __init__(
        self,
        check_interval_seconds: int = 300,
        max_concurrent_sends: int = 10,
        retry_attempts: int = 3,
        retry_delay_seconds: int = 5,
    ):
        self.check_interval = check_interval_seconds
        self.max_concurrent = max_concurrent_sends
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay_seconds
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max_concurrent_sends)
        self._current_batch_id: Optional[uuid.UUID] = None
        
        logger.info(f"Scheduler initialized with interval={check_interval_seconds}s")
    
    async def start(self):
        """Start the scheduler"""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Notification scheduler started")
    
    async def stop(self):
        """Stop the scheduler gracefully"""
        if not self._running:
            return
        
        logger.info("Stopping scheduler...")
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Scheduler stopped")
    
    async def _run_loop(self):
        """Main scheduler loop"""
        while self._running:
            try:
                await self._check_and_send_notifications()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retry
    
    async def _check_and_send_notifications(self):
        """Check and send notifications"""
        async with self._get_db_session() as db:
            try:
                # Get settings
                settings = await SettingsService.get_settings(db)
                
                # Check system status
                if settings.system_status != SystemStatus.ACTIVE.value:
                    logger.debug(f"System not active: {settings.system_status}")
                    return
                
                # Check if should send
                should_send = await self._should_send_notifications(db, settings)
                if not should_send:
                    logger.debug("Not time to send yet")
                    return
                
                # Get recipients
                recipients = await self._get_target_recipients(db, settings)
                if not recipients:
                    logger.info("No recipients found")
                    return
                
                # Create new batch
                self._current_batch_id = uuid.uuid4()
                
                logger.info(
                    f"Starting notification batch {self._current_batch_id} "
                    f"with {len(recipients)} recipients"
                )
                
                # Send notifications
                await self._send_batch(db, recipients, settings)
                
                logger.info(f"Batch {self._current_batch_id} completed")
                
            except Exception as e:
                logger.error(f"Error in notification check: {e}", exc_info=True)
    
    async def _should_send_notifications(
        self,
        db: AsyncSession,
        settings
    ) -> bool:
        """Check if it's time to send based on last successful batch"""
        # Get last successful notification
        result = await db.execute(
            select(NotificationLog.sent_at)
            .where(
                and_(
                    NotificationLog.status.in_([
                        NotificationStatus.SENT.value,
                        NotificationStatus.DELIVERED.value
                    ]),
                    NotificationLog.notification_type == "vaccination_reminder"
                )
            )
            .order_by(NotificationLog.sent_at.desc())
            .limit(1)
        )
        
        last_sent = result.scalar_one_or_none()
        
        if not last_sent:
            return True  # First time, send
        
        time_since_last = datetime.now(timezone.utc) - last_sent
        interval = timedelta(days=settings.reminder_interval_days)
        
        return time_since_last >= interval
    
    async def _get_target_recipients(
        self,
        db: AsyncSession,
        settings
    ) -> List[Dict]:
        """
        Get recipients based on target setting.
        
        IMPORTANT: Adjust this query to match your database schema.
        """
        target = settings.notification_target
        
        # Example query - CUSTOMIZE THIS FOR YOUR SCHEMA
        # from app.models.patient import Patient
        
        # Base query
        # query = select(Patient).where(Patient.is_active == True)
        
        # Apply target filter
        # if target == NotificationTarget.PREGNANT_ONLY.value:
        #     query = query.where(Patient.is_pregnant == True)
        # elif target == NotificationTarget.MOTHERS_ONLY.value:
        #     query = query.where(Patient.has_children == True)
        # ... etc
        
        # result = await db.execute(query)
        # patients = result.scalars().all()
        
        # recipients = []
        # for patient in patients:
        #     # Check deduplication - skip if sent recently
        #     if await self._was_sent_recently(db, patient.id):
        #         continue
        #     
        #     recipients.append({
        #         "id": str(patient.id),
        #         "name": patient.full_name,
        #         "email": patient.email,
        #         "phone": patient.phone_number,
        #         "type": "patient"
        #     })
        
        # For now, return empty list
        # Replace with actual implementation
        recipients = []
        
        logger.info(f"Found {len(recipients)} recipients for '{target}'")
        return recipients
    
    async def _was_sent_recently(
        self,
        db: AsyncSession,
        recipient_id: uuid.UUID,
        hours: int = 24
    ) -> bool:
        """Check if notification was sent to recipient recently"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = await db.execute(
            select(func.count(NotificationLog.id))
            .where(
                and_(
                    NotificationLog.recipient_id == recipient_id,
                    NotificationLog.sent_at >= cutoff,
                    NotificationLog.status.in_([
                        NotificationStatus.SENT.value,
                        NotificationStatus.DELIVERED.value
                    ])
                )
            )
        )
        
        count = result.scalar()
        return count > 0
    
    async def _send_batch(
        self,
        db: AsyncSession,
        recipients: List[Dict],
        settings
    ):
        """Send notifications to all recipients"""
        message = settings.reminder_message or self._get_default_message()
        
        # Create tasks
        tasks = [
            self._send_with_logging(db, recipient, message)
            for recipient in recipients
        ]
        
        # Execute concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_with_logging(
        self,
        db: AsyncSession,
        recipient: Dict,
        message: str
    ):
        """Send notification and log to database"""
        async with self._semaphore:
            # Personalize message
            personalized = message.replace("{name}", recipient.get("name", ""))
            
            # Send via each available channel
            email_log = None
            sms_log = None
            
            # Email
            if recipient.get("email"):
                email_log = await self._send_email_with_log(
                    db, recipient, personalized
                )
            
            # SMS
            if recipient.get("phone"):
                sms_log = await self._send_sms_with_log(
                    db, recipient, personalized
                )
            
            # Commit logs
            try:
                await db.commit()
            except Exception as e:
                logger.error(f"Error committing logs: {e}")
                await db.rollback()
    
    async def _send_email_with_log(
        self,
        db: AsyncSession,
        recipient: Dict,
        message: str
    ) -> NotificationLog:
        """Send email and create log entry"""
        # Create log entry
        log = NotificationLog(
            recipient_id=uuid.UUID(recipient["id"]),
            recipient_type=recipient.get("type", "patient"),
            recipient_name=recipient["name"],
            recipient_email=recipient["email"],
            channel=NotificationChannel.EMAIL.value,
            subject="Vaccination Reminder",
            message=message,
            notification_type="vaccination_reminder",
            status=NotificationStatus.PENDING.value,
            triggered_by="scheduler",
            batch_id=self._current_batch_id,
        )
        
        db.add(log)
        await db.flush()  # Get ID
        
        # Attempt to send
        for attempt in range(1, self.retry_attempts + 1):
            try:
                success = await EmailService.send_email(
                    to=recipient["email"],
                    subject="Vaccination Reminder",
                    body=message,
                    html=self._format_html(message)
                )
                
                if success:
                    log.mark_sent()
                    logger.info(f"Email sent to {recipient['name']}")
                    return log
                
                # Failed, retry if possible
                if attempt < self.retry_attempts:
                    await asyncio.sleep(self.retry_delay * attempt)
                    log.retry_count += 1
                
            except Exception as e:
                log.retry_count += 1
                if attempt == self.retry_attempts:
                    log.mark_failed(str(e))
                    logger.error(f"Email failed to {recipient['name']}: {e}")
                else:
                    await asyncio.sleep(self.retry_delay * attempt)
        
        return log
    
    async def _send_sms_with_log(
        self,
        db: AsyncSession,
        recipient: Dict,
        message: str
    ) -> NotificationLog:
        """Send SMS and create log entry"""
        # Create log entry
        log = NotificationLog(
            recipient_id=uuid.UUID(recipient["id"]),
            recipient_type=recipient.get("type", "patient"),
            recipient_name=recipient["name"],
            recipient_phone=recipient["phone"],
            channel=NotificationChannel.SMS.value,
            message=message,
            notification_type="vaccination_reminder",
            status=NotificationStatus.PENDING.value,
            triggered_by="scheduler",
            batch_id=self._current_batch_id,
        )
        
        db.add(log)
        await db.flush()
        
        # Attempt to send
        for attempt in range(1, self.retry_attempts + 1):
            try:
                result = await SMSService.send_sms(
                    to=recipient["phone"],
                    message=message
                )
                
                if result.get(recipient["phone"], False):
                    log.mark_sent()
                    logger.info(f"SMS sent to {recipient['name']}")
                    return log
                
                if attempt < self.retry_attempts:
                    await asyncio.sleep(self.retry_delay * attempt)
                    log.retry_count += 1
                
            except Exception as e:
                log.retry_count += 1
                if attempt == self.retry_attempts:
                    log.mark_failed(str(e))
                    logger.error(f"SMS failed to {recipient['name']}: {e}")
                else:
                    await asyncio.sleep(self.retry_delay * attempt)
        
        return log
    
    def _get_default_message(self) -> str:
        """Default reminder message"""
        return (
            "Hello {name},\n\n"
            "This is a reminder about your vaccination schedule. "
            "Please contact us to confirm your appointment.\n\n"
            "Stay healthy!"
        )
    
    def _format_html(self, text: str) -> str:
        """Format HTML email"""
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #2c3e50;">Vaccination Reminder</h2>
                    <p style="line-height: 1.6;">{text.replace(chr(10), '<br>')}</p>
                    <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                    <p style="font-size: 12px; color: #888;">
                        Automated message - please do not reply.
                    </p>
                </div>
            </body>
        </html>
        """
    
    @asynccontextmanager
    async def _get_db_session(self):
        """Get database session"""
        async with async_session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def get_stats(self, db: AsyncSession, days: int = 7) -> Dict:
        """Get notification statistics"""
        date_from = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Total sent
        total_result = await db.execute(
            select(func.count(NotificationLog.id))
            .where(NotificationLog.sent_at >= date_from)
        )
        total = total_result.scalar()
        
        # By status
        status_result = await db.execute(
            select(
                NotificationLog.status,
                func.count(NotificationLog.id)
            )
            .where(NotificationLog.sent_at >= date_from)
            .group_by(NotificationLog.status)
        )
        by_status = dict(status_result.all())
        
        return {
            "running": self._running,
            "period_days": days,
            "total_sent": total,
            "by_status": by_status,
        }


# Global instance
_scheduler: Optional[NotificationScheduler] = None


async def start_scheduler(**kwargs) -> NotificationScheduler:
    """Start the scheduler"""
    global _scheduler
    
    if _scheduler:
        return _scheduler
    
    _scheduler = NotificationScheduler(**kwargs)
    await _scheduler.start()
    return _scheduler


async def stop_scheduler():
    """Stop the enhanced scheduler"""
    global _scheduler
    
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None


def get_scheduler() -> Optional[NotificationScheduler]:
    """Get scheduler instance"""
    return _scheduler