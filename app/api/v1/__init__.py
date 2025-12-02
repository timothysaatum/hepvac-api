from fastapi import APIRouter
from .user.user_routes import router as user_router
from .facility.facility_routes import router as facility_router
from .vaccines.vaccine_routes import router as vaccine_router
from .patient.patient_routes import router as patient_router
from .patient.child_routes import router as child_router
from .patient.medication_routes import router as medication_router
from .patient.patient_schedules import router as patient_schedule_router
from .patient.reminder_routes import router as reminder_router
from .vaccines.vaccine_purchases import router as vaccine_purchase_router
from .vaccines.vaccine_payment import router as vaccine_payment
from .vaccines.administer_vaccine import router as administer_vaccine
from .devices.devices import router as device_router
from .search.search_routes import router as search_router
from .dashboard.dashboard import router as dashboard_router
from .settings.settings import router as settings_router

router = APIRouter()


router.include_router(user_router)
router.include_router(device_router)
router.include_router(facility_router)
router.include_router(vaccine_router)
router.include_router(patient_router)
router.include_router(child_router)
router.include_router(vaccine_purchase_router)
router.include_router(vaccine_payment)
router.include_router(administer_vaccine)
router.include_router(medication_router)
router.include_router(patient_schedule_router)
router.include_router(reminder_router)
router.include_router(search_router)
router.include_router(dashboard_router)
router.include_router(settings_router)