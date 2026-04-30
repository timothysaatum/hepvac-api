"""
Model registry — exports every ORM model from a single import point.

Usage:
    from app.models import User, Patient, Vaccine, Facility, Role, Permission, ...

Note: Infrastructure models (TrustedDevice, LoginAttempt, GeographicRestriction,
NotificationLog, Setting) are intentionally NOT exported from this registry.
They are application-layer concerns and should be imported directly from their
own modules to prevent tight coupling between the ORM model layer and application
infrastructure:

    from app.middlewares.device_trust import TrustedDevice, LoginAttempt, GeographicRestriction
    from app.core.notification_log import NotificationLog
    from app.core.settings import Setting
"""

# Auth & users
from .user_model import (
    User,
    RefreshToken,
    UserSession,
)

# RBAC
from .rbac import (
    Role,
    Permission,
    user_roles,
    role_permissions,
)

# Facility
from .facility_model import Facility

# Vaccines & inventory
from .vaccine_model import (
    Vaccine,
    PatientVaccinePurchase,
)

# Patients & clinical records
from .patient_model import (
    Patient,
    PregnantPatient,
    RegularPatient,
    Diagnosis,
    PatientLabResult,
    PatientLabTest,
    PatientIdentifier,
    PatientAllergy,
    Vaccination,
    Child,
    Payment,
    Prescription,
    MedicationSchedule,
    PatientReminder,
    FacilityNotification,
)

from app.core.settings import Setting
from app.core.notification_log import NotificationLog
from app.middlewares.device_trust import TrustedDevice, LoginAttempt, GeographicRestriction
from .job_queue_model import JobQueue
