import traceback
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.permission_checker import require_staff_or_admin
from app.models.user_model import User
from app.schemas.vaccine_schemas import PaymentCreateSchema, PaymentResponseSchema
from app.services.vaccine_purchase_service import VaccinePurchaseService
from app.core.utils import logger


router = APIRouter(prefix="/vaccine-payment", tags=["vaccine payment"])


@router.post(
    "/{purchase_id}",
    response_model=PaymentResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    purchase_id: uuid.UUID,
    payment_data: PaymentCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Record a payment for a vaccine purchase.

    This creates a payment record and updates the purchase balance automatically.

    Args:
        purchase_id: Vaccine purchase UUID
        payment_data: Payment creation data
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        PaymentResponseSchema: Created payment information

    Raises:
        404: Vaccine purchase not found
        400: Invalid payment amount or purchase already fully paid
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        # Set vaccine_purchase_id and received_by_id from path and authenticated user
        payment_data.vaccine_purchase_id = purchase_id
        payment_data.received_by_id = current_user.id

        payment = await service.create_payment(payment_data)

        logger.log_info(
            {
                "event": "payment_recorded",
                "payment_id": str(payment.id),
                "purchase_id": str(purchase_id),
                "amount": float(payment.amount),
                "payment_method": payment.payment_method,
                "received_by": str(current_user.id),
            }
        )

        return PaymentResponseSchema.model_validate(payment, from_attributes=True)

    except HTTPException:
        raise

    except ValueError as e:
        logger.log_warning(
            {
                "event": "payment_creation_failed",
                "reason": "validation_error",
                "error": str(e),
                "purchase_id": str(purchase_id),
                "received_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.log_error(
            {
                "event": "payment_creation_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "purchase_id": str(purchase_id),
                "received_by": str(current_user.id),
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while recording payment",
        )


@router.get(
    "/{purchase_id}",
    response_model=List[PaymentResponseSchema],
)
async def list_purchase_payments(
    purchase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    List all payments for a vaccine purchase.

    Args:
        purchase_id: Vaccine purchase UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        List[PaymentResponseSchema]: List of payments ordered by date

    Raises:
        404: Vaccine purchase not found
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        payments = await service.list_purchase_payments(purchase_id)

        logger.log_info(
            {
                "event": "purchase_payments_listed",
                "purchase_id": str(purchase_id),
                "payment_count": len(payments),
                "user_id": str(current_user.id),
            }
        )

        return [
            PaymentResponseSchema.model_validate(p, from_attributes=True)
            for p in payments
        ]

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "list_purchase_payments_error",
                "purchase_id": str(purchase_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving payments",
        )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponseSchema,
)
async def get_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    """
    Get payment by ID.

    Args:
        payment_id: Payment UUID
        db: Database session
        current_user: Authenticated admin or staff user

    Returns:
        PaymentResponseSchema: Payment information

    Raises:
        404: Payment not found
        500: Internal server error
    """
    service = VaccinePurchaseService(db)

    try:
        payment = await service.get_payment(payment_id)

        return PaymentResponseSchema.model_validate(payment, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.log_error(
            {
                "event": "get_payment_error",
                "payment_id": str(payment_id),
                "error": str(e),
                "user_id": str(current_user.id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving payment",
        )
