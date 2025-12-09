"""
Notification Log Model

Tracks all sent notifications for auditing and deduplication.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String, Text, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db.base import Base


class NotificationChannel(str, Enum):
    """Notification delivery channels"""
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"


class NotificationStatus(str, Enum):
    """Notification delivery status"""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"
    DELIVERED = "delivered"


class NotificationLog(Base):
    """
    Log of all sent notifications for tracking and auditing.
    """
    __tablename__ = "notification_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique notification log ID"
    )
    
    # Recipient information
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="ID of the recipient (patient/staff)"
    )
    
    recipient_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of recipient (patient, staff, etc.)"
    )
    
    recipient_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of recipient at time of sending"
    )
    
    recipient_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Email address used"
    )
    
    recipient_phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Phone number used"
    )
    
    # Notification details
    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Channel used (email, sms, etc.)"
    )
    
    subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Email subject or SMS title"
    )
    
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message content sent"
    )
    
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of notification (reminder, alert, etc.)"
    )
    
    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default=NotificationStatus.PENDING.value,
        nullable=False,
        index=True,
        comment="Current delivery status"
    )
    
    sent_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        index=True,
        comment="When notification was sent"
    )
    
    delivered_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="When notification was delivered (if tracked)"
    )
    
    failed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="When notification failed"
    )
    
    # Error tracking
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )
    
    retry_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        comment="Number of retry attempts"
    )
    
    # Provider information
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Service provider used (twilio, termii, etc.)"
    )
    
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Provider's message ID for tracking"
    )
    
    # Metadata
    triggered_by: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="What triggered this notification (scheduler, manual, etc.)"
    )
    
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who triggered (if manual)"
    )
    
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Batch ID for grouped notifications"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.now(timezone.utc),
        nullable=False,
        index=True,
        comment="When log entry was created"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        nullable=False,
        comment="Last update timestamp"
    )
    
    # Relationships
    triggered_by_user = relationship(
        "User",
        foreign_keys=[triggered_by_user_id],
        lazy="select"
    )
    
    # Table args
    __table_args__ = (
        # Composite indexes for common queries
        Index(
            'idx_notification_recipient_date',
            'recipient_id',
            'sent_at'
        ),
        Index(
            'idx_notification_status_channel',
            'status',
            'channel',
            'created_at'
        ),
        Index(
            'idx_notification_batch',
            'batch_id',
            'status'
        ),
        Index(
            'idx_notification_type_date',
            'notification_type',
            'sent_at'
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<NotificationLog(id={self.id}, recipient={self.recipient_name}, "
            f"channel={self.channel}, status={self.status})>"
        )
    
    def mark_sent(self):
        """Mark notification as sent"""
        self.status = NotificationStatus.SENT.value
        self.sent_at = datetime.now(timezone.utc)
    
    def mark_failed(self, error_message: str):
        """Mark notification as failed"""
        self.status = NotificationStatus.FAILED.value
        self.failed_at = datetime.now(timezone.utc)
        self.error_message = error_message
    
    def mark_delivered(self):
        """Mark notification as delivered"""
        self.status = NotificationStatus.DELIVERED.value
        self.delivered_at = datetime.now(timezone.utc)