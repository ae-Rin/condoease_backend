# routers/payments.py
"""
Payment confirmation API.

POST /payments/confirm: confirm a payment (e.g. after provider webhook or client callback).
Marks invoice PAID, appends blockchain ledger record, returns transaction hash.
Does NOT integrate with PayMaya secrets; assumes provider has already secured fund movement.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_session
from models import Invoice
from models.invoice import InvoiceStatus
from schemas.payment import PaymentConfirmRequest, PaymentConfirmResponse
from services.ledger_service import append_payment_record

from main import verify_token

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post(
    "/confirm",
    response_model=PaymentConfirmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm payment",
)
def confirm_payment(
    body: PaymentConfirmRequest,
    db: Session = Depends(get_session),
    token: dict = Depends(verify_token),
):
    """
    Confirm that a payment has been completed (e.g. after PayMaya callback).

    1. Validates invoice exists and amount matches.
    2. Marks invoice as PAID.
    3. Appends an immutable blockchain ledger record.
    4. Returns transaction hash for client verification.

    **No PayMaya secrets** – assume the provider has already secured fund movement;
    this endpoint records the confirmation and builds the ledger chain.
    """
    invoice = db.query(Invoice).filter(Invoice.id == body.invoice_id).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID {body.invoice_id} not found",
        )

    if invoice.status == InvoiceStatus.PAID:
        # Idempotent: already paid; return existing ledger hash or backfill once
        if invoice.payment_ledger_entry:
            return PaymentConfirmResponse(
                invoice_id=invoice.id,
                transaction_hash=invoice.payment_ledger_entry.transaction_hash,
                provider_reference=body.provider_reference,
                status="PAID",
            )
        # Paid but no ledger entry (e.g. legacy); backfill and return hash
        if body.amount != invoice.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Amount mismatch: invoice amount is {invoice.amount}, received {body.amount}",
            )
        try:
            entry = append_payment_record(
                db,
                invoice_id=invoice.id,
                tenant_id=invoice.tenant_id,
                amount=invoice.amount,
                timestamp=None,
            )
            db.commit()
            db.refresh(invoice)
            return PaymentConfirmResponse(
                invoice_id=invoice.id,
                transaction_hash=entry.transaction_hash,
                provider_reference=body.provider_reference,
                status="PAID",
            )
        except ValueError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ledger entry already exists for this invoice",
            )

    if body.amount != invoice.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Amount mismatch: invoice amount is {invoice.amount}, received {body.amount}",
        )

    invoice.mark_as_paid()
    try:
        entry = append_payment_record(
            db,
            invoice_id=invoice.id,
            tenant_id=invoice.tenant_id,
            amount=invoice.amount,
            timestamp=None,
        )
        transaction_hash = entry.transaction_hash
    except ValueError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ledger entry already exists for this invoice",
        )

    db.commit()
    db.refresh(invoice)

    return PaymentConfirmResponse(
        invoice_id=invoice.id,
        transaction_hash=transaction_hash,
        provider_reference=body.provider_reference,
        status="PAID",
    )
