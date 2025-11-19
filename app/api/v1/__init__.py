from fastapi import APIRouter
from .patient.user_routes import router as user_router
from .patient.facility_routes import router as facility_router
from .patient.patient_routes import router as patient_router
from .patient.vaccination_routes import router as vaccination_router
from .patient.wallet_routes import router as wallet_router
from .patient.child_routes import router as child_router
from .patient.medication_routes import router as medication_router
from .patient.patient_schedules import router as patient_schedule_router
from .patient.reminder_routes import router as reminder_router

router = APIRouter()


router.include_router(user_router)
router.include_router(facility_router)
router.include_router(patient_router)
router.include_router(vaccination_router)
router.include_router(wallet_router)
router.include_router(child_router)
router.include_router(medication_router)
router.include_router(patient_schedule_router)
router.include_router(reminder_router)
