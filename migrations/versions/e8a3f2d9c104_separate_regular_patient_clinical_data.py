"""separate regular patient clinical data

Revision ID: e8a3f2d9c104
Revises: d4f7a91c2b30
Create Date: 2026-04-30 00:00:03.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a3f2d9c104"
down_revision: Union[str, Sequence[str], None] = "d4f7a91c2b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("regular_patients", schema=None) as batch_op:
        batch_op.drop_constraint("ck_regular_diagnosis_not_future", type_="check")
        batch_op.drop_constraint("ck_regular_viral_load_not_future", type_="check")
        batch_op.drop_column("diagnosis_date")
        batch_op.drop_column("viral_load")
        batch_op.drop_column("last_viral_load_date")
        batch_op.drop_column("treatment_start_date")
        batch_op.drop_column("treatment_regimen")
        batch_op.drop_column("medical_history")
        batch_op.drop_column("allergies")
        batch_op.drop_column("notes")


def downgrade() -> None:
    with op.batch_alter_table("regular_patients", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("allergies", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("medical_history", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("treatment_regimen", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("treatment_start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("last_viral_load_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("viral_load", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("diagnosis_date", sa.Date(), nullable=True))
        batch_op.create_check_constraint(
            "ck_regular_viral_load_not_future",
            "last_viral_load_date IS NULL OR last_viral_load_date <= CURRENT_DATE",
        )
        batch_op.create_check_constraint(
            "ck_regular_diagnosis_not_future",
            "diagnosis_date IS NULL OR diagnosis_date <= CURRENT_DATE",
        )
