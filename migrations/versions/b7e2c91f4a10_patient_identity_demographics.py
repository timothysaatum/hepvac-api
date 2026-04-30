"""patient identity demographics

Revision ID: b7e2c91f4a10
Revises: 9f1c2a8d7b44
Create Date: 2026-04-30 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e2c91f4a10"
down_revision: Union[str, Sequence[str], None] = "9f1c2a8d7b44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("patients", schema=None) as batch_op:
        batch_op.add_column(sa.Column("first_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("last_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("preferred_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("medical_record_number", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("address_line", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("city", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("district", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("region", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("country", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("emergency_contact_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("emergency_contact_phone", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("emergency_contact_relationship", sa.String(length=100), nullable=True))
        batch_op.create_index(batch_op.f("ix_patients_first_name"), ["first_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_patients_last_name"), ["last_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_patients_medical_record_number"), ["medical_record_number"], unique=False)
        batch_op.create_index(batch_op.f("ix_patients_city"), ["city"], unique=False)
        batch_op.create_index(batch_op.f("ix_patients_district"), ["district"], unique=False)
        batch_op.create_index(batch_op.f("ix_patients_region"), ["region"], unique=False)

    op.execute(
        """
        UPDATE patients
        SET first_name = split_part(name, ' ', 1),
            last_name = NULLIF(trim(substr(name, length(split_part(name, ' ', 1)) + 1)), '')
        WHERE first_name IS NULL
          AND name IS NOT NULL
        """
    )

    op.create_index(
        "uix_patients_facility_mrn_active",
        "patients",
        ["facility_id", "medical_record_number"],
        unique=True,
        postgresql_where=sa.text("is_deleted = FALSE AND medical_record_number IS NOT NULL"),
    )

    op.create_table(
        "patient_identifiers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("facility_id", sa.UUID(), nullable=False),
        sa.Column("identifier_type", sa.String(length=50), nullable=False),
        sa.Column("identifier_value", sa.String(length=100), nullable=False),
        sa.Column("issuer", sa.String(length=100), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("facility_id", "identifier_type", "identifier_value", name="uq_patient_identifier_facility_type_value"),
    )
    with op.batch_alter_table("patient_identifiers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_patient_identifiers_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_identifiers_patient_id"), ["patient_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_identifiers_facility_id"), ["facility_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_identifiers_identifier_type"), ["identifier_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_identifiers_identifier_value"), ["identifier_value"], unique=False)

    op.create_table(
        "patient_allergies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("allergen", sa.String(length=255), nullable=False),
        sa.Column("reaction", sa.String(length=255), nullable=True),
        sa.Column("severity", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id", "allergen", name="uq_patient_allergy_allergen"),
    )
    with op.batch_alter_table("patient_allergies", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_patient_allergies_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_allergies_patient_id"), ["patient_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_allergies_allergen"), ["allergen"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_allergies_severity"), ["severity"], unique=False)
        batch_op.create_index(batch_op.f("ix_patient_allergies_is_active"), ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_table("patient_allergies")
    op.drop_table("patient_identifiers")
    op.drop_index("uix_patients_facility_mrn_active", table_name="patients")
    with op.batch_alter_table("patients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_patients_region"))
        batch_op.drop_index(batch_op.f("ix_patients_district"))
        batch_op.drop_index(batch_op.f("ix_patients_city"))
        batch_op.drop_index(batch_op.f("ix_patients_medical_record_number"))
        batch_op.drop_index(batch_op.f("ix_patients_last_name"))
        batch_op.drop_index(batch_op.f("ix_patients_first_name"))
        batch_op.drop_column("emergency_contact_relationship")
        batch_op.drop_column("emergency_contact_phone")
        batch_op.drop_column("emergency_contact_name")
        batch_op.drop_column("country")
        batch_op.drop_column("region")
        batch_op.drop_column("district")
        batch_op.drop_column("city")
        batch_op.drop_column("address_line")
        batch_op.drop_column("medical_record_number")
        batch_op.drop_column("preferred_name")
        batch_op.drop_column("last_name")
        batch_op.drop_column("first_name")
