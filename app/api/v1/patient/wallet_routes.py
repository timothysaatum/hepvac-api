import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.patient_schemas import (
    PatientWalletCreateSchema,
    PatientWalletResponseSchema,
    PaymentCreateSchema,
    PaymentResponseSchema,
)
from app.services.patient_service import PatientService
from app.core.utils import logger


router = APIRouter(prefix="/patient-wallet", tags=["patient wallets"])

# ============= Wallet Routes =============
@router.post(
    "/{patient_id}",
    response_model=PatientWalletResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_wallet(
    patient_id: uuid.UUID,
    wallet_data: PatientWalletCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Create wallet for patient (Staff only)."""
    service = PatientService(db)
    try:
        wallet_data.patient_id = patient_id
        wallet = await service.create_wallet(wallet_data)

        logger.log_info(
            {
                "event": "wallet_created",
                "wallet_id": str(wallet.id),
                "patient_id": str(patient_id),
                "created_by": str(current_user.id),
            }
        )

        return PatientWalletResponseSchema.model_validate(wallet, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "create_wallet_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating wallet",
        )


@router.get("/{patient_id}", response_model=PatientWalletResponseSchema)
async def get_patient_wallet(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Get patient wallet (Staff only)."""
    service = PatientService(db)
    try:
        wallet = await service.get_patient_wallet(patient_id)
        return PatientWalletResponseSchema.model_validate(wallet, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_wallet_error",
                "patient_id": str(patient_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving wallet",
        )


# ============= Payment Routes =============
@router.post(
    "/{wallet_id}/payments",
    response_model=PaymentResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    wallet_id: uuid.UUID,
    payment_data: PaymentCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """Create payment for wallet (Staff only)."""
    service = PatientService(db)
    try:
        payment_data.wallet_id = wallet_id
        payment_data.received_by_id = current_user.id

        payment = await service.create_payment(payment_data)

        logger.log_info(
            {
                "event": "payment_created",
                "payment_id": str(payment.id),
                "wallet_id": str(wallet_id),
                "amount": str(payment.amount),
                "received_by": str(current_user.id),
            }
        )

        return PaymentResponseSchema.model_validate(payment, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "create_payment_error",
                "wallet_id": str(wallet_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating payment",
        )


@router.get("/{wallet_id}/payments", response_model=list[PaymentResponseSchema])
async def list_wallet_payments(
    wallet_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """List all payments for wallet (Staff only)."""
    service = PatientService(db)
    try:
        payments = await service.list_wallet_payments(wallet_id)
        return [
            PaymentResponseSchema.model_validate(p, from_attributes=True)
            for p in payments
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_payments_error",
                "wallet_id": str(wallet_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving payments",
        )
