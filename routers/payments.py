# routers/payments.py
"""
Payment confirmation API.

POST /payments/confirm: confirm a payment (e.g. after provider webhook or client callback).
Marks invoice PAID, appends blockchain ledger record, returns transaction hash.
Does NOT integrate with PayMaya secrets; assumes provider has already secured fund movement.
"""
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

import os
import base64
import requests
from fastapi import Body

from database import get_session
from models import Invoice
from models.invoice import InvoiceStatus
from schemas.payment import PaymentConfirmRequest, PaymentConfirmResponse, CheckoutRequest
from services.ledger_service import append_payment_record

from main import verify_token

router = APIRouter(prefix="/api/payments", tags=["payments"])

PAYMAYA_PUBLIC_KEY = os.getenv("PAYMAYA_PUBLIC_KEY")
PAYMAYA_SECRET_KEY = os.getenv("PAYMAYA_SECRET_KEY")
PAYMAYA_BASE_URL_SANDBOX = os.getenv("PAYMAYA_BASE_URL_SANDBOX")


def _paymaya_headers():
     auth = base64.b64encode(f"{PAYMAYA_SECRET_KEY}:".encode()).decode()
     return {
          "Content-Type": "application/json",
          "Authorization": f"Basic {auth}"
     }


@router.post("/checkout")
def create_checkout(
     body: CheckoutRequest,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token),
):
     invoice = db.query(Invoice).filter(Invoice.id == body.invoice_id).first()
     if not invoice:
          raise HTTPException(404, "Invoice not found")

     if invoice.status == InvoiceStatus.PAID:
          raise HTTPException(400, "Invoice already paid")

     payload = {
          "totalAmount": {
               "value": float(invoice.amount),
               "currency": "PHP"
          },
          "buyer": {
               "firstName": "Tenant",
               "lastName": "User"
          },
          "requestReferenceNumber": f"INV-{invoice.id}",
          "redirectUrl": {
               "success": "https://condoease.me/payment-success",
               "failure": "https://condoease.me/payment-failure",
               "cancel": "https://condoease.me/payment-cancel"
          }
     }

     response = requests.post(
          f"{PAYMAYA_BASE_URL_SANDBOX}/checkout/v1/checkouts",
          json=payload,
          headers=_paymaya_headers()
     )

     if response.status_code not in [200, 201]:
          raise HTTPException(500, response.text)

     data = response.json()

     return {
          "checkout_id": data["checkoutId"],
          "redirect_url": data["redirectUrl"]
     }

@router.post(
     "/confirm",
     response_model=PaymentConfirmResponse,
     status_code=status.HTTP_201_CREATED,
     summary="Confirm payment",
)
@router.post("/webhook")
async def paymaya_webhook(
     payload: dict = Body(...),
     db: Session = Depends(get_session),
):
     """
     Receives PayMaya payment result.
     """
     event = payload.get("event")
     data = payload.get("data", {})
     if event != "CHECKOUT.SUCCESS":
          return {"message": "Ignored non-success event"}
     checkout_id = data.get("id")
     request_ref = data.get("requestReferenceNumber")

     # Extract invoice ID from reference
     if not request_ref.startswith("INV-"):
          raise HTTPException(400, "Invalid reference")
     invoice_id = int(request_ref.replace("INV-", ""))
     invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
     if not invoice:
          raise HTTPException(404, "Invoice not found")
     if invoice.status == InvoiceStatus.PAID:
          return {"message": "Already processed"}

     # Mark paid
     invoice.mark_as_paid()
     entry = append_payment_record(
          db,
          invoice_id=invoice.id,
          tenant_id=invoice.tenant_id,
          amount=invoice.amount,
          timestamp=None,
     )
     db.commit()
     return {
          "invoice_id": invoice.id,
          "transaction_hash": entry.transaction_hash,
          "provider_reference": checkout_id,
          "status": "PAID"
     }

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
