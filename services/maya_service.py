# services/maya_service.py
"""
Maya Sandbox Payment Integration Service.

Handles PayMaya sandbox checkout creation, webhook validation, and payment confirmation.
"""
import os
import hmac
import hashlib
import json
import requests
from typing import Optional, Dict, Tuple
from decimal import Decimal
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Maya Sandbox Configuration
MAYA_API_KEY = os.getenv("MAYA_API_KEY")
MAYA_SECRET_KEY = os.getenv("MAYA_SECRET_KEY")
MAYA_SANDBOX_URL = os.getenv("MAYA_SANDBOX_URL", "https://payments-sandbox.paycom.ph")
MAYA_WEBHOOK_SECRET = os.getenv("MAYA_WEBHOOK_SECRET")

# Derived URLs
MAYA_CHECKOUT_URL = f"{MAYA_SANDBOX_URL}/checkout/v1/create"
MAYA_PAYMENT_STATUS_URL = f"{MAYA_SANDBOX_URL}/payment/v1"


class MayaPaymentError(Exception):
    """Base exception for Maya payment errors."""
    pass


class MayaValidationError(MayaPaymentError):
    """Exception for webhook validation failures."""
    pass


class MayaService:
    """Service for Maya Sandbox payment operations."""
    
    @staticmethod
    def create_checkout(
        invoice_id: int,
        tenant_id: int,
        amount: Decimal,
        tenant_email: str,
        tenant_name: str,
        return_url: str,
        webhook_url: str,
        description: str = "CondoEase Invoice Payment"
    ) -> Dict:
        """
        Create a Maya sandbox checkout session.
        
        Args:
            invoice_id: Invoice ID to link to this payment
            tenant_id: Tenant ID for payment tracking
            amount: Payment amount in PHP
            tenant_email: Tenant email address
            tenant_name: Tenant name
            return_url: URL to redirect after checkout
            webhook_url: URL for webhook callbacks
            description: Payment description
            
        Returns:
            Dictionary with checkout data including checkout_url
            
        Raises:
            MayaPaymentError: If checkout creation fails
        """
        if not MAYA_API_KEY or not MAYA_SECRET_KEY:
            raise MayaPaymentError("Maya API keys not configured")
        
        # Normalize amount to 2 decimal places
        normalized_amount = float(amount)
        
        # Prepare checkout payload
        payload = {
            "requestReferenceNumber": f"INV-{invoice_id}-{int(datetime.utcnow().timestamp())}",
            "amount": {
                "value": normalized_amount,
                "currency": "PHP"
            },
            "description": description,
            "redirectUrl": {
                "success": return_url,
                "failure": return_url,
                "cancel": return_url
            },
            "metadata": {
                "invoice_id": str(invoice_id),
                "tenant_id": str(tenant_id),
                "tenant_email": tenant_email,
                "tenant_name": tenant_name
            },
            "buyer": {
                "firstName": tenant_name.split()[0] if tenant_name else "Tenant",
                "lastName": tenant_name.split()[-1] if len(tenant_name.split()) > 1 else "",
                "email": tenant_email
            },
            "webhook": {
                "url": webhook_url,
                "eventType": "PAYMENT_SUCCESS"
            }
        }
        
        # Create basic auth header
        auth_string = f"{MAYA_API_KEY}:"
        import base64
        auth_header = "Basic " + base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                MAYA_CHECKOUT_URL,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            checkout_data = response.json()
            
            # Validate response structure
            if "checkoutId" not in checkout_data or "redirectUrl" not in checkout_data:
                raise MayaPaymentError("Invalid Maya checkout response structure")
            
            return {
                "checkout_id": checkout_data["checkoutId"],
                "checkout_url": checkout_data["redirectUrl"],
                "request_reference": payload["requestReferenceNumber"],
                "status": "PENDING",
                "created_at": datetime.utcnow().isoformat()
            }
            
        except requests.exceptions.RequestException as e:
            raise MayaPaymentError(f"Failed to create Maya checkout: {str(e)}")
        except (KeyError, ValueError) as e:
            raise MayaPaymentError(f"Invalid Maya response: {str(e)}")
    
    @staticmethod
    def validate_webhook_signature(
        request_body: bytes,
        signature_header: str
    ) -> bool:
        """
        Validate Maya webhook signature.
        
        Args:
            request_body: Raw request body bytes
            signature_header: X-Maya-Signature header value
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not MAYA_WEBHOOK_SECRET:
            raise MayaValidationError("Maya webhook secret not configured")
        
        # Compute HMAC-SHA256
        computed_signature = hmac.new(
            MAYA_WEBHOOK_SECRET.encode(),
            request_body,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures (constant-time comparison to prevent timing attacks)
        return hmac.compare_digest(computed_signature, signature_header)
    
    @staticmethod
    def parse_webhook_payload(webhook_data: Dict) -> Tuple[str, Optional[Dict]]:
        """
        Parse and validate Maya webhook payload.
        
        Args:
            webhook_data: Parsed JSON from webhook request
            
        Returns:
            Tuple of (status: str, metadata: Optional[Dict])
            Status can be: PAYMENT_SUCCESS, PAYMENT_FAILED, PAYMENT_EXPIRED
            
        Raises:
            MayaValidationError: If payload structure is invalid
        """
        try:
            # Extract payment status
            status = webhook_data.get("status", "").upper()
            
            # Extract metadata
            metadata = webhook_data.get("metadata", {})
            
            # Validate required fields for successful payment
            if status == "PAYMENT_SUCCESS":
                if not metadata.get("invoice_id"):
                    raise MayaValidationError("Missing invoice_id in webhook metadata")
                if not metadata.get("tenant_id"):
                    raise MayaValidationError("Missing tenant_id in webhook metadata")
            
            return status, metadata
            
        except (KeyError, AttributeError) as e:
            raise MayaValidationError(f"Invalid webhook payload structure: {str(e)}")
    
    @staticmethod
    def get_payment_status(checkout_id: str) -> Dict:
        """
        Get payment status from Maya API.
        
        Args:
            checkout_id: Maya checkout ID
            
        Returns:
            Dictionary with payment details and status
            
        Raises:
            MayaPaymentError: If API call fails
        """
        if not MAYA_API_KEY:
            raise MayaPaymentError("Maya API key not configured")
        
        import base64
        auth_string = f"{MAYA_API_KEY}:"
        auth_header = "Basic " + base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
        
        try:
            url = f"{MAYA_PAYMENT_STATUS_URL}/{checkout_id}"
            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise MayaPaymentError(f"Failed to get payment status: {str(e)}")


def create_checkout_for_invoice(
    db,
    invoice_id: int,
    return_url: str,
    webhook_url: str
) -> Dict:
    """
    Helper function to create Maya checkout for an invoice.
    
    Args:
        db: SQLAlchemy session
        invoice_id: Invoice ID
        return_url: Redirect URL after payment
        webhook_url: Webhook URL for payment notifications
        
    Returns:
        Checkout data dictionary
        
    Raises:
        ValueError: If invoice not found
        MayaPaymentError: If checkout creation fails
    """
    from models import Invoice
    
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise ValueError(f"Invoice {invoice_id} not found")
    
    tenant = invoice.tenant
    if not tenant:
        raise ValueError(f"Tenant not found for invoice {invoice_id}")
    
    # Create checkout
    return MayaService.create_checkout(
        invoice_id=invoice_id,
        tenant_id=tenant.tenant_id,
        amount=invoice.amount,
        tenant_email=tenant.email or "no-email@condoease.ph",
        tenant_name=tenant.first_name or "Tenant",
        return_url=return_url,
        webhook_url=webhook_url,
        description=f"Invoice #{invoice_id} - CondoEase"
    )
