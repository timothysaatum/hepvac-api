"""
Patient service — business logic layer.
The service layer orchestrates complex operations that may involve multiple repository calls, transactions, and business rules. It owns the transaction
"""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_model import (
    PregnantPatient,
    Pregnancy,
    RegularPatient,
    Child,
    Prescription,
    MedicationSchedule,
    PatientReminder, Diagnosis, FacilityNotification,
    PatientIdentifier,
    PatientAllergy,
    PatientLabResult,
    PatientLabTest,
)
from app.schemas.patient_schemas import (
    PregnantPatientCreateSchema,
    PregnantPatientUpdateSchema,
    PregnancyCreateSchema,
    PregnancyUpdateSchema,
    PregnancyCloseSchema,
    RegularPatientCreateSchema,
    RegularPatientUpdateSchema,
    ChildCreateSchema,
    ChildUpdateSchema,
    PrescriptionCreateSchema,
    PrescriptionUpdateSchema,
    MedicationScheduleCreateSchema,
    MedicationScheduleUpdateSchema,
    PatientReminderCreateSchema,
    PatientReminderUpdateSchema,
    ConvertToRegularPatientSchema,
    ReRegisterAsPregnantSchema,
    PatientStatus,
    PatientType,
    Sex,
    PatientAllergySchema,
    PatientAllergyUpdateSchema,
    PatientLabResultCreateSchema,
    PatientLabResultUpdateSchema,
    PatientLabTestCreateSchema,
    PatientLabTestUpdateSchema,
    FacilityNotificationUpdateSchema,
    DiagnosisCreateSchema,
    DiagnosisUpdateSchema,
    LabResultFlag,
    LabTestStatus,
    LabTestType,
    PregnancyOutcome,
)
from app.repositories.patient_repo import PatientRepository
from app.services.reminder_schedule import build_reminder_rows, cancel_pending_reminders
from app.schemas.patient_schemas import ReminderStatus, ReminderType
from app.models.user_model import User


class PatientService:
    """Service layer for patient business logic."""

    CLOSED_PREGNANCY_CHILD_ENTRY_GRACE_DAYS = 7

    def __init__(self, db: AsyncSession, current_user: Optional[User] = None):
        self.db = db
        self.repo = PatientRepository(self.db)
        self.current_user = current_user

    def _is_admin_context(self) -> bool:
        return bool(
            self.current_user
            and (
                self.current_user.has_role("admin")
                or self.current_user.has_role("superadmin")
            )
        )

    def _can_verify_lab_results(self) -> bool:
        if not self.current_user:
            return False
        role_names = {role.name.lower() for role in self.current_user.roles}
        return bool(
            role_names
            & {"admin", "superadmin", "super_admin", "supervisor", "lab_supervisor", "manager"}
        )

    def _current_facility_id(self) -> Optional[uuid.UUID]:
        return self.current_user.facility_id if self.current_user else None

    def _scope_facility_filter(
        self,
        requested_facility_id: Optional[uuid.UUID] = None,
    ) -> Optional[uuid.UUID]:
        """
        Staff users are always constrained to their own facility. Admins may
        pass an explicit facility filter or see cross-facility data.
        """
        if self.current_user is None or self._is_admin_context():
            return requested_facility_id

        user_facility_id = self._current_facility_id()
        if user_facility_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not assigned to a facility.",
            )
        if requested_facility_id and requested_facility_id != user_facility_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot access patients outside your facility.",
            )
        return user_facility_id

    def _assert_facility_access(self, facility_id: Optional[uuid.UUID]) -> None:
        if self.current_user is None or self._is_admin_context():
            return
        if facility_id is None or facility_id != self._current_facility_id():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )

    def _display_name_from_identity(self, data: dict) -> str:
        first_name = (data.get("first_name") or "").strip()
        last_name = (data.get("last_name") or "").strip()
        preferred_name = (data.get("preferred_name") or "").strip()
        explicit_name = (data.get("name") or "").strip()
        if first_name and last_name:
            return f"{first_name} {last_name}"
        if explicit_name:
            return explicit_name
        if preferred_name:
            return preferred_name
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either name or both first_name and last_name.",
        )

    def _attach_identity_children(
        self,
        patient,
        identifiers: list,
    ) -> None:
        for item in identifiers:
            item_dict = dict(item)
            item_dict.pop("id", None)
            item_dict["facility_id"] = patient.facility_id
            patient.identifiers.append(PatientIdentifier(**item_dict))

    async def _assert_patient_access(self, patient_id: uuid.UUID) -> None:
        if self.current_user is None or self._is_admin_context():
            return
        facility_id = await self.repo.get_patient_facility_id(patient_id)
        self._assert_facility_access(facility_id)

    async def _assert_pregnancy_access(self, pregnancy_id: uuid.UUID) -> None:
        if self.current_user is None or self._is_admin_context():
            return
        facility_id = await self.repo.get_pregnancy_facility_id(pregnancy_id)
        self._assert_facility_access(facility_id)

    async def _assert_child_access(self, child_id: uuid.UUID) -> None:
        if self.current_user is None or self._is_admin_context():
            return
        facility_id = await self.repo.get_child_facility_id(child_id)
        self._assert_facility_access(facility_id)

    async def _assert_diagnosis_access(self, diagnosis_id: uuid.UUID) -> None:
        if self.current_user is None or self._is_admin_context():
            return
        facility_id = await self.repo.get_diagnosis_facility_id(diagnosis_id)
        self._assert_facility_access(facility_id)

    async def _assert_lab_test_access(self, lab_test_id: uuid.UUID) -> None:
        if self.current_user is None or self._is_admin_context():
            return
        facility_id = await self.repo.get_lab_test_facility_id(lab_test_id)
        self._assert_facility_access(facility_id)

    async def _assert_lab_result_access(self, lab_result_id: uuid.UUID) -> None:
        if self.current_user is None or self._is_admin_context():
            return
        facility_id = await self.repo.get_lab_result_facility_id(lab_result_id)
        self._assert_facility_access(facility_id)

    def _default_lab_test_name(self, test_type: LabTestType) -> str:
        names = {
            LabTestType.HEP_B: "Hepatitis B test",
            LabTestType.RFT: "Renal function test",
            LabTestType.LFT: "Liver function test",
        }
        return names[test_type]

    def _apply_lab_result_indicator(self, result: PatientLabResult) -> None:
        result.apply_abnormal_indicator()
        if result.is_abnormal and result.abnormal_flag == LabResultFlag.NORMAL:
            result.abnormal_flag = LabResultFlag.ABNORMAL

    async def _apply_parameter_definition_to_result(
        self,
        result: PatientLabResult,
        lab_test: Optional[PatientLabTest] = None,
    ) -> None:
        if not result.parameter_definition_id:
            self._apply_lab_result_indicator(result)
            return

        parameter = await self.repo.get_lab_parameter_definition_by_id(result.parameter_definition_id)
        if not parameter or not parameter.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected lab parameter is not available.",
            )

        if lab_test and lab_test.test_definition_id and parameter.lab_test_definition_id != lab_test.test_definition_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected parameter does not belong to this lab test.",
            )

        result.component_name = parameter.name
        result.component_code = parameter.code
        result.unit = parameter.unit
        result.reference_min = parameter.reference_min
        result.reference_max = parameter.reference_max

        self._apply_lab_result_indicator(result)

        text_value = (result.value_text or "").strip().lower()
        if text_value:
            abnormal_values = {v.lower() for v in (parameter.abnormal_values or [])}
            normal_values = {v.lower() for v in (parameter.normal_values or [])}
            if text_value in abnormal_values:
                result.abnormal_flag = LabResultFlag.ABNORMAL
                result.is_abnormal = True
            elif text_value in normal_values:
                result.abnormal_flag = LabResultFlag.NORMAL
                result.is_abnormal = False

    def _add_months(self, start: date, months: int) -> date:
        month = start.month - 1 + months
        year = start.year + month // 12
        month = month % 12 + 1
        month_days = [
            31,
            29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ]
        return date(year, month, min(start.day, month_days[month - 1]))

    def _delivery_date_range(
        self,
        delivery_date_field: Optional[str],
        delivery_window_days: Optional[int],
        delivery_window_months: Optional[int],
        delivery_date_from: Optional[date] = None,
        delivery_date_to: Optional[date] = None,
    ) -> tuple[Optional[date], Optional[date]]:
        has_explicit_range = delivery_date_from is not None or delivery_date_to is not None
        if (
            not delivery_date_field
            and delivery_window_days is None
            and delivery_window_months is None
            and not has_explicit_range
        ):
            return None, None

        if delivery_date_field not in {"expected", "actual"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="delivery_date_field must be either 'expected' or 'actual'.",
            )
        if has_explicit_range:
            if delivery_window_days is not None or delivery_window_months is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Use either delivery date range or delivery window filters, not both.",
                )
            if delivery_date_from and delivery_date_to and delivery_date_from > delivery_date_to:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="delivery_date_from must not be later than delivery_date_to.",
                )
            return delivery_date_from, delivery_date_to

        if delivery_window_days is not None and delivery_window_months is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use either delivery_window_days or delivery_window_months, not both.",
            )
        if delivery_window_days is None and delivery_window_months is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide delivery_window_days or delivery_window_months.",
            )
        if delivery_window_days is not None and not (0 <= delivery_window_days <= 366):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="delivery_window_days must be between 0 and 366.",
            )
        if delivery_window_months is not None and not (0 <= delivery_window_months <= 24):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="delivery_window_months must be between 0 and 24.",
            )

        today = date.today()
        if delivery_window_days is not None:
            span = timedelta(days=delivery_window_days)
            if delivery_date_field == "expected":
                return today, today + span
            return today - span, today

        months = delivery_window_months or 0
        if delivery_date_field == "expected":
            return today, self._add_months(today, months)
        return self._add_months(today, -months), today

    def _closed_pregnancy_grace_deadline(self, pregnancy: Pregnancy) -> Optional[date]:
        if pregnancy.is_active or pregnancy.actual_delivery_date is None:
            return None
        return pregnancy.actual_delivery_date + timedelta(
            days=self.CLOSED_PREGNANCY_CHILD_ENTRY_GRACE_DAYS
        )

    def _is_closed_pregnancy_in_grace(self, pregnancy: Pregnancy) -> bool:
        deadline = self._closed_pregnancy_grace_deadline(pregnancy)
        return deadline is not None and date.today() <= deadline

    def _assert_child_can_be_added_to_pregnancy(self, pregnancy: Pregnancy) -> None:
        if pregnancy.is_active or self._is_admin_context():
            return

        if pregnancy.outcome != PregnancyOutcome.LIVE_BIRTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Children can only be added to a closed pregnancy when the outcome was live birth.",
            )

        if not self._is_closed_pregnancy_in_grace(pregnancy):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "The child registration window for this closed pregnancy has ended. "
                    "Ask an admin to add or correct birth records."
                ),
            )

    def _assert_closed_pregnancy_edit_allowed(self, pregnancy: Pregnancy) -> None:
        if pregnancy.is_active or self._is_admin_context():
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Closed pregnancy details can only be modified by an admin.",
        )

    # =========================================================================
    # Pregnant patient
    # =========================================================================

    async def create_pregnant_patient(
        self, patient_data: PregnantPatientCreateSchema
    ) -> PregnantPatient:
        """
        Create a new pregnant patient together with her first pregnancy episode.

        The schema embeds a `first_pregnancy: PregnancyCreateSchema`. We pop
        that field before constructing the ORM model, then call
        open_new_pregnancy() to attach the episode atomically.
        """
        if patient_data.facility_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Facility ID is required to create a patient.",
            )
        self._assert_facility_access(patient_data.facility_id)
        if patient_data.sex != Sex.FEMALE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only female patients can be registered as pregnant.",
            )

        existing = await self.repo.get_patient_by_phone(
            patient_data.phone, patient_data.facility_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A patient with this phone number already exists in this facility.",
            )

        # Separate the nested pregnancy data before ORM construction.
        # Passing it through model_dump() would include `first_pregnancy` as a
        # dict kwarg to PregnantPatient(**...) which has no such column.
        patient_dict = patient_data.model_dump(exclude={"first_pregnancy"})
        identifiers = patient_dict.pop("identifiers", []) or []
        patient_dict["name"] = self._display_name_from_identity(patient_dict)
        patient_dict["patient_type"] = PatientType.PREGNANT
        patient_dict["status"] = PatientStatus.ACTIVE

        db_patient = PregnantPatient(**patient_dict)
        self._attach_identity_children(db_patient, identifiers)

        # Open the first pregnancy episode using the model's business logic.
        # This increments gravida to 1 and sets pregnancy_number = 1.
        pregnancy = db_patient.open_new_pregnancy()

        # Apply any clinical data that was provided in the request.
        first_preg_data = patient_data.first_pregnancy
        if first_preg_data.lmp_date:
            pregnancy.lmp_date = first_preg_data.lmp_date
        if first_preg_data.expected_delivery_date:
            pregnancy.expected_delivery_date = first_preg_data.expected_delivery_date
        if first_preg_data.gestational_age_weeks is not None:
            pregnancy.gestational_age_weeks = first_preg_data.gestational_age_weeks
        if first_preg_data.risk_factors:
            pregnancy.risk_factors = first_preg_data.risk_factors
        if first_preg_data.notes:
            pregnancy.notes = first_preg_data.notes

        # create_pregnant_patient cascades the Pregnancy via the relationship.
        created = await self.repo.create_pregnant_patient(db_patient)

        # Generate delivery reminders immediately if EDD was provided at registration
        if first_preg_data.expected_delivery_date:
            rows = build_reminder_rows(
                patient_id=created.id,
                due_date=first_preg_data.expected_delivery_date,
                reminder_type=ReminderType.DELIVERY_WEEK,
                patient_name=created.name,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return created

    async def get_pregnant_patient(self, patient_id: uuid.UUID) -> PregnantPatient:
        """Get pregnant patient by ID."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            # If the base patient exists but is now regular, this endpoint is
            # simply the wrong resource. The unified GET /patients/{id} endpoint
            # should be used when the frontend does not know the current type.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        return patient

    async def update_pregnant_patient(
        self,
        updated_by_id: uuid.UUID,
        patient_id: uuid.UUID,
        update_data: PregnantPatientUpdateSchema,
    ) -> PregnantPatient:
        """Update patient-level fields on a PregnantPatient."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        self._assert_facility_access(patient.facility_id)

        update_dict = update_data.model_dump(exclude_unset=True)

        if "phone" in update_dict and update_dict["phone"] != patient.phone:
            existing = await self.repo.get_patient_by_phone(
                update_dict["phone"], patient.facility_id
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A patient with this phone number already exists.",
                )

        identity_fields = {"first_name", "last_name", "preferred_name"}
        if "name" not in update_dict and identity_fields.intersection(update_dict):
            merged = {
                "name": patient.name,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "preferred_name": patient.preferred_name,
            }
            merged.update(update_dict)
            update_dict["name"] = self._display_name_from_identity(merged)

        for field, value in update_dict.items():
            setattr(patient, field, value)

        return await self.repo.update_pregnant_patient(updated_by_id, patient)

    async def convert_to_regular_patient(
        self,
        user_id: uuid.UUID,
        patient_id: uuid.UUID,
        conversion_data: ConvertToRegularPatientSchema,
    ) -> RegularPatient:
        """
        Convert a pregnant patient to a regular patient after delivery.

        How it works:
          1. Close the active Pregnancy episode with the provided outcome.
          2. Update the patient_type discriminator on the base Patient row.
          3. Create a RegularPatient subtype row using the SAME primary key,
             so all existing prescriptions, vaccinations, and payments remain
             linked to the same patient_id.
          4. Soft-mark the old pregnant_patients row (via status = POSTPARTUM)
             — the actual row is kept for Pregnancy/Child history.

        The old approach created a brand new UUID, permanently orphaning all
        related records. That approach has been replaced here.
        """
        from app.core.utils import logger
        
        pregnant_patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not pregnant_patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        self._assert_facility_access(pregnant_patient.facility_id)

        if pregnant_patient.status not in (PatientStatus.ACTIVE, PatientStatus.POSTPARTUM):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only active or postpartum patients can be converted.",
            )

        # Step 1: close the active Pregnancy episode.
        active_pregnancy = await self.repo.get_active_pregnancy(patient_id)
        if active_pregnancy:
            # increment_para=True for LIVE_BIRTH and STILLBIRTH; the model
            # method handles it; we pass the flag based on outcome type.
            from app.schemas.patient_schemas import PregnancyOutcome
            increment = conversion_data.outcome in (
                PregnancyOutcome.LIVE_BIRTH,
                PregnancyOutcome.STILLBIRTH,
            )
            try:
                pregnant_patient.close_active_pregnancy(
                    outcome=conversion_data.outcome,
                    delivery_date=conversion_data.actual_delivery_date,
                    increment_para=increment,
                )
            except ValueError as e:
                logger.log_error({
                    "event": "pregnancy_closure_failed",
                    "patient_id": str(patient_id),
                    "error": str(e)
                })
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                )
            await self.repo.update_pregnant_patient(user_id, pregnant_patient)

        # Steps 2 & 3: raw SQL to avoid ORM INSERT on the existing patients row.
        #
        # db.add(RegularPatient(id=existing_id)) looks new to SQLAlchemy's identity
        # map → it emits INSERT INTO patients with nulls → NOT NULL violation on name.
        # The patients row already exists; we only need to:
        #   a. UPDATE the discriminator column.
        #   b. INSERT into regular_patients (subtype table only).
        from sqlalchemy import text as _text, select as _select

        try:
            await self.db.execute(
                _text("""
                    UPDATE patients
                    SET patient_type  = 'REGULAR',
                        status        = 'POSTPARTUM',
                        updated_by_id = :user_id
                    WHERE id = :patient_id
                """),
                {"user_id": str(user_id), "patient_id": str(patient_id)},
            )

            await self.db.execute(
                _text("""
                    INSERT INTO regular_patients
                        (id)
                    VALUES
                        (:id)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": str(patient_id),
                },
            )

            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.log_error({
                "event": "conversion_transaction_failed",
                "patient_id": str(patient_id),
                "error": str(e)
            }, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Conversion transaction failed. Please try again.",
            )

        # FIX: expunge_all() instead of expire_all().
        # expire_all() only marks attributes stale — it does NOT remove the
        # PregnantPatient object from the identity map. The subsequent
        # select(RegularPatient) would find the cached PregnantPatient for this
        # PK and return None or the wrong type. expunge_all() fully evicts all
        # objects so the next SELECT builds a fresh RegularPatient from the DB.
        self.db.expunge_all()

        # Reload with a clean SELECT with all eager loads the response schema needs.
        # RegularPatient relationships are lazy="noload" — selectinload is required
        # or from_patient() will trigger implicit lazy loads → MissingGreenlet error.
        from sqlalchemy.orm import selectinload as _sil
        result = await self.db.execute(
            _select(RegularPatient)
            .where(RegularPatient.id == patient_id)
            .options(
                _sil(RegularPatient.facility),
                _sil(RegularPatient.created_by),
                _sil(RegularPatient.updated_by),
                _sil(RegularPatient.identifiers),
                _sil(RegularPatient.allergies_structured),
            )
        )
        regular_patient = result.scalars().first()
        
        if not regular_patient:
            logger.log_error({
                "event": "conversion_verification_failed",
                "patient_id": str(patient_id),
                "detail": "Could not reload RegularPatient after conversion"
            })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Conversion succeeded but patient could not be reloaded.",
            )
        
        logger.log_info({
            "event": "patient_converted_to_regular",
            "patient_id": str(patient_id),
            "converted_by": str(user_id),
        })
        
        return regular_patient

    # =========================================================================
    # Regular patient
    # =========================================================================

    async def create_regular_patient(
        self, patient_data: RegularPatientCreateSchema
    ) -> RegularPatient:
        """Create a new regular patient."""
        if patient_data.facility_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Facility ID is required to create a patient.",
            )
        self._assert_facility_access(patient_data.facility_id)

        existing = await self.repo.get_patient_by_phone(
            patient_data.phone, patient_data.facility_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A patient with this phone number already exists in this facility.",
            )

        patient_dict = patient_data.model_dump()
        identifiers = patient_dict.pop("identifiers", []) or []
        patient_dict["name"] = self._display_name_from_identity(patient_dict)
        patient_dict["patient_type"] = PatientType.REGULAR
        patient_dict["status"] = PatientStatus.ACTIVE

        db_patient = RegularPatient(**patient_dict)
        self._attach_identity_children(db_patient, identifiers)
        return await self.repo.create_regular_patient(db_patient)

    async def get_regular_patient(self, patient_id: uuid.UUID) -> RegularPatient:
        """Get regular patient by ID."""
        patient = await self.repo.get_regular_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regular patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        return patient

    async def update_regular_patient(
        self,
        updated_by_id: uuid.UUID,
        patient_id: uuid.UUID,
        update_data: RegularPatientUpdateSchema,
    ) -> RegularPatient:
        """Update regular patient."""
        patient = await self.repo.get_regular_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regular patient not found.",
            )
        self._assert_facility_access(patient.facility_id)

        update_dict = update_data.model_dump(exclude_unset=True)

        if "phone" in update_dict and update_dict["phone"] != patient.phone:
            existing = await self.repo.get_patient_by_phone(
                update_dict["phone"], patient.facility_id
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A patient with this phone number already exists.",
                )

        identity_fields = {"first_name", "last_name", "preferred_name"}
        if "name" not in update_dict and identity_fields.intersection(update_dict):
            merged = {
                "name": patient.name,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "preferred_name": patient.preferred_name,
            }
            merged.update(update_dict)
            update_dict["name"] = self._display_name_from_identity(merged)

        for field, value in update_dict.items():
            setattr(patient, field, value)

        return await self.repo.update_regular_patient(updated_by_id, patient)

    async def get_patient(self, patient_id: uuid.UUID):
        """Get a patient by ID, automatically returning the current subtype."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        return patient

    # =========================================================================
    # Common patient
    # =========================================================================

    async def list_patients_paginated(
        self,
        facility_id: Optional[uuid.UUID] = None,
        patient_type: Optional[str] = None,
        patient_status: Optional[str] = None,
        delivery_date_field: Optional[str] = None,
        delivery_window_days: Optional[int] = None,
        delivery_window_months: Optional[int] = None,
        delivery_date_from: Optional[date] = None,
        delivery_date_to: Optional[date] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[List, int]:
        """Paginated patient list with validation."""
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page number must be greater than 0.",
            )
        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page size must be between 1 and 100.",
            )
        if patient_type and patient_type not in ("pregnant", "regular"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid patient_type. Must be 'pregnant' or 'regular'.",
            )
        if patient_status:
            try:
                PatientStatus(patient_status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid patient_status. Must be one of: {[s.value for s in PatientStatus]}.",
                )

        delivery_start_date, delivery_end_date = self._delivery_date_range(
            delivery_date_field,
            delivery_window_days,
            delivery_window_months,
            delivery_date_from,
            delivery_date_to,
        )

        facility_id = self._scope_facility_filter(facility_id)
        skip = (page - 1) * page_size
        return await self.repo.list_patients_paginated(
            facility_id=facility_id,
            patient_type=patient_type,
            patient_status=patient_status,
            delivery_date_field=delivery_date_field,
            delivery_start_date=delivery_start_date,
            delivery_end_date=delivery_end_date,
            skip=skip,
            limit=page_size,
        )

    async def delete_patient(self, patient_id: uuid.UUID) -> bool:
        """Soft delete a patient."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        self._assert_facility_access(patient.facility_id)
        await self.repo.delete_patient(patient)
        return True

    # =========================================================================
    # Pregnancy
    # =========================================================================

    async def open_pregnancy(
        self,
        patient_id: uuid.UUID,
        pregnancy_data: PregnancyCreateSchema,
        updated_by_id: uuid.UUID,
    ) -> Pregnancy:
        """
        Open a new pregnancy episode for a returning pregnant patient.

        Raises 404 if patient not found, 400 if she already has an active
        pregnancy (enforced by PregnantPatient.open_new_pregnancy()).
        """
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        self._assert_facility_access(patient.facility_id)

        try:
            pregnancy = patient.open_new_pregnancy()
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )

        # Apply provided clinical data.
        if pregnancy_data.lmp_date:
            pregnancy.lmp_date = pregnancy_data.lmp_date
        if pregnancy_data.expected_delivery_date:
            pregnancy.expected_delivery_date = pregnancy_data.expected_delivery_date
        if pregnancy_data.gestational_age_weeks is not None:
            pregnancy.gestational_age_weeks = pregnancy_data.gestational_age_weeks
        if pregnancy_data.risk_factors:
            pregnancy.risk_factors = pregnancy_data.risk_factors
        if pregnancy_data.notes:
            pregnancy.notes = pregnancy_data.notes

        # Persist the updated gravida count and the new Pregnancy row.
        await self.repo.update_pregnant_patient(updated_by_id, patient)
        created_pregnancy = await self.repo.create_pregnancy(pregnancy)

        # Generate delivery reminders if EDD was provided when opening the episode
        if created_pregnancy.expected_delivery_date:
            patient_record = await self.repo.get_pregnant_patient_by_id(patient_id)
            patient_name = patient_record.name if patient_record else "Dear patient"
            rows = build_reminder_rows(
                patient_id=patient_id,
                due_date=created_pregnancy.expected_delivery_date,
                reminder_type=ReminderType.DELIVERY_WEEK,
                patient_name=patient_name,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return created_pregnancy

    async def get_pregnancy(self, pregnancy_id: uuid.UUID) -> Pregnancy:
        """Get a pregnancy episode by ID."""
        pregnancy = await self.repo.get_pregnancy_by_id(pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        await self._assert_pregnancy_access(pregnancy_id)
        return pregnancy

    async def list_patient_pregnancies(
        self, patient_id: uuid.UUID
    ) -> List[Pregnancy]:
        """List all pregnancy episodes for a patient."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        return await self.repo.get_patient_pregnancies(patient_id)

    async def update_pregnancy(
        self,
        pregnancy_id: uuid.UUID,
        update_data: PregnancyUpdateSchema,
    ) -> Pregnancy:
        """Update pregnancy episode data.

        Staff can update active pregnancies. Closed pregnancy corrections are
        intentionally admin-only because they alter finalized birth/outcome
        documentation.
        """
        pregnancy = await self.repo.get_pregnancy_by_id(pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        await self._assert_pregnancy_access(pregnancy_id)
        self._assert_closed_pregnancy_edit_allowed(pregnancy)

        update_dict = update_data.model_dump(exclude_unset=True)

        # Track whether EDD is actually changing before applying updates
        edd_changed = (
            "expected_delivery_date" in update_dict
            and update_dict["expected_delivery_date"] != pregnancy.expected_delivery_date
        )

        for field, value in update_dict.items():
            setattr(pregnancy, field, value)

        updated = await self.repo.update_pregnancy(pregnancy)

        # Regenerate delivery reminders when EDD is set or changed
        if edd_changed and updated.expected_delivery_date:
            patient = await self.repo.get_pregnant_patient_by_id(updated.patient_id)
            patient_name = patient.name if patient else "Dear patient"

            # Cancel all pending delivery reminders for this patient first
            await cancel_pending_reminders(
                db=self.repo.db,
                patient_id=updated.patient_id,
                reminder_type=ReminderType.DELIVERY_WEEK,
            )

            # Build and persist the fresh escalating reminder set
            rows = build_reminder_rows(
                patient_id=updated.patient_id,
                due_date=updated.expected_delivery_date,
                reminder_type=ReminderType.DELIVERY_WEEK,
                patient_name=patient_name,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return updated

    async def close_pregnancy(
        self,
        pregnancy_id: uuid.UUID,
        close_data: PregnancyCloseSchema,
        closing_user_id: uuid.UUID,
    ) -> Pregnancy:
        """
        Close an active pregnancy episode with a clinical outcome.

        Also updates para on the parent PregnantPatient when appropriate.
        """
        pregnancy = await self.repo.get_pregnancy_by_id(pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        await self._assert_pregnancy_access(pregnancy_id)
        if not pregnancy.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This pregnancy episode is already closed.",
            )

        # Update the episode itself.
        pregnancy.close(
            outcome=close_data.outcome,
            delivery_date=close_data.delivery_date,
        )

        # Update para on the parent patient if warranted.
        if close_data.increment_para:
            patient = await self.repo.get_pregnant_patient_by_id(pregnancy.patient_id)
            if patient:
                patient.para += 1
                await self.repo.update_pregnant_patient(closing_user_id, patient)

        return await self.repo.update_pregnancy(pregnancy)

    # =========================================================================
    # Child
    # =========================================================================

    async def create_child(self, child_data: ChildCreateSchema) -> Child:
        """
        Create a child record linked to a specific pregnancy episode.

        Automatically calculates the six-month checkup date from date_of_birth.
        Verifies the pregnancy exists before creating the child.
        """
        if child_data.pregnancy_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pregnancy ID is required to create a child record.",
            )

        pregnancy = await self.repo.get_pregnancy_by_id(child_data.pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        await self._assert_pregnancy_access(child_data.pregnancy_id)
        self._assert_child_can_be_added_to_pregnancy(pregnancy)

        child_dict = child_data.model_dump()
        child_dict["six_month_checkup_date"] = (
            child_data.date_of_birth + timedelta(days=180)
        )

        child = Child(**child_dict)
        self.db.add(child)
        await self.db.flush()  # flush to get the child ID for logging
        await self.db.refresh(child, ["pregnancy"])

        # Generate 6-month checkup reminders immediately — the date is always
        # set at creation, so no need to wait for an update.
        if child.six_month_checkup_date and child.pregnancy:
            patient = await self.repo.get_pregnant_patient_by_id(child.pregnancy.patient_id)
            patient_name = patient.name if patient else "Dear patient"

            rows = build_reminder_rows(
                patient_id=child.pregnancy.patient_id,
                due_date=child.six_month_checkup_date,
                reminder_type=ReminderType.CHILD_6MONTH_CHECKUP,
                patient_name=patient_name,
                child_id=child.id,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return child

    async def get_child(self, child_id: uuid.UUID) -> Child:
        """Get child by ID."""
        child = await self.repo.get_child_by_id(child_id)
        if not child:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child record not found.",
            )
        await self._assert_child_access(child_id)
        return child

    async def update_child(
        self,
        child_id: uuid.UUID,
        update_data: ChildUpdateSchema,
        updated_by_id: Optional[uuid.UUID] = None,
    ) -> Child:
        """Update child monitoring fields."""
        child = await self.repo.get_child_by_id(child_id)
        if not child:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child record not found.",
            )
        await self._assert_child_access(child_id)
        update_dict = update_data.model_dump(exclude_unset=True)

        pregnancy = await self.repo.get_pregnancy_by_id(child.pregnancy_id)
        if pregnancy and not pregnancy.is_active and not self._is_admin_context():
            birth_detail_fields = {"name", "sex", "notes"}
            if birth_detail_fields.intersection(update_dict):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Birth details for a closed pregnancy can only be corrected by an admin. "
                        "Six-month checkup and Hep B monitoring fields remain editable."
                    ),
                )

        # Stamp the audit field regardless of whether the caller included it
        # in the schema body — always prefer the injected auth-context value.
        if updated_by_id is not None:
            update_dict["updated_by_id"] = updated_by_id

        # Detect if six_month_checkup_date is being set or changed
        checkup_changed = (
            "six_month_checkup_date" in update_dict
            and update_dict["six_month_checkup_date"] != child.six_month_checkup_date
        )

        for field, value in update_dict.items():
            setattr(child, field, value)

        updated_child = await self.repo.update_child(child)

        # Regenerate checkup reminders when the date changes and checkup isn't done yet
        if checkup_changed and updated_child.six_month_checkup_date and not updated_child.six_month_checkup_completed:
            patient_name = "Dear patient"
            if pregnancy:
                patient = await self.repo.get_pregnant_patient_by_id(pregnancy.patient_id)
                if patient:
                    patient_name = patient.name

            # Cancel existing pending checkup reminders for this specific child
            await cancel_pending_reminders(
                db=self.repo.db,
                patient_id=pregnancy.patient_id if pregnancy else updated_child.pregnancy_id,
                reminder_type=ReminderType.CHILD_6MONTH_CHECKUP,
                child_id=updated_child.id,
            )

            # Build and persist the fresh escalating reminder set
            rows = build_reminder_rows(
                patient_id=pregnancy.patient_id if pregnancy else updated_child.pregnancy_id,
                due_date=updated_child.six_month_checkup_date,
                reminder_type=ReminderType.CHILD_6MONTH_CHECKUP,
                patient_name=patient_name,
                child_id=updated_child.id,
            )
            if rows:
                await self.repo.bulk_create_reminders(rows)

        return updated_child

    async def list_pregnancy_children(
        self, pregnancy_id: uuid.UUID
    ) -> List[Child]:
        """List all children born from a specific pregnancy episode."""
        pregnancy = await self.repo.get_pregnancy_by_id(pregnancy_id)
        if not pregnancy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnancy not found.",
            )
        await self._assert_pregnancy_access(pregnancy_id)
        return await self.repo.get_pregnancy_children(pregnancy_id)

    async def list_mother_children(self, patient_id: uuid.UUID) -> List[Child]:
        """List all children for a mother across all her pregnancies."""
        patient = await self.repo.get_pregnant_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pregnant patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        return await self.repo.get_mother_children(patient_id)

    # =========================================================================
    # Prescription
    # =========================================================================

    async def create_prescription(
        self, prescription_data: PrescriptionCreateSchema
    ) -> Prescription:
        if prescription_data.patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient ID is required to create a prescription.",
            )
        patient = await self.repo.get_patient_by_id(prescription_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        self._assert_facility_access(patient.facility_id)
        prescription_dict = prescription_data.model_dump()
        prescription_dict["is_active"] = True
        return await self.repo.create_prescription(Prescription(**prescription_dict))

    async def get_prescription(self, prescription_id: uuid.UUID) -> Prescription:
        prescription = await self.repo.get_prescription_by_id(prescription_id)
        if not prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found.",
            )
        return prescription

    async def update_prescription(
        self, prescription_id: uuid.UUID, update_data: PrescriptionUpdateSchema
    ) -> Prescription:
        prescription = await self.repo.get_prescription_by_id(prescription_id)
        if not prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found.",
            )
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(prescription, field, value)
        return await self.repo.update_prescription(prescription)

    async def list_patient_prescriptions(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[Prescription]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        self._assert_facility_access(patient.facility_id)
        return await self.repo.get_patient_prescriptions(patient_id, active_only)

    # =========================================================================
    # Medication schedule
    # =========================================================================

    async def create_medication_schedule(
        self, schedule_data: MedicationScheduleCreateSchema
    ) -> MedicationSchedule:
        if schedule_data.patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient ID is required to create a medication schedule.",
            )
        patient = await self.repo.get_patient_by_id(schedule_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        self._assert_facility_access(patient.facility_id)
        schedule_dict = schedule_data.model_dump()
        schedule_dict.update(
            is_completed=False,
            lab_review_scheduled=False,
            lab_review_completed=False,
        )
        return await self.repo.create_medication_schedule(
            MedicationSchedule(**schedule_dict)
        )

    async def get_medication_schedule(
        self, schedule_id: uuid.UUID
    ) -> MedicationSchedule:
        schedule = await self.repo.get_medication_schedule_by_id(schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medication schedule not found.",
            )
        return schedule

    async def update_medication_schedule(
        self, schedule_id: uuid.UUID, update_data: MedicationScheduleUpdateSchema
    ) -> MedicationSchedule:
        schedule = await self.repo.get_medication_schedule_by_id(schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Medication schedule not found.",
            )
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(schedule, field, value)
        return await self.repo.update_medication_schedule(schedule)

    async def list_patient_medication_schedules(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[MedicationSchedule]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        self._assert_facility_access(patient.facility_id)
        return await self.repo.get_patient_medication_schedules(patient_id, active_only)

    # =========================================================================
    # Patient allergy
    # =========================================================================

    async def create_patient_allergy(
        self,
        patient_id: uuid.UUID,
        allergy_data: PatientAllergySchema,
        recorded_by_id: uuid.UUID,
    ) -> PatientAllergy:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        allergy_dict = allergy_data.model_dump(exclude={"id"})
        allergy_dict["allergen"] = allergy_dict["allergen"].strip()
        allergy_dict["patient_id"] = patient_id
        allergy_dict["recorded_by_id"] = recorded_by_id
        try:
            return await self.repo.create_patient_allergy(PatientAllergy(**allergy_dict))
        except IntegrityError as e:
            await self.db.rollback()
            if "uq_patient_allergy_allergen" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This allergy is already recorded for the patient.",
                )
            raise

    async def list_patient_allergies(
        self, patient_id: uuid.UUID, active_only: bool = False
    ) -> List[PatientAllergy]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        return await self.repo.get_patient_allergies(patient_id, active_only)

    async def update_patient_allergy(
        self,
        allergy_id: uuid.UUID,
        update_data: PatientAllergyUpdateSchema,
    ) -> PatientAllergy:
        allergy = await self.repo.get_patient_allergy_by_id(allergy_id)
        if not allergy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Allergy record not found.",
            )
        patient = await self.repo.get_patient_by_id(allergy.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(allergy, field, value)
        return await self.repo.update_patient_allergy(allergy)

    # =========================================================================
    # Patient lab tests
    # =========================================================================

    async def create_patient_lab_test(
        self,
        patient_id: uuid.UUID,
        lab_test_data: PatientLabTestCreateSchema,
        ordered_by_id: uuid.UUID,
    ) -> PatientLabTest:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )
        self._assert_facility_access(patient.facility_id)

        lab_test_dict = lab_test_data.model_dump(exclude={"results"})
        lab_test_dict["patient_id"] = patient_id
        lab_test_dict["ordered_by_id"] = ordered_by_id
        definition = None
        if lab_test_dict.get("test_definition_id"):
            definition = await self.repo.get_lab_test_definition_by_id(
                lab_test_dict["test_definition_id"]
            )
            if not definition or not definition.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected lab test definition is not available.",
                )
            lab_test_dict["test_name"] = lab_test_dict.get("test_name") or definition.name

        if not lab_test_dict.get("test_name"):
            lab_test_dict["test_name"] = self._default_lab_test_name(
                lab_test_dict["test_type"]
            )

        results = []
        for result_data in lab_test_data.results:
            result = PatientLabResult(**result_data.model_dump())
            results.append(result)

        if results and lab_test_dict.get("status") in {
            LabTestStatus.ORDERED,
            LabTestStatus.IN_PROGRESS,
        }:
            lab_test_dict["status"] = LabTestStatus.DRAFT

        if lab_test_dict.get("status") == LabTestStatus.FILED:
            lab_test_dict["reported_at"] = lab_test_dict.get("reported_at") or datetime.now(timezone.utc)

        if lab_test_dict.get("status") == LabTestStatus.VERIFIED:
            if not self._can_verify_lab_results():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only a supervisor or administrator can verify lab results.",
                )
            lab_test_dict["reviewed_by_id"] = ordered_by_id
            lab_test_dict["reported_at"] = lab_test_dict.get("reported_at") or datetime.now(timezone.utc)

        lab_test = PatientLabTest(**lab_test_dict)
        for result in results:
            await self._apply_parameter_definition_to_result(result, lab_test)
        lab_test.results.extend(results)
        return await self.repo.create_patient_lab_test(lab_test)

    async def get_patient_lab_test(self, lab_test_id: uuid.UUID) -> PatientLabTest:
        lab_test = await self.repo.get_patient_lab_test_by_id(lab_test_id)
        if not lab_test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lab test not found.",
            )
        await self._assert_lab_test_access(lab_test_id)
        return lab_test

    async def list_patient_lab_tests(
        self,
        patient_id: uuid.UUID,
        test_type: Optional[str] = None,
    ) -> List[PatientLabTest]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )
        self._assert_facility_access(patient.facility_id)
        if test_type:
            try:
                LabTestType(test_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid test_type. Must be one of: hep_b, rft, lft.",
                )
        return await self.repo.get_patient_lab_tests(patient_id, test_type)

    async def update_patient_lab_test(
        self,
        lab_test_id: uuid.UUID,
        update_data: PatientLabTestUpdateSchema,
        reviewed_by_id: uuid.UUID,
    ) -> PatientLabTest:
        lab_test = await self.repo.get_patient_lab_test_by_id(lab_test_id)
        if not lab_test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lab test not found.",
            )
        await self._assert_lab_test_access(lab_test_id)

        update_dict = update_data.model_dump(exclude_unset=True)
        if "test_definition_id" in update_dict and not update_dict.get("test_name"):
            definition = await self.repo.get_lab_test_definition_by_id(
                update_dict["test_definition_id"]
            )
            if not definition or not definition.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected lab test definition is not available.",
                )
            update_dict["test_name"] = definition.name
        if "test_type" in update_dict and not update_dict.get("test_name") and update_dict.get("test_type"):
            update_dict["test_name"] = self._default_lab_test_name(
                update_dict["test_type"]
            )
        for field, value in update_dict.items():
            setattr(lab_test, field, value)

        if update_dict.get("status") == LabTestStatus.VERIFIED:
            if not self._can_verify_lab_results():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only a supervisor or administrator can verify lab results.",
                )
            lab_test.reviewed_by_id = reviewed_by_id
            lab_test.reported_at = lab_test.reported_at or datetime.now(timezone.utc)
        elif update_dict.get("status") == LabTestStatus.FILED:
            lab_test.reviewed_by_id = None
            lab_test.reported_at = lab_test.reported_at or datetime.now(timezone.utc)
        elif update_dict.get("status") == LabTestStatus.DRAFT:
            lab_test.reviewed_by_id = None

        return await self.repo.update_patient_lab_test(lab_test)

    async def add_patient_lab_result(
        self,
        lab_test_id: uuid.UUID,
        result_data: PatientLabResultCreateSchema,
        reviewed_by_id: uuid.UUID,
    ) -> PatientLabTest:
        lab_test = await self.repo.get_patient_lab_test_by_id(lab_test_id)
        if not lab_test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lab test not found.",
            )
        await self._assert_lab_test_access(lab_test_id)

        lab_result = PatientLabResult(
            lab_test_id=lab_test_id,
            **result_data.model_dump(),
        )
        await self._apply_parameter_definition_to_result(lab_result, lab_test)
        await self.repo.create_patient_lab_result(lab_result)

        if lab_test.status in {
            LabTestStatus.ORDERED,
            LabTestStatus.IN_PROGRESS,
            LabTestStatus.COMPLETED,
        }:
            lab_test.status = LabTestStatus.DRAFT
        lab_test.reviewed_by_id = None
        await self.repo.update_patient_lab_test(lab_test)

        refreshed = await self.repo.get_patient_lab_test_by_id(lab_test_id)
        return refreshed

    async def update_patient_lab_result(
        self,
        lab_result_id: uuid.UUID,
        update_data: PatientLabResultUpdateSchema,
        reviewed_by_id: uuid.UUID,
    ) -> PatientLabTest:
        lab_result = await self.repo.get_patient_lab_result_by_id(lab_result_id)
        if not lab_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lab result not found.",
            )
        await self._assert_lab_result_access(lab_result_id)

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(lab_result, field, value)
        lab_test = await self.repo.get_patient_lab_test_by_id(lab_result.lab_test_id)
        await self._apply_parameter_definition_to_result(lab_result, lab_test)
        await self.repo.update_patient_lab_result(lab_result)

        if lab_test.status != LabTestStatus.VERIFIED:
            lab_test.reviewed_by_id = None
        await self.repo.update_patient_lab_test(lab_test)

        refreshed = await self.repo.get_patient_lab_test_by_id(lab_result.lab_test_id)
        return refreshed

    # =========================================================================
    # Reminder
    # =========================================================================

    async def create_reminder(
        self, reminder_data: PatientReminderCreateSchema
    ) -> PatientReminder:
        if reminder_data.patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Patient ID is required to create a reminder.",
            )
        patient = await self.repo.get_patient_by_id(reminder_data.patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        self._assert_facility_access(patient.facility_id)
        if reminder_data.child_id:
            child = await self.repo.get_child_by_id(reminder_data.child_id)
            if not child:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Child not found."
                )
            await self._assert_child_access(reminder_data.child_id)
        reminder_dict = reminder_data.model_dump()
        reminder_dict["status"] = "pending"
        return await self.repo.create_reminder(PatientReminder(**reminder_dict))

    async def create_facility_notification_for_reminder(
        self, reminder: PatientReminder
    ) -> Optional[FacilityNotification]:
        existing = await self.repo.get_facility_notification_by_reminder(reminder.id)
        if existing:
            return existing
        patient = await self.repo.get_patient_by_id(reminder.patient_id)
        if not patient:
            return None
        priority = "urgent" if reminder.scheduled_date <= datetime.now(timezone.utc).date() else "high"
        reminder_type = getattr(reminder.reminder_type, "value", reminder.reminder_type)
        patient_type = getattr(patient.patient_type, "value", patient.patient_type)
        notification = FacilityNotification(
            facility_id=patient.facility_id,
            patient_id=patient.id,
            reminder_id=reminder.id,
            title="Call patient for reminder follow-up",
            message=(
                f"{patient.name} received a {str(reminder_type).replace('_', ' ')} "
                f"reminder. Please call to confirm they understood and can attend."
            ),
            notification_type="patient_reminder_call",
            priority=priority,
            status="unread",
            action_label="Open patient",
            action_url=f"/patients/{patient.id}?type={str(patient_type).lower()}",
            due_date=reminder.scheduled_date,
            patient_phone=patient.phone,
        )
        return await self.repo.create_facility_notification(notification)

    async def get_reminder(self, reminder_id: uuid.UUID) -> PatientReminder:
        reminder = await self.repo.get_reminder_by_id(reminder_id)
        if not reminder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found."
            )
        return reminder

    async def update_reminder(
        self, reminder_id: uuid.UUID, update_data: PatientReminderUpdateSchema
    ) -> PatientReminder:
        reminder = await self.repo.get_reminder_by_id(reminder_id)
        if not reminder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found."
            )
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(reminder, field, value)
        updated = await self.repo.update_reminder(reminder)
        if updated.status == ReminderStatus.SENT:
            await self.create_facility_notification_for_reminder(updated)
        return updated

    async def list_patient_reminders(
        self, patient_id: uuid.UUID, pending_only: bool = False
    ) -> List[PatientReminder]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        self._assert_facility_access(patient.facility_id)
        return await self.repo.get_patient_reminders(patient_id, pending_only)

    async def list_facility_notifications(
        self,
        status_filter: Optional[str] = None,
        unresolved_only: bool = True,
        limit: int = 50,
    ) -> List[FacilityNotification]:
        facility_id = self._current_facility_id()
        if facility_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not assigned to a facility.",
            )
        return await self.repo.list_facility_notifications(
            facility_id=facility_id,
            status_filter=status_filter,
            unresolved_only=unresolved_only,
            limit=limit,
        )

    async def update_facility_notification(
        self,
        notification_id: uuid.UUID,
        update_data: FacilityNotificationUpdateSchema,
    ) -> FacilityNotification:
        notification = await self.repo.get_facility_notification_by_id(notification_id)
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )
        self._assert_facility_access(notification.facility_id)
        changes = update_data.model_dump(exclude_unset=True)
        now = datetime.now(timezone.utc)
        for field, value in changes.items():
            setattr(notification, field, value)
        if changes.get("status") in {"acknowledged", "in_progress"} and notification.acknowledged_at is None:
            notification.acknowledged_at = now
        if changes.get("status") in {"resolved", "dismissed"}:
            notification.resolved_at = now
        return await self.repo.update_facility_notification(notification)

    async def list_patient_reminders_paginated(
        self,
        patient_id: uuid.UUID,
        pagination,  # PaginationParams
        status_filter: Optional[str] = None,
        upcoming_only: bool = False,
    ):
        """Get paginated reminders with smart filtering and ordering."""
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
            )
        self._assert_facility_access(patient.facility_id)
        return await self.repo.get_patient_reminders_paginated(
            patient_id=patient_id,
            pagination=pagination,
            status_filter=status_filter,
            upcoming_only=upcoming_only,
        )

    # =========================================================================
    # Diagnosis
    # =========================================================================

    async def create_diagnosis(
                self, diagnosis_data: DiagnosisCreateSchema
        ) -> Diagnosis:
        if diagnosis_data.patient_id is None:
            raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Patient ID is required to create a diagnosis.",
                )
        patient = await self.repo.get_patient_by_id(diagnosis_data.patient_id)
        if not patient:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
                )
        self._assert_facility_access(patient.facility_id)
        diagnosis_dict = diagnosis_data.model_dump()
        return await self.repo.create_diagnosis(Diagnosis(**diagnosis_dict))

    async def get_diagnosis(self, diagnosis_id: uuid.UUID) -> Diagnosis:
        diagnosis = await self.repo.get_diagnosis_by_id(diagnosis_id)
        if not diagnosis:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found."
                )
        await self._assert_diagnosis_access(diagnosis_id)
        return diagnosis

    async def update_diagnosis(
                self, diagnosis_id: uuid.UUID, update_data: DiagnosisUpdateSchema
        ) -> Diagnosis:
        diagnosis = await self.repo.get_diagnosis_by_id(diagnosis_id)
        if not diagnosis:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found."
                )
        await self._assert_diagnosis_access(diagnosis_id)
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(diagnosis, field, value)
        return await self.repo.update_diagnosis(diagnosis)

    async def delete_diagnosis(self, diagnosis_id: uuid.UUID) -> None:
        diagnosis = await self.repo.get_diagnosis_by_id(diagnosis_id)
        if not diagnosis:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found."
                )
        await self._assert_diagnosis_access(diagnosis_id)
        diagnosis.is_deleted = True
        from datetime import datetime, timezone
        diagnosis.deleted_at = datetime.now(timezone.utc)
        await self.repo.update_diagnosis(diagnosis)

    async def list_patient_diagnoses(
                self, patient_id: uuid.UUID
        ) -> list[Diagnosis]:
        patient = await self.repo.get_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
                )
        self._assert_facility_access(patient.facility_id)
        return await self.repo.get_patient_diagnoses(patient_id)

    # =========================================================================
    # Re-register as pregnant
    # =========================================================================

    async def re_register_as_pregnant(
        self,
        user_id: uuid.UUID,
        patient_id: uuid.UUID,
        pregnancy_data: "ReRegisterAsPregnantSchema",
    ) -> PregnantPatient:
        """
        Re-register a regular patient as pregnant (second or later pregnancy).

        The pregnant_patients row is never deleted on conversion — it stays for
        history. So re-registration only needs to:
          1. UPDATE the discriminator back to PREGNANT.
          2. Load the existing PregnantPatient ORM object.
          3. Call open_new_pregnancy() — increments gravida, creates new episode.
          4. Apply any clinical data from the request.
          5. Commit. No INSERT into pregnant_patients needed.
        """
        from sqlalchemy import text as _text, select as _select
        from app.core.utils import logger

        # FIX: expunge_all() instead of expire_all().
        # expire_all() only marks attributes stale — it does NOT evict objects
        # from the identity map. If a prior request in the same worker loaded
        # this patient as PregnantPatient, get_regular_patient_by_id() would
        # encounter a discriminator mismatch, silently return None, and cause
        # a false 409. expunge_all() fully clears the identity map so every
        # subsequent query builds fresh ORM instances from the current DB state.
        self.db.expunge_all()

        regular = await self.repo.get_regular_patient_by_id(patient_id)
        if not regular:
            base = await self.repo.get_patient_by_id(patient_id)
            if base:
                self._assert_facility_access(base.facility_id)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Patient is already registered as pregnant.",
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regular patient not found.",
            )
        self._assert_facility_access(regular.facility_id)
        if regular.sex != Sex.FEMALE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only female patients can be re-registered as pregnant.",
            )

        # Step 1: Flip discriminator back to PREGNANT.
        await self.db.execute(
            _text("""
                UPDATE patients
                SET patient_type  = 'PREGNANT',
                    status        = 'ACTIVE',
                    updated_by_id = :user_id
                WHERE id = :patient_id
            """),
            {"user_id": str(user_id), "patient_id": str(patient_id)},
        )
        await self.db.commit()

        # FIX: expunge_all() instead of expire_all().
        # This is the critical call. After the raw SQL UPDATE above, the identity
        # map still holds the RegularPatient instance for this UUID. expire_all()
        # would refresh its attribute values but cannot change its Python class.
        # The subsequent select(PregnantPatient) would hit the identity map,
        # find the cached RegularPatient, and return it — causing the
        # AttributeError: 'RegularPatient' object has no attribute 'open_new_pregnancy'.
        # expunge_all() fully evicts all objects so SQLAlchemy builds a fresh
        # PregnantPatient from the updated DB row.
        self.db.expunge_all()

        # Load the existing PregnantPatient row with all relationships the response
        # schema needs (facility, created_by, updated_by, pregnancies).
        # All relationships are lazy="noload" — they MUST be selectinload'd here.
        from sqlalchemy.orm import selectinload as _sil
        result = await self.db.execute(
            _select(PregnantPatient)
            .where(PregnantPatient.id == patient_id)
            .options(
                _sil(PregnantPatient.facility),
                _sil(PregnantPatient.created_by),
                _sil(PregnantPatient.updated_by),
                _sil(PregnantPatient.pregnancies),
                _sil(PregnantPatient.identifiers),
                _sil(PregnantPatient.allergies_structured),
            )
        )
        pregnant_patient = result.scalars().first()
        
        # CRITICAL FIX: If pregnant_patients row is missing, create it now.
        # This can happen if the initial conversion had data inconsistencies.
        if not pregnant_patient:
            logger.log_warning({
                "event": "pregnant_patients_row_missing_during_reregistration",
                "patient_id": str(patient_id),
                "detail": "Creating missing pregnant_patients row"
            })
            
            # Create the missing subtype row with default/inherited values
            await self.db.execute(
                _text("""
                    INSERT INTO pregnant_patients
                        (id, gravida, para)
                    VALUES
                        (:id, 1, :para)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": str(patient_id),
                    "para": regular.para if hasattr(regular, "para") else 0,
                },
            )
            await self.db.commit()
            self.db.expunge_all()
            
            # Retry load
            result = await self.db.execute(
                _select(PregnantPatient)
                .where(PregnantPatient.id == patient_id)
                .options(
                    _sil(PregnantPatient.facility),
                    _sil(PregnantPatient.created_by),
                    _sil(PregnantPatient.updated_by),
                    _sil(PregnantPatient.pregnancies),
                    _sil(PregnantPatient.identifiers),
                    _sil(PregnantPatient.allergies_structured),
                )
            )
            pregnant_patient = result.scalars().first()
        
        if not pregnant_patient:
            logger.log_error({
                "event": "re_register_pregnant_fatal_error",
                "patient_id": str(patient_id),
                "detail": "Still could not load PregnantPatient after row creation"
            })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Re-registration failed: unable to load patient data.",
            )

        # Step 3: Open the new episode via the model's business logic.
        try:
            pregnancy = pregnant_patient.open_new_pregnancy()
        except ValueError as e:
            logger.log_warning({
                "event": "pregnancy_creation_failed",
                "patient_id": str(patient_id),
                "error": str(e)
            })
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )

        # Apply optional clinical data.
        if pregnancy_data.lmp_date:
            pregnancy.lmp_date = pregnancy_data.lmp_date
        if pregnancy_data.expected_delivery_date:
            pregnancy.expected_delivery_date = pregnancy_data.expected_delivery_date
        if pregnancy_data.gestational_age_weeks is not None:
            pregnancy.gestational_age_weeks = pregnancy_data.gestational_age_weeks
        if pregnancy_data.risk_factors:
            pregnancy.risk_factors = pregnancy_data.risk_factors
        if pregnancy_data.notes:
            pregnancy.notes = pregnancy_data.notes

        pregnant_patient.updated_by_id = user_id
        self.db.add(pregnant_patient)
        await self.db.commit()

        logger.log_info({
            "event": "pregnancy_episode_opened",
            "patient_id": str(patient_id),
            "gravida": pregnant_patient.gravida,
        })

        # After commit, do a final SELECT with all eager loads so the response
        # schema can access facility/created_by/updated_by/pregnancies without
        # triggering implicit lazy loads on an async session (MissingGreenlet).
        self.db.expunge_all()
        final = await self.db.execute(
            _select(PregnantPatient)
            .where(PregnantPatient.id == patient_id)
            .options(
                _sil(PregnantPatient.facility),
                _sil(PregnantPatient.created_by),
                _sil(PregnantPatient.updated_by),
                _sil(PregnantPatient.pregnancies),
                _sil(PregnantPatient.identifiers),
                _sil(PregnantPatient.allergies_structured),
            )
        )
        return final.scalars().first()
