# schemas/payment.py
"""
Pydantic schemas for payment confirmation API.
"""
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class PaymentConfirmRequest(BaseModel):
     """Request body for POST /payments/confirm."""

     invoice_id: int = Field(..., gt=0, description="Invoice to confirm payment for")
     amount: Decimal = Field(..., gt=0, description="Amount paid (must match invoice amount)")
     provider_reference: str = Field(
          ...,
          min_length=1,
          max_length=255,
          description="External payment provider reference (e.g. PayMaya checkout ID)",
     )

     model_config = ConfigDict(
          json_schema_extra={
               "example": {
                    "invoice_id": 1,
                    "amount": 5000.00,
                    "provider_reference": "PM-CHECKOUT-abc123xyz",
               }
          }
     )


class PaymentConfirmResponse(BaseModel):
     """Response for POST /payments/confirm."""

     invoice_id: int = Field(..., description="Invoice that was paid")
     transaction_hash: str = Field(..., description="Ledger transaction hash for client verification")
     provider_reference: str = Field(..., description="Provider reference as submitted")
     status: str = Field(default="PAID", description="Invoice status after confirmation")

     model_config = ConfigDict(
          json_schema_extra={
               "example": {
                    "invoice_id": 1,
                    "transaction_hash": "a1b2c3d4e5f6...",
                    "provider_reference": "PM-CHECKOUT-abc123xyz",
                    "status": "PAID",
               }
          }
     )
