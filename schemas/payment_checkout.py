# schemas/payment_checkout.py
from pydantic import BaseModel, Field
from decimal import Decimal

class CheckoutRequest(BaseModel):
     invoice_id: int = Field(..., gt=0, description="Invoice to create checkout for")
     