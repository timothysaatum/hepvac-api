"""lab test definition management

Revision ID: a7d4c91e2b30
Revises: 10c8928570ec
Create Date: 2026-05-02 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a7d4c91e2b30"
down_revision: Union[str, Sequence[str], None] = "10c8928570ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lab_test_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("short_name", sa.String(length=40), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("specimen", sa.String(length=80), nullable=True),
        sa.Column("method", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("code = lower(code)", name="ck_lab_test_definition_code_lower"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_lab_test_definitions_code"),
    )
    with op.batch_alter_table("lab_test_definitions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_lab_test_definitions_category"), ["category"], unique=False)
        batch_op.create_index(batch_op.f("ix_lab_test_definitions_code"), ["code"], unique=False)
        batch_op.create_index(batch_op.f("ix_lab_test_definitions_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_lab_test_definitions_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_lab_test_definitions_name"), ["name"], unique=False)

    op.create_table(
        "lab_test_parameter_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lab_test_definition_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False, server_default="numeric"),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("reference_min", sa.Numeric(12, 4), nullable=True),
        sa.Column("reference_max", sa.Numeric(12, 4), nullable=True),
        sa.Column("normal_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("abnormal_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("reference_min IS NULL OR reference_max IS NULL OR reference_min <= reference_max", name="ck_lab_parameter_range_valid"),
        sa.CheckConstraint("value_type IN ('numeric', 'text', 'both')", name="ck_lab_parameter_value_type"),
        sa.ForeignKeyConstraint(["lab_test_definition_id"], ["lab_test_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lab_test_definition_id", "code", name="uq_lab_test_parameter_definition_code"),
    )
    with op.batch_alter_table("lab_test_parameter_definitions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_lab_test_parameter_definitions_code"), ["code"], unique=False)
        batch_op.create_index(batch_op.f("ix_lab_test_parameter_definitions_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_lab_test_parameter_definitions_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_lab_test_parameter_definitions_lab_test_definition_id"), ["lab_test_definition_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_lab_test_parameter_definitions_name"), ["name"], unique=False)

    with op.batch_alter_table("patient_lab_tests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("test_definition_id", sa.UUID(), nullable=True))
        batch_op.alter_column("test_type", existing_type=postgresql.ENUM(name="lab_test_type"), nullable=True)
        batch_op.create_foreign_key(
            "fk_lab_tests_test_def_id",
            "lab_test_definitions",
            ["test_definition_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(batch_op.f("ix_patient_lab_tests_test_definition_id"), ["test_definition_id"], unique=False)

    with op.batch_alter_table("patient_lab_results", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parameter_definition_id", sa.UUID(), nullable=True))
        batch_op.create_foreign_key(
            "fk_lab_results_param_def_id",
            "lab_test_parameter_definitions",
            ["parameter_definition_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(batch_op.f("ix_patient_lab_results_parameter_definition_id"), ["parameter_definition_id"], unique=False)

    _seed_default_lab_definitions()
    op.execute(f"""
        UPDATE patient_lab_tests
        SET test_definition_id = CASE test_type::text
            WHEN 'HEP_B' THEN '{hep_b_id()}'
            WHEN 'RFT' THEN '{rft_id()}'
            WHEN 'LFT' THEN '{lft_id()}'
            ELSE test_definition_id
        END
        WHERE test_definition_id IS NULL
    """)


def downgrade() -> None:
    with op.batch_alter_table("patient_lab_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_patient_lab_results_parameter_definition_id"))
        batch_op.drop_constraint(
            "fk_lab_results_param_def_id",
            type_="foreignkey",
        )
        batch_op.drop_column("parameter_definition_id")

    with op.batch_alter_table("patient_lab_tests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_patient_lab_tests_test_definition_id"))
        batch_op.drop_constraint(
            "fk_lab_tests_test_def_id",
            type_="foreignkey",
        )
        batch_op.alter_column("test_type", existing_type=postgresql.ENUM(name="lab_test_type"), nullable=False)
        batch_op.drop_column("test_definition_id")

    with op.batch_alter_table("lab_test_parameter_definitions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_lab_test_parameter_definitions_name"))
        batch_op.drop_index(batch_op.f("ix_lab_test_parameter_definitions_lab_test_definition_id"))
        batch_op.drop_index(batch_op.f("ix_lab_test_parameter_definitions_is_active"))
        batch_op.drop_index(batch_op.f("ix_lab_test_parameter_definitions_id"))
        batch_op.drop_index(batch_op.f("ix_lab_test_parameter_definitions_code"))
    op.drop_table("lab_test_parameter_definitions")

    with op.batch_alter_table("lab_test_definitions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_lab_test_definitions_name"))
        batch_op.drop_index(batch_op.f("ix_lab_test_definitions_is_active"))
        batch_op.drop_index(batch_op.f("ix_lab_test_definitions_id"))
        batch_op.drop_index(batch_op.f("ix_lab_test_definitions_code"))
        batch_op.drop_index(batch_op.f("ix_lab_test_definitions_category"))
    op.drop_table("lab_test_definitions")


def _seed_default_lab_definitions() -> None:
    definitions = sa.table(
        "lab_test_definitions",
        sa.column("id", sa.UUID()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("short_name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("specimen", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    parameters = sa.table(
        "lab_test_parameter_definitions",
        sa.column("id", sa.UUID()),
        sa.column("lab_test_definition_id", sa.UUID()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("value_type", sa.String()),
        sa.column("unit", sa.String()),
        sa.column("reference_min", sa.Numeric()),
        sa.column("reference_max", sa.Numeric()),
        sa.column("normal_values", postgresql.JSONB()),
        sa.column("abnormal_values", postgresql.JSONB()),
        sa.column("display_order", sa.Integer()),
        sa.column("is_required", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
    )

    hep_b_uuid = hep_b_id()
    rft_uuid = rft_id()
    lft_uuid = lft_id()

    op.bulk_insert(definitions, [
        {"id": hep_b_uuid, "code": "hep_b", "name": "Hepatitis B test", "short_name": "Hep B", "category": "Serology", "description": "Hepatitis B screening and monitoring markers.", "specimen": "Blood", "is_active": True},
        {"id": rft_uuid, "code": "rft", "name": "Renal function test", "short_name": "RFT", "category": "Chemistry", "description": "Renal function and electrolyte panel.", "specimen": "Blood", "is_active": True},
        {"id": lft_uuid, "code": "lft", "name": "Liver function test", "short_name": "LFT", "category": "Chemistry", "description": "Liver enzyme and protein panel.", "specimen": "Blood", "is_active": True},
    ])

    op.bulk_insert(parameters, [
        {"id": "11111111-1111-4111-8111-000000000001", "lab_test_definition_id": hep_b_uuid, "code": "hbsag", "name": "HBsAg", "value_type": "text", "unit": None, "reference_min": None, "reference_max": None, "normal_values": ["negative", "non-reactive", "non reactive"], "abnormal_values": ["positive", "reactive"], "display_order": 1, "is_required": False, "is_active": True},
        {"id": "11111111-1111-4111-8111-000000000002", "lab_test_definition_id": hep_b_uuid, "code": "anti_hbs", "name": "Anti-HBs", "value_type": "numeric", "unit": "mIU/mL", "reference_min": 10, "reference_max": None, "normal_values": None, "abnormal_values": None, "display_order": 2, "is_required": False, "is_active": True},
        {"id": "11111111-1111-4111-8111-000000000003", "lab_test_definition_id": hep_b_uuid, "code": "hbeag", "name": "HBeAg", "value_type": "text", "unit": None, "reference_min": None, "reference_max": None, "normal_values": ["negative", "non-reactive", "non reactive"], "abnormal_values": ["positive", "reactive"], "display_order": 3, "is_required": False, "is_active": True},
        {"id": "22222222-2222-4222-8222-000000000001", "lab_test_definition_id": rft_uuid, "code": "creatinine", "name": "Creatinine", "value_type": "numeric", "unit": "umol/L", "reference_min": 44, "reference_max": 106, "normal_values": None, "abnormal_values": None, "display_order": 1, "is_required": False, "is_active": True},
        {"id": "22222222-2222-4222-8222-000000000002", "lab_test_definition_id": rft_uuid, "code": "urea", "name": "Urea", "value_type": "numeric", "unit": "mmol/L", "reference_min": 2.5, "reference_max": 7.8, "normal_values": None, "abnormal_values": None, "display_order": 2, "is_required": False, "is_active": True},
        {"id": "22222222-2222-4222-8222-000000000003", "lab_test_definition_id": rft_uuid, "code": "egfr", "name": "eGFR", "value_type": "numeric", "unit": "mL/min/1.73m2", "reference_min": 60, "reference_max": None, "normal_values": None, "abnormal_values": None, "display_order": 3, "is_required": False, "is_active": True},
        {"id": "22222222-2222-4222-8222-000000000004", "lab_test_definition_id": rft_uuid, "code": "sodium", "name": "Sodium", "value_type": "numeric", "unit": "mmol/L", "reference_min": 135, "reference_max": 145, "normal_values": None, "abnormal_values": None, "display_order": 4, "is_required": False, "is_active": True},
        {"id": "22222222-2222-4222-8222-000000000005", "lab_test_definition_id": rft_uuid, "code": "potassium", "name": "Potassium", "value_type": "numeric", "unit": "mmol/L", "reference_min": 3.5, "reference_max": 5.1, "normal_values": None, "abnormal_values": None, "display_order": 5, "is_required": False, "is_active": True},
        {"id": "33333333-3333-4333-8333-000000000001", "lab_test_definition_id": lft_uuid, "code": "alt", "name": "ALT", "value_type": "numeric", "unit": "U/L", "reference_min": None, "reference_max": 41, "normal_values": None, "abnormal_values": None, "display_order": 1, "is_required": False, "is_active": True},
        {"id": "33333333-3333-4333-8333-000000000002", "lab_test_definition_id": lft_uuid, "code": "ast", "name": "AST", "value_type": "numeric", "unit": "U/L", "reference_min": None, "reference_max": 40, "normal_values": None, "abnormal_values": None, "display_order": 2, "is_required": False, "is_active": True},
        {"id": "33333333-3333-4333-8333-000000000003", "lab_test_definition_id": lft_uuid, "code": "alp", "name": "ALP", "value_type": "numeric", "unit": "U/L", "reference_min": 44, "reference_max": 147, "normal_values": None, "abnormal_values": None, "display_order": 3, "is_required": False, "is_active": True},
        {"id": "33333333-3333-4333-8333-000000000004", "lab_test_definition_id": lft_uuid, "code": "ggt", "name": "GGT", "value_type": "numeric", "unit": "U/L", "reference_min": None, "reference_max": 60, "normal_values": None, "abnormal_values": None, "display_order": 4, "is_required": False, "is_active": True},
        {"id": "33333333-3333-4333-8333-000000000005", "lab_test_definition_id": lft_uuid, "code": "bilirubin", "name": "Bilirubin", "value_type": "numeric", "unit": "umol/L", "reference_min": 3, "reference_max": 21, "normal_values": None, "abnormal_values": None, "display_order": 5, "is_required": False, "is_active": True},
        {"id": "33333333-3333-4333-8333-000000000006", "lab_test_definition_id": lft_uuid, "code": "albumin", "name": "Albumin", "value_type": "numeric", "unit": "g/L", "reference_min": 35, "reference_max": 50, "normal_values": None, "abnormal_values": None, "display_order": 6, "is_required": False, "is_active": True},
    ])


def hep_b_id() -> str:
    return "11111111-1111-4111-8111-111111111111"


def rft_id() -> str:
    return "22222222-2222-4222-8222-222222222222"


def lft_id() -> str:
    return "33333333-3333-4333-8333-333333333333"
