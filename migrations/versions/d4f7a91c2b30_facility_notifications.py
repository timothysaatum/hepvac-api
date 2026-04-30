"""facility notifications

Revision ID: d4f7a91c2b30
Revises: b7e2c91f4a10
Create Date: 2026-04-30 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f7a91c2b30"
down_revision: Union[str, Sequence[str], None] = "b7e2c91f4a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "facility_notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("facility_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("reminder_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("notification_type", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("action_label", sa.String(length=80), nullable=True),
        sa.Column("action_url", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("patient_phone", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("assigned_to_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="ck_facility_notification_priority",
        ),
        sa.CheckConstraint(
            "status IN ('unread', 'acknowledged', 'in_progress', 'resolved', 'dismissed')",
            name="ck_facility_notification_status",
        ),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reminder_id"], ["patient_reminders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reminder_id", name="uq_facility_notification_reminder"),
    )
    with op.batch_alter_table("facility_notifications", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_facility_notifications_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_facility_notifications_facility_id"), ["facility_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_facility_notifications_patient_id"), ["patient_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_facility_notifications_reminder_id"), ["reminder_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_facility_notifications_notification_type"), ["notification_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_facility_notifications_priority"), ["priority"], unique=False)
        batch_op.create_index(batch_op.f("ix_facility_notifications_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_facility_notifications_due_date"), ["due_date"], unique=False)


def downgrade() -> None:
    op.drop_table("facility_notifications")
