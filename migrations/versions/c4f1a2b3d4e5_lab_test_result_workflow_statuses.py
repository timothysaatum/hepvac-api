"""lab test result workflow statuses

Revision ID: c4f1a2b3d4e5
Revises: 636f796579e5
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c4f1a2b3d4e5"
down_revision: Union[str, Sequence[str], None] = "636f796579e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE lab_test_status ADD VALUE IF NOT EXISTS 'DRAFT'")
        op.execute("ALTER TYPE lab_test_status ADD VALUE IF NOT EXISTS 'FILED'")
        op.execute("ALTER TYPE lab_test_status ADD VALUE IF NOT EXISTS 'VERIFIED'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without recreating the type.
    pass
