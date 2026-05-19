# routers/checkout.py
"""
Payment Checkout API routes.

Handles checkout session creation and initialization for Maya payments.
"""
import logging
import os
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_session
from models import Invoice
from models.invoice import InvoiceStatus
from services.maya_service import MayaService, MayaPaymentError, create_checkout_for_invoice
from main import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


class CheckoutRequest(BaseModel):
    """Request to initiate checkout."""
    invoice_id: int = Field(..., gt=0, description="Invoice ID to pay")
    return_url: str = Field(..., description="URL to redirect after checkout")


class CheckoutResponse(BaseModel):
    """Response with checkout session details."""
    checkout_id: str = Field(..., description="Maya checkout session ID")
    checkout_url: str = Field(..., description="URL to redirect user to for payment")
    request_reference: str = Field(..., description="Request reference number")
    status: str = Field(default="PENDING", description="Checkout status")
    invoice_id: int = Field(..., description="Associated invoice ID")


class CheckoutStatusRequest(BaseModel):
    """Request to check checkout status."""
    checkout_id: str = Field(..., description="Maya checkout ID")


class CheckoutStatusResponse(BaseModel):
    """Response with checkout status."""
    checkout_id: str = Field(..., description="Checkout ID")
    status: str = Field(..., description="Payment status (PENDING, SUCCESS, FAILED, EXPIRED)")
    invoice_id: Optional[int] = Field(None, description="Associated invoice ID")
    amount: Optional[Decimal] = Field(None, description="Payment amount")


@router.post(
    "/initiate",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate payment checkout"
)
async def initiate_checkout(
    request_data: CheckoutRequest,
    db: Session = Depends(get_session),
    token: dict = Depends(verify_token)
):
    """
    Initiate a Maya payment checkout for an invoice.
    
    **Flow:**
    1. Validate invoice exists and is unpaid
    2. Create Maya checkout session
    3. Return checkout URL for client to redirect to
    4. After payment, webhook callback confirms payment
    
    **Request:**
    ```json
    {
      "invoice_id": 1,
      "return_url": "https://app.example.com/payment/return"
    }
    ```
    
    **Response:**
    ```json
    {
      "checkout_id": "MAYA_CHECKOUT_ID",
      "checkout_url": "https://payments-sandbox.paycom.ph/checkout/...",
      "request_reference": "INV-1-1234567890",
      "status": "PENDING",
      "invoice_id": 1
    }
    ```
    
    **Error Cases:**
    - 404: Invoice not found
    - 400: Invoice already paid or validation failed
    - 503: Maya service unavailable
    """
    try:
        invoice_id = request_data.invoice_id
        
        # Validate invoice exists
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            logger.warning(f"Checkout attempt for non-existent invoice {invoice_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )
        
        # Verify user can access this invoice (RBAC)
        user_id = token.get("id")
        user_role = token.get("role")
        
        # Add your RBAC logic here if needed
        # For now, allow if they have a valid token
        
        # Check if invoice is already paid
        if invoice.status == InvoiceStatus.PAID:
            logger.warning(f"Checkout attempt for already-paid invoice {invoice_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invoice is already paid"
            )
        
        # Build webhook URL
        webhook_url = os.getenv(
            "WEBHOOK_URL",
            "https://api.condoease.ph/api/webhooks/payments/maya"
        )
        
        logger.info(f"Creating checkout for invoice {invoice_id}, amount: {invoice.amount}")
        
        # Create checkout
        checkout_data = create_checkout_for_invoice(
            db=db,
            invoice_id=invoice_id,
            return_url=request_data.return_url,
            webhook_url=webhook_url
        )
        
        logger.info(f"Checkout created: {checkout_data['checkout_id']}")
        
        return CheckoutResponse(
            checkout_id=checkout_data["checkout_id"],
            checkout_url=checkout_data["checkout_url"],
            request_reference=checkout_data["request_reference"],
            status=checkout_data["status"],
            invoice_id=invoice_id
        )
        
    except HTTPException:
        raise
    except MayaPaymentError as e:
        logger.error(f"Maya payment error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Error initiating checkout: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )


@router.post(
    "/status",
    response_model=CheckoutStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check checkout status"
)
async def check_checkout_status(
    request_data: CheckoutStatusRequest,
    db: Session = Depends(get_session),
    token: dict = Depends(verify_token)
):
    """
    Check the status of a Maya checkout session.
    
    **Note:** This is optional - webhooks provide real-time status updates.
    Can be used for polling if needed.
    """
    try:
        checkout_id = request_data.checkout_id
        
        logger.info(f"Checking status for checkout {checkout_id}")
        
        # Get payment status from Maya
        status_data = MayaService.get_payment_status(checkout_id)
        
        # Extract relevant fields
        payment_status = status_data.get("status", "UNKNOWN")
        metadata = status_data.get("metadata", {})
        amount = status_data.get("amount", {}).get("value")
        
        return CheckoutStatusResponse(
            checkout_id=checkout_id,
            status=payment_status,
            invoice_id=int(metadata.get("invoice_id")) if metadata.get("invoice_id") else None,
            amount=Decimal(str(amount)) if amount else None
        )
        
    except MayaPaymentError as e:
        logger.error(f"Maya API error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Error checking checkout status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve checkout status"
        )


from typing import Optional
