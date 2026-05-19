# routers/webhooks.py
"""
Payment Webhook API routes.

Handles incoming webhooks from Maya payment gateway.
Validates signatures and processes payment events.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_session
from services.webhook_service import WebhookProcessor, store_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post(
    "/payments/maya",
    status_code=status.HTTP_200_OK,
    summary="Maya payment webhook handler"
)
async def handle_maya_webhook(
    request: Request,
    db: Session = Depends(get_session)
):
    """
    Handle incoming Maya payment webhook.
    
    Validates webhook signature and processes payment status updates.
    
    **Webhook Flow:**
    1. Receive webhook with signature
    2. Validate signature using MAYA_WEBHOOK_SECRET
    3. Parse payment status and metadata
    4. Update invoice status and create ledger entry
    5. Return confirmation
    
    **Security:**
    - Signature is validated using HMAC-SHA256
    - Raw request body is used for signature verification
    - Webhook is idempotent (repeated calls safe)
    
    **Expected Webhook Payload:**
    ```json
    {
      "status": "PAYMENT_SUCCESS",
      "amount": {
        "value": 5000.00,
        "currency": "PHP"
      },
      "metadata": {
        "invoice_id": "1",
        "tenant_id": "1",
        "tenant_email": "tenant@example.com",
        "tenant_name": "John Doe"
      }
    }
    ```
    
    **Response:**
    ```json
    {
      "success": true,
      "message": "Payment confirmed successfully",
      "data": {
        "invoice_id": 1,
        "transaction_hash": "abc123...",
        "status": "PAID"
      }
    }
    ```
    """
    try:
        # Extract signature from headers
        signature = request.headers.get("X-Maya-Signature")
        if not signature:
            logger.warning("Missing X-Maya-Signature header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Maya-Signature header"
            )
        
        # Get raw body for signature verification
        raw_body = await request.body()
        
        # Parse JSON
        webhook_data = await request.json()
        
        logger.info(f"Received webhook for invoice {webhook_data.get('metadata', {}).get('invoice_id')}")
        
        # Validate and process webhook
        success, message, result = WebhookProcessor.validate_and_process_webhook(
            db=db,
            webhook_data=webhook_data,
            signature=signature,
            raw_body=raw_body
        )
        
        # Store webhook event for audit
        store_webhook_event(
            db=db,
            webhook_event=webhook_data,
            validation_status="SUCCESS" if success else "FAILED",
            result=result
        )
        
        # Return response
        response_status = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
        
        return {
            "success": success,
            "message": message,
            "data": result
        }
        
    except ValueError as e:
        logger.error(f"Invalid JSON in webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error processing webhook"
        )


@router.post(
    "/payments/confirm",
    status_code=status.HTTP_200_OK,
    summary="Manual payment confirmation",
    deprecated=True  # Use webhook instead
)
async def manual_payment_confirmation(
    invoice_id: int,
    amount: float,
    provider_reference: str,
    db: Session = Depends(get_session)
):
    """
    **DEPRECATED**: Use webhook endpoint instead.
    
    Legacy endpoint for manual payment confirmation.
    Keep for backward compatibility but webhooks are preferred.
    
    This endpoint is kept for testing and fallback scenarios.
    Production should use webhook-based confirmation.
    """
    logger.warning(f"Manual payment confirmation called for invoice {invoice_id}")
    
    return {
        "warning": "This endpoint is deprecated. Use webhook instead.",
        "message": "Please use /api/webhooks/payments/maya for payment confirmation"
    }


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Webhook health check"
)
async def webhook_health():
    """
    Health check for webhook endpoint.
    
    Can be used by payment provider to verify endpoint is active.
    """
    return {
        "status": "ok",
        "service": "payment-webhooks",
        "timestamp": None  # Will be filled by response middleware
    }
