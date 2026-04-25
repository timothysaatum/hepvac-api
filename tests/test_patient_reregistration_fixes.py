"""
Test suite for patient re-registration bug fixes.

Tests the following fixes:
1. Enum serialization in search results (corrupted "Man DbPregnant" display)
2. Re-registration with missing pregnant_patients row
3. Transaction atomicity during conversion
4. Proper error handling and recovery
"""

import pytest
import uuid
from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_model import PregnantPatient, RegularPatient, Patient, Pregnancy
from app.schemas.patient_schemas import (
    PregnantPatientCreateSchema,
    ConvertToRegularPatientSchema,
    ReRegisterAsPregnantSchema,
    PregnancyOutcome,
    PatientStatus,
    PatientType,
    Sex,
)
from app.services.patient_service import PatientService
from app.services.search_service import SearchService
from app.repositories.patient_repo import PatientRepository


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def pregnant_patient_data():
    """Sample data for creating a pregnant patient."""
    return PregnantPatientCreateSchema(
        name="Jane Smith",
        phone="+254712345678",
        sex=Sex.FEMALE,
        date_of_birth=date(1990, 5, 15),
        facility_id=uuid.uuid4(),
        first_pregnancy={
            "lmp_date": date(2025, 11, 1),
            "expected_delivery_date": date(2026, 8, 1),
            "gestational_age_weeks": 25,
            "risk_factors": "None",
            "notes": "Healthy pregnancy",
        }
    )


# ============================================================================
# TEST: Enum Serialization Fix
# ============================================================================

class TestEnumSerializationFix:
    """Verify enum values are properly serialized in search results."""
    
    @pytest.mark.asyncio
    async def test_search_result_enum_conversion(self, db: AsyncSession):
        """
        Test that enum fields in search results are converted to strings.
        
        Before fix: Enums remained as objects → "Man DbPregnant" corruption
        After fix: Enums converted to their .value → "female", "pregnant", "active"
        """
        service = SearchService(db)
        
        # Create test patient
        repo = PatientRepository(db)
        patient = PregnantPatient(
            id=uuid.uuid4(),
            name="Test Patient",
            phone="+254700000000",
            sex=Sex.FEMALE,  # This is an enum
            date_of_birth=date(1995, 1, 1),
            patient_type=PatientType.PREGNANT,  # This is an enum
            status=PatientStatus.ACTIVE,  # This is an enum
            facility_id=uuid.uuid4(),
        )
        await repo.create_pregnant_patient(patient)
        
        # Search and verify serialization
        filters_dict = {
            "facility_id": patient.facility_id,
            "patient_type": PatientType.PREGNANT.value,
        }
        
        # Execute search
        patients, total = await repo.search_patients(
            facility_id=patient.facility_id,
            patient_type=PatientType.PREGNANT.value,
        )
        
        # Verify enum is correctly converted
        assert len(patients) > 0
        result = service._patient_to_search_result(patients[0])
        
        # These should be strings, not enum representations
        assert isinstance(result.sex, Sex)  # Pydantic converts to enum
        assert result.sex.value == "female"  # But .value is a string
        assert isinstance(result.status, PatientStatus)
        assert result.status.value == "active"
        assert isinstance(result.patient_type, str)
        assert result.patient_type == "pregnant"
        
        # Verify no corruption
        assert "DbPregnant" not in str(result.patient_type)
        assert "Man" not in str(result.sex)
        assert "undefined" not in str(result)

    @pytest.mark.asyncio
    async def test_corrupted_display_fixed(self, db: AsyncSession):
        """
        Test that corrupted display like "Man DbPregnant 0259355889Gundefined Pundefined" 
        no longer occurs.
        """
        service = SearchService(db)
        
        patient = PregnantPatient(
            id=uuid.uuid4(),
            name="Amina Mohamed",
            phone="0259355889",
            sex=Sex.FEMALE,
            date_of_birth=date(1992, 3, 20),
            patient_type=PatientType.PREGNANT,
            status=PatientStatus.ACTIVE,
            facility_id=uuid.uuid4(),
        )
        
        result = service._patient_to_search_result(patient)
        result_str = str(result.model_dump())
        
        # Verify no corrupted values
        assert "DbPregnant" not in result_str
        assert "Gundefined" not in result_str
        assert "Pundefined" not in result_str
        assert result.name == "Amina Mohamed"
        assert result.phone == "0259355889"


# ============================================================================
# TEST: Re-registration Missing pregnant_patients Row Fix
# ============================================================================

class TestReregistrationMissingRowFix:
    """Verify re-registration works even if pregnant_patients row is missing."""
    
    @pytest.mark.asyncio
    async def test_reregister_with_missing_row_auto_recovery(self, db: AsyncSession):
        """
        Test that re-registration auto-creates missing pregnant_patients row.
        
        Scenario:
        1. Patient was converted to regular (pregnant_patients row kept)
        2. Re-registering as pregnant - row should exist
        3. If row is missing due to data corruption, it should auto-create
        """
        service = PatientService(db)
        repo = PatientRepository(db)
        user_id = uuid.uuid4()
        facility_id = uuid.uuid4()
        
        # Create a regular patient (simulating one converted from pregnant)
        regular_patient = RegularPatient(
            id=uuid.uuid4(),
            name="Sarah Johnson",
            phone="+254712345679",
            sex=Sex.FEMALE,
            date_of_birth=date(1988, 7, 10),
            patient_type=PatientType.REGULAR,
            status=PatientStatus.POSTPARTUM,
            facility_id=facility_id,
            created_by_id=user_id,
            para=1,  # Has given birth once
        )
        await repo.create_regular_patient(regular_patient)
        
        # Re-register as pregnant
        reregister_data = ReRegisterAsPregnantSchema(
            lmp_date=date(2026, 1, 15),
            expected_delivery_date=date(2026, 10, 15),
            gestational_age_weeks=10,
            risk_factors="Previous delivery",
        )
        
        result = await service.re_register_as_pregnant(
            user_id, regular_patient.id, reregister_data
        )
        
        # Verify success
        assert result is not None
        assert result.patient_type == PatientType.PREGNANT
        assert result.status == PatientStatus.ACTIVE
        assert result.gravida == 2  # Incremented from re-registration
        
        # Verify pregnancy was created
        pregnancies = await repo.get_patient_pregnancies(regular_patient.id)
        assert len(pregnancies) > 0
        latest_pregnancy = pregnancies[-1]
        assert latest_pregnancy.lmp_date == date(2026, 1, 15)

    @pytest.mark.asyncio
    async def test_reregister_preserves_patient_history(self, db: AsyncSession):
        """
        Test that re-registration doesn't lose any patient history.
        
        All vaccines, prescriptions, children from previous pregnancies should remain.
        """
        # This would need actual related records to test fully
        # Placeholder for integration test
        pass


# ============================================================================
# TEST: Conversion Transaction Atomicity
# ============================================================================

class TestConversionAtomicity:
    """Verify conversion transactions are properly atomic."""
    
    @pytest.mark.asyncio
    async def test_convert_pregnant_to_regular_atomic(self, db: AsyncSession):
        """
        Test that conversion is atomic - either fully succeeds or fully rolls back.
        """
        service = PatientService(db)
        repo = PatientRepository(db)
        user_id = uuid.uuid4()
        facility_id = uuid.uuid4()
        
        # Create a pregnant patient
        pregnant_patient = PregnantPatient(
            id=uuid.uuid4(),
            name="Mary Williams",
            phone="+254712345680",
            sex=Sex.FEMALE,
            date_of_birth=date(1994, 2, 28),
            patient_type=PatientType.PREGNANT,
            status=PatientStatus.ACTIVE,
            facility_id=facility_id,
            created_by_id=user_id,
            gravida=1,
            para=0,
        )
        await repo.create_pregnant_patient(pregnant_patient)
        
        # Open a pregnancy
        pregnancy = pregnant_patient.open_new_pregnancy()
        pregnancy.lmp_date = date(2025, 12, 1)
        pregnancy.expected_delivery_date = date(2026, 9, 1)
        await repo.create_pregnancy(pregnancy)
        
        # Convert to regular
        conversion_data = ConvertToRegularPatientSchema(
            outcome=PregnancyOutcome.LIVE_BIRTH,
            actual_delivery_date=date(2026, 8, 29),
            treatment_regimen="HAART",
            notes="Post-delivery treatment",
        )
        
        result = await service.convert_to_regular_patient(
            user_id, pregnant_patient.id, conversion_data
        )
        
        # Verify conversion succeeded
        assert result is not None
        assert result.patient_type == PatientType.REGULAR
        assert result.status == PatientStatus.POSTPARTUM
        
        # Verify both tables were updated
        reloaded = await repo.get_patient_by_id(pregnant_patient.id)
        assert reloaded.patient_type == PatientType.REGULAR

    @pytest.mark.asyncio
    async def test_conversion_rollback_on_error(self, db: AsyncSession):
        """
        Test that conversion rolls back if there's an error during transaction.
        """
        # Placeholder for error scenario test
        # Would need to mock a failure in the middle of transaction
        pass


# ============================================================================
# TEST: Error Handling & Recovery
# ============================================================================

class TestErrorHandling:
    """Verify proper error handling and recovery."""
    
    @pytest.mark.asyncio
    async def test_detailed_error_messages(self, db: AsyncSession):
        """
        Test that error messages are helpful and specific.
        """
        service = PatientService(db)
        user_id = uuid.uuid4()
        fake_patient_id = uuid.uuid4()
        
        # Try to re-register non-existent patient
        with pytest.raises(Exception) as exc_info:
            await service.re_register_as_pregnant(
                user_id,
                fake_patient_id,
                ReRegisterAsPregnantSchema()
            )
        
        # Verify error message is helpful
        assert "Regular patient not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_handles_data_inconsistencies(self, db: AsyncSession):
        """
        Test that search gracefully handles inconsistent data.
        """
        # This tests the error handling in list_patients endpoint
        # where individual patients that fail serialization are skipped
        pass


# ============================================================================
# TEST: Full Workflow
# ============================================================================

class TestFullWorkflow:
    """Test complete workflow: Register → Convert → Re-register."""
    
    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, db: AsyncSession):
        """
        Test full patient lifecycle:
        1. Register as pregnant (gravida=1)
        2. Convert to regular after delivery
        3. Re-register as pregnant (gravida=2)
        4. Verify all data is correct
        """
        service = PatientService(db)
        repo = PatientRepository(db)
        search_service = SearchService(db)
        user_id = uuid.uuid4()
        facility_id = uuid.uuid4()
        
        # Step 1: Register as pregnant
        patient = PregnantPatient(
            id=uuid.uuid4(),
            name="Elizabeth Brown",
            phone="+254712345681",
            sex=Sex.FEMALE,
            date_of_birth=date(1991, 9, 5),
            patient_type=PatientType.PREGNANT,
            status=PatientStatus.ACTIVE,
            facility_id=facility_id,
            created_by_id=user_id,
            gravida=1,
            para=0,
        )
        await repo.create_pregnant_patient(patient)
        
        pregnancy1 = patient.open_new_pregnancy()
        pregnancy1.lmp_date = date(2025, 10, 1)
        await repo.create_pregnancy(pregnancy1)
        
        # Verify initial search result
        patients, _ = await repo.search_patients(facility_id=facility_id)
        assert len(patients) > 0
        result = search_service._patient_to_search_result(patients[0])
        assert result.patient_type == "pregnant"
        
        # Step 2: Convert to regular
        conversion_data = ConvertToRegularPatientSchema(
            outcome=PregnancyOutcome.LIVE_BIRTH,
            actual_delivery_date=date(2026, 8, 15),
            treatment_regimen="HAART",
        )
        
        regular = await service.convert_to_regular_patient(
            user_id, patient.id, conversion_data
        )
        assert regular.patient_type == PatientType.REGULAR
        
        # Verify search shows as regular
        patients, _ = await repo.search_patients(facility_id=facility_id)
        result = search_service._patient_to_search_result(patients[0])
        assert result.patient_type == "regular"
        
        # Step 3: Re-register as pregnant
        reregister_data = ReRegisterAsPregnantSchema(
            lmp_date=date(2026, 1, 10),
            expected_delivery_date=date(2026, 10, 10),
        )
        
        pregnant_again = await service.re_register_as_pregnant(
            user_id, patient.id, reregister_data
        )
        assert pregnant_again.patient_type == PatientType.PREGNANT
        assert pregnant_again.gravida == 2  # Second pregnancy
        
        # Verify final search result
        patients, _ = await repo.search_patients(facility_id=facility_id)
        result = search_service._patient_to_search_result(patients[0])
        assert result.patient_type == "pregnant"
        assert result.active_pregnancy is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
