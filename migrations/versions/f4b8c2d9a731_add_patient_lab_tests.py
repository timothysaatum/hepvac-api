"""add patient lab tests

Revision ID: f4b8c2d9a731
Revises: c900779aea47
Create Date: 2026-04-30 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f4b8c2d9a731"
down_revision: Union[str, Sequence[str], None] = "c900779aea47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


lab_test_type = postgresql.ENUM(
    "HEP_B",
    "RFT",
    "LFT",
    name="lab_test_type",
    create_type=False,
)
lab_test_status = postgresql.ENUM(
    "ORDERED",
    "IN_PROGRESS",
    "COMPLETED",
    "CANCELLED",
    name="lab_test_status",
    create_type=False,
)
lab_result_flag = postgresql.ENUM(
    "NORMAL",
    "LOW",
    "HIGH",
    "CRITICAL_LOW",
    "CRITICAL_HIGH",
    "ABNORMAL",
    name="lab_result_flag",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    lab_test_type.create(bind, checkfirst=True)
    lab_test_status.create(bind, checkfirst=True)
    lab_result_flag.create(bind, checkfirst=True)

    op.create_table(
        "patient_lab_tests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("test_type", lab_test_type, nullable=False),
        sa.Column("test_name", sa.String(length=120), nullable=False),
        sa.Column("status", lab_test_status, nullable=False),
        sa.Column("ordered_by_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("ordered_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("collected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reported_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "reported_at IS NULL OR collected_at IS NULL OR reported_at >= collected_at",
            name="ck_lab_test_reported_after_collected",
        ),
        sa.ForeignKeyConstraint(["ordered_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("patient_lab_tests", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_patient_lab_tests_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_tests_ordered_at"), ["ordered_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_tests_patient_id"), ["patient_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_tests_reported_at"), ["reported_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_tests_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_tests_test_type"), ["test_type"], unique=False)

    op.create_table(
        "patient_lab_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lab_test_id", sa.UUID(), nullable=False),
        sa.Column("component_name", sa.String(length=120), nullable=False),
        sa.Column("component_code", sa.String(length=50), nullable=True),
        sa.Column("value_numeric", sa.Numeric(12, 4), nullable=True),
        sa.Column("value_text", sa.String(length=120), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("reference_min", sa.Numeric(12, 4), nullable=True),
        sa.Column("reference_max", sa.Numeric(12, 4), nullable=True),
        sa.Column("abnormal_flag", lab_result_flag, nullable=False),
        sa.Column("is_abnormal", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "value_numeric IS NOT NULL OR value_text IS NOT NULL",
            name="ck_lab_result_value_present",
        ),
        sa.CheckConstraint(
            "reference_min IS NULL OR reference_max IS NULL OR reference_min <= reference_max",
            name="ck_lab_result_reference_range_valid",
        ),
        sa.ForeignKeyConstraint(["lab_test_id"], ["patient_lab_tests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("patient_lab_results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_patient_lab_results_abnormal_flag"), ["abnormal_flag"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_results_component_code"), ["component_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_results_component_name"), ["component_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_results_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_results_is_abnormal"), ["is_abnormal"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_lab_results_lab_test_id"), ["lab_test_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("patient_lab_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_patient_lab_results_lab_test_id"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_results_is_abnormal"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_results_id"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_results_component_name"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_results_component_code"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_results_abnormal_flag"))
    op.drop_table("patient_lab_results")

    with op.batch_alter_table("patient_lab_tests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_patient_lab_tests_test_type"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_tests_status"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_tests_reported_at"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_tests_patient_id"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_tests_ordered_at"))
        batch_op.drop_index(batch_op.f("ix_patient_lab_tests_id"))
    op.drop_table("patient_lab_tests")

    bind = op.get_bind()
    lab_result_flag.drop(bind, checkfirst=True)
    lab_test_status.drop(bind, checkfirst=True)
    lab_test_type.drop(bind, checkfirst=True)
