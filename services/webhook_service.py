# services/webhook_service.py
"""
Webhook Validation and Processing Service.

Handles Maya webhook validation, event processing, and state management.
Ensures that payments are only confirmed after proper validation.
"""
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from models import Invoice
from models.invoice import InvoiceStatus
from services.maya_service import MayaService, MayaValidationError
from services.ledger_service import append_payment_record

logger = logging.getLogger(__name__)


class WebhookValidationError(Exception):
    """Exception for webhook validation failures."""
    pass


class WebhookProcessor:
    """Processes and validates payment webhooks."""
    
    @staticmethod
    def validate_and_process_webhook(
        db: Session,
        webhook_data: Dict,
        signature: str,
        raw_body: bytes
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Validate webhook signature and process payment event.
        
        Args:
            db: SQLAlchemy session
            webhook_data: Parsed JSON webhook data
            signature: X-Maya-Signature header
            raw_body: Raw request body for signature verification
            
        Returns:
            Tuple of (success: bool, message: str, result: Optional[Dict])
            result contains transaction details if successful
        """
        try:
            # Step 1: Validate webhook signature
            if not MayaService.validate_webhook_signature(raw_body, signature):
                logger.warning(f"Webhook signature validation failed")
                raise WebhookValidationError("Webhook signature invalid")
            
            logger.info("Webhook signature validated successfully")
            
            # Step 2: Parse webhook payload
            status, metadata = MayaService.parse_webhook_payload(webhook_data)
            logger.info(f"Webhook status: {status}, metadata: {metadata}")
            
            # Step 3: Handle different payment statuses
            if status == "PAYMENT_SUCCESS":
                return WebhookProcessor._handle_payment_success(
                    db=db,
                    webhook_data=webhook_data,
                    metadata=metadata
                )
            elif status == "PAYMENT_FAILED":
                return WebhookProcessor._handle_payment_failed(
                    db=db,
                    metadata=metadata
                )
            elif status == "PAYMENT_EXPIRED":
                return WebhookProcessor._handle_payment_expired(
                    db=db,
                    metadata=metadata
                )
            else:
                logger.warning(f"Unknown webhook status: {status}")
                return False, f"Unknown webhook status: {status}", None
                
        except WebhookValidationError as e:
            logger.error(f"Webhook validation error: {str(e)}")
            return False, str(e), None
        except MayaValidationError as e:
            logger.error(f"Maya validation error: {str(e)}")
            return False, str(e), None
        except Exception as e:
            logger.error(f"Unexpected error processing webhook: {str(e)}", exc_info=True)
            return False, f"Internal error: {str(e)}", None
    
    @staticmethod
    def _handle_payment_success(
        db: Session,
        webhook_data: Dict,
        metadata: Dict
    ) -> Tuple[bool, str, Dict]:
        """
        Handle successful payment webhook.
        
        Flow:
        1. Validate invoice exists and amount matches
        2. Mark invoice as PAID
        3. Create immutable ledger entry with hash
        4. Return confirmation
        """
        try:
            invoice_id = int(metadata.get("invoice_id"))
            tenant_id = int(metadata.get("tenant_id"))
            
            # Load invoice
            invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if not invoice:
                logger.error(f"Invoice {invoice_id} not found")
                return False, f"Invoice {invoice_id} not found", None
            
            # Verify invoice belongs to tenant
            if invoice.tenant_id != tenant_id:
                logger.error(f"Tenant ID mismatch for invoice {invoice_id}")
                return False, "Tenant ID mismatch", None
            
            # Check if already paid
            if invoice.status == InvoiceStatus.PAID:
                logger.info(f"Invoice {invoice_id} already paid - idempotent response")
                # Return existing hash if available
                if invoice.payment_ledger_entry:
                    return True, "Invoice already paid", {
                        "invoice_id": invoice_id,
                        "transaction_hash": invoice.payment_ledger_entry.transaction_hash,
                        "status": "ALREADY_PAID"
                    }
            
            # Get payment amount from webhook
            amount = webhook_data.get("amount", {}).get("value")
            if not amount:
                logger.error("Payment amount not found in webhook")
                return False, "Payment amount not found", None
            
            # Mark invoice as PAID
            invoice.mark_as_paid()
            
            # Append ledger entry
            try:
                entry = append_payment_record(
                    db=db,
                    invoice_id=invoice_id,
                    tenant_id=tenant_id,
                    amount=invoice.amount,
                    timestamp=None  # Uses current timestamp
                )
                db.commit()
                
                logger.info(f"Invoice {invoice_id} marked as PAID with hash {entry.transaction_hash[:16]}...")
                
                return True, "Payment confirmed successfully", {
                    "invoice_id": invoice_id,
                    "transaction_hash": entry.transaction_hash,
                    "status": "PAID",
                    "timestamp": entry.timestamp.isoformat()
                }
                
            except ValueError as e:
                db.rollback()
                logger.error(f"Ledger error: {str(e)}")
                return False, f"Ledger error: {str(e)}", None
                
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid webhook data: {str(e)}")
            return False, f"Invalid webhook data: {str(e)}", None
        except Exception as e:
            db.rollback()
            logger.error(f"Error handling payment success: {str(e)}", exc_info=True)
            return False, f"Error processing payment: {str(e)}", None
    
    @staticmethod
    def _handle_payment_failed(
        db: Session,
        metadata: Dict
    ) -> Tuple[bool, str, Dict]:
        """Handle failed payment webhook."""
        try:
            invoice_id = int(metadata.get("invoice_id"))
            
            logger.warning(f"Payment failed for invoice {invoice_id}")
            
            # Keep invoice in PENDING state
            return True, "Payment failed recorded", {
                "invoice_id": invoice_id,
                "status": "FAILED"
            }
            
        except Exception as e:
            logger.error(f"Error handling payment failure: {str(e)}")
            return False, str(e), None
    
    @staticmethod
    def _handle_payment_expired(
        db: Session,
        metadata: Dict
    ) -> Tuple[bool, str, Dict]:
        """Handle expired payment webhook."""
        try:
            invoice_id = int(metadata.get("invoice_id"))
            
            logger.warning(f"Payment expired for invoice {invoice_id}")
            
            # Mark invoice as OVERDUE if past due date
            invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if invoice and invoice.is_overdue:
                invoice.mark_as_overdue()
                db.commit()
                logger.info(f"Invoice {invoice_id} marked as OVERDUE")
            
            return True, "Payment expiration recorded", {
                "invoice_id": invoice_id,
                "status": "EXPIRED"
            }
            
        except Exception as e:
            logger.error(f"Error handling payment expiration: {str(e)}")
            return False, str(e), None


def store_webhook_event(
    db: Session,
    webhook_event: Dict,
    validation_status: str,
    result: Optional[Dict] = None
) -> None:
    """
    Store webhook event in database for audit trail.
    
    Args:
        db: SQLAlchemy session
        webhook_event: Full webhook payload
        validation_status: Status of validation (SUCCESS, FAILED, ERROR)
        result: Processing result dictionary
    """
    try:
        # Optional: Create a WebhookLog table to track all events
        # For now, just log to file/console
        logger.info(
            f"Webhook event stored - Status: {validation_status}, "
            f"Invoice: {webhook_event.get('metadata', {}).get('invoice_id')}, "
            f"Result: {result}"
        )
    except Exception as e:
        logger.error(f"Failed to store webhook event: {str(e)}")
