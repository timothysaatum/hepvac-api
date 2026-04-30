"""harden patient integrity

Revision ID: 9f1c2a8d7b44
Revises: eb21b869f569
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f1c2a8d7b44"
down_revision: Union[str, Sequence[str], None] = "eb21b869f569"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with patient safety and integrity constraints."""
    op.execute("ALTER TYPE patientstatus ADD VALUE IF NOT EXISTS 'CONVERTED'")

    op.execute(
        """
        UPDATE patients
        SET phone = '+' || regexp_replace(phone, '\\D', '', 'g')
        WHERE phone IS NOT NULL
          AND phone !~ '^\\+[0-9]{10,15}$'
          AND length(regexp_replace(phone, '\\D', '', 'g')) BETWEEN 10 AND 15
        """
    )

    op.create_index(
        "uix_patients_facility_phone_active",
        "patients",
        ["facility_id", "phone"],
        unique=True,
        postgresql_where=sa.text("is_deleted = FALSE"),
    )

    with op.batch_alter_table("patients", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_patient_dob_not_future",
            "date_of_birth IS NULL OR date_of_birth <= CURRENT_DATE",
        )
        batch_op.create_check_constraint(
            "ck_patient_deleted_timestamp_consistent",
            "(is_deleted = FALSE AND deleted_at IS NULL) OR "
            "(is_deleted = TRUE AND deleted_at IS NOT NULL)",
        )

    with op.batch_alter_table("pregnant_patients", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_pregnant_gravida_non_negative",
            "gravida >= 0",
        )
        batch_op.create_check_constraint(
            "ck_pregnant_para_non_negative",
            "para >= 0",
        )
        batch_op.create_check_constraint(
            "ck_pregnant_para_not_gt_gravida",
            "para <= gravida",
        )

    # Existing development data may predate the stricter pregnancy lifecycle
    # rules. Repair impossible or ambiguous rows before adding CHECK
    # constraints so the database becomes self-consistent instead of leaving
    # the migration half-applied.
    op.execute(
        """
        UPDATE pregnancies
        SET gestational_age_weeks = NULL
        WHERE gestational_age_weeks IS NOT NULL
          AND (gestational_age_weeks < 0 OR gestational_age_weeks > 45)
        """
    )
    op.execute(
        """
        UPDATE pregnancies
        SET lmp_date = NULL,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: removed future LMP date while enforcing pregnancy date constraints.'
            )
        WHERE lmp_date IS NOT NULL
          AND lmp_date > CURRENT_DATE
        """
    )
    op.execute(
        """
        UPDATE pregnancies
        SET is_active = FALSE,
            outcome = COALESCE(outcome, 'LIVE_BIRTH'::pregnancy_outcome),
            actual_delivery_date = COALESCE(actual_delivery_date, CURRENT_DATE),
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: closed pregnancy because delivery/outcome data already existed.'
            )
        WHERE is_active = TRUE
          AND (outcome IS NOT NULL OR actual_delivery_date IS NOT NULL)
        """
    )
    op.execute(
        """
        UPDATE pregnancies
        SET outcome = COALESCE(outcome, 'LIVE_BIRTH'::pregnancy_outcome),
            actual_delivery_date = COALESCE(actual_delivery_date, CURRENT_DATE),
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: completed missing closure fields for historical inactive pregnancy.'
            )
        WHERE is_active = FALSE
          AND (outcome IS NULL OR actual_delivery_date IS NULL)
        """
    )
    op.execute(
        """
        UPDATE pregnancies
        SET lmp_date = NULL,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: removed LMP date because it was after the recorded delivery date.'
            )
        WHERE actual_delivery_date IS NOT NULL
          AND lmp_date IS NOT NULL
          AND actual_delivery_date < lmp_date
        """
    )
    op.execute(
        """
        UPDATE pregnancies
        SET expected_delivery_date = NULL,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: removed expected delivery date because it was before LMP.'
            )
        WHERE expected_delivery_date IS NOT NULL
          AND lmp_date IS NOT NULL
          AND expected_delivery_date < lmp_date
        """
    )

    with op.batch_alter_table("pregnancies", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_pregnancy_gestational_age_range",
            "gestational_age_weeks IS NULL OR "
            "(gestational_age_weeks >= 0 AND gestational_age_weeks <= 45)",
        )
        batch_op.create_check_constraint(
            "ck_pregnancy_lmp_not_future",
            "lmp_date IS NULL OR lmp_date <= CURRENT_DATE",
        )
        batch_op.create_check_constraint(
            "ck_pregnancy_edd_after_lmp",
            "expected_delivery_date IS NULL OR lmp_date IS NULL OR "
            "expected_delivery_date >= lmp_date",
        )
        batch_op.create_check_constraint(
            "ck_pregnancy_delivery_after_lmp",
            "actual_delivery_date IS NULL OR lmp_date IS NULL OR "
            "actual_delivery_date >= lmp_date",
        )
        batch_op.create_check_constraint(
            "ck_pregnancy_closed_state_consistent",
            "(is_active = TRUE AND outcome IS NULL AND actual_delivery_date IS NULL) OR "
            "(is_active = FALSE AND outcome IS NOT NULL AND actual_delivery_date IS NOT NULL)",
        )

    op.execute(
        """
        UPDATE regular_patients
        SET diagnosis_date = NULL,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: removed future diagnosis date while enforcing date constraints.'
            )
        WHERE diagnosis_date IS NOT NULL
          AND diagnosis_date > CURRENT_DATE
        """
    )
    op.execute(
        """
        UPDATE regular_patients
        SET last_viral_load_date = NULL,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: removed future viral load date while enforcing date constraints.'
            )
        WHERE last_viral_load_date IS NOT NULL
          AND last_viral_load_date > CURRENT_DATE
        """
    )

    with op.batch_alter_table("regular_patients", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_regular_diagnosis_not_future",
            "diagnosis_date IS NULL OR diagnosis_date <= CURRENT_DATE",
        )
        batch_op.create_check_constraint(
            "ck_regular_viral_load_not_future",
            "last_viral_load_date IS NULL OR last_viral_load_date <= CURRENT_DATE",
        )

    op.execute(
        """
        UPDATE children
        SET date_of_birth = CURRENT_DATE,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: capped future child date of birth to migration date while enforcing date constraints.'
            )
        WHERE date_of_birth > CURRENT_DATE
        """
    )
    op.execute(
        """
        UPDATE children
        SET test_date = NULL,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: removed future test date while enforcing date constraints.'
            )
        WHERE test_date IS NOT NULL
          AND test_date > CURRENT_DATE
        """
    )

    with op.batch_alter_table("children", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_child_dob_not_future",
            "date_of_birth <= CURRENT_DATE",
        )
        batch_op.create_check_constraint(
            "ck_child_test_date_not_future",
            "test_date IS NULL OR test_date <= CURRENT_DATE",
        )

    op.execute(
        """
        UPDATE payments
        SET amount = 0.01,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: raised non-positive payment amount to minimum placeholder while enforcing payment constraints.'
            )
        WHERE amount <= 0
        """
    )
    op.execute(
        """
        UPDATE payments
        SET payment_date = CURRENT_DATE,
            notes = CONCAT_WS(
                E'\n',
                NULLIF(notes, ''),
                'Migration note: capped future payment date to migration date while enforcing payment constraints.'
            )
        WHERE payment_date > CURRENT_DATE
        """
    )

    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_payment_amount_positive",
            "amount > 0",
        )
        batch_op.create_check_constraint(
            "ck_payment_date_not_future",
            "payment_date <= CURRENT_DATE",
        )

    op.execute(
        """
        UPDATE prescriptions
        SET duration_months = 1,
            instructions = CONCAT_WS(
                E'\n',
                NULLIF(instructions, ''),
                'Migration note: raised non-positive prescription duration to one month while enforcing prescription constraints.'
            )
        WHERE duration_months <= 0
        """
    )
    op.execute(
        """
        UPDATE prescriptions
        SET end_date = start_date,
            instructions = CONCAT_WS(
                E'\n',
                NULLIF(instructions, ''),
                'Migration note: adjusted prescription end date to start date because it was earlier than start date.'
            )
        WHERE end_date IS NOT NULL
          AND end_date < start_date
        """
    )

    with op.batch_alter_table("prescriptions", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_prescription_duration_positive",
            "duration_months > 0",
        )
        batch_op.create_check_constraint(
            "ck_prescription_end_after_start",
            "end_date IS NULL OR end_date >= start_date",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("prescriptions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_prescription_end_after_start", type_="check")
        batch_op.drop_constraint("ck_prescription_duration_positive", type_="check")

    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.drop_constraint("ck_payment_date_not_future", type_="check")
        batch_op.drop_constraint("ck_payment_amount_positive", type_="check")

    with op.batch_alter_table("children", schema=None) as batch_op:
        batch_op.drop_constraint("ck_child_test_date_not_future", type_="check")
        batch_op.drop_constraint("ck_child_dob_not_future", type_="check")

    with op.batch_alter_table("regular_patients", schema=None) as batch_op:
        batch_op.drop_constraint("ck_regular_viral_load_not_future", type_="check")
        batch_op.drop_constraint("ck_regular_diagnosis_not_future", type_="check")

    with op.batch_alter_table("pregnancies", schema=None) as batch_op:
        batch_op.drop_constraint("ck_pregnancy_closed_state_consistent", type_="check")
        batch_op.drop_constraint("ck_pregnancy_delivery_after_lmp", type_="check")
        batch_op.drop_constraint("ck_pregnancy_edd_after_lmp", type_="check")
        batch_op.drop_constraint("ck_pregnancy_lmp_not_future", type_="check")
        batch_op.drop_constraint("ck_pregnancy_gestational_age_range", type_="check")

    with op.batch_alter_table("pregnant_patients", schema=None) as batch_op:
        batch_op.drop_constraint("ck_pregnant_para_not_gt_gravida", type_="check")
        batch_op.drop_constraint("ck_pregnant_para_non_negative", type_="check")
        batch_op.drop_constraint("ck_pregnant_gravida_non_negative", type_="check")

    with op.batch_alter_table("patients", schema=None) as batch_op:
        batch_op.drop_constraint("ck_patient_deleted_timestamp_consistent", type_="check")
        batch_op.drop_constraint("ck_patient_dob_not_future", type_="check")

    op.drop_index("uix_patients_facility_phone_active", table_name="patients")
