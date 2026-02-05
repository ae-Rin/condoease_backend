# schemas/invoice.py
"""
Pydantic schemas for Invoice API request/response validation.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class InvoiceStatusEnum(str, Enum):
     """Invoice payment status options."""
     PENDING = "PENDING"
     PAID = "PAID"
     OVERDUE = "OVERDUE"


class InvoiceCreate(BaseModel):
     """Schema for creating a new invoice."""
     tenant_id: int = Field(..., gt=0, description="Tenant ID (must exist)")
     lease_id: int = Field(..., gt=0, description="Lease ID (must exist)")
     amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2, description="Invoice amount")
     due_date: date = Field(..., description="Payment due date")
     status: InvoiceStatusEnum = Field(default=InvoiceStatusEnum.PENDING, description="Payment status")

     model_config = ConfigDict(
          json_schema_extra={
               "example": {
                    "tenant_id": 1,
                    "lease_id": 1,
                    "amount": 5000.00,
                    "due_date": "2026-02-28",
                    "status": "PENDING"
               }
          }
     )


class InvoiceUpdate(BaseModel):
     """Schema for updating an existing invoice."""
     amount: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
     due_date: Optional[date] = None
     status: Optional[InvoiceStatusEnum] = None

     model_config = ConfigDict(
          json_schema_extra={
               "example": {
                    "status": "PAID"
               }
          }
     )


class InvoiceResponse(BaseModel):
     """Schema for invoice response."""
     id: int
     tenant_id: int
     lease_id: int
     amount: Decimal
     due_date: date
     status: InvoiceStatusEnum
     created_at: datetime
     
     # Optional related data
     tenant_name: Optional[str] = None
     tenant_email: Optional[str] = None
     property_name: Optional[str] = None
     unit_number: Optional[str] = None

     model_config = ConfigDict(
          from_attributes=True,
          json_schema_extra={
               "example": {
                    "id": 1,
                    "tenant_id": 1,
                    "lease_id": 1,
                    "amount": 5000.00,
                    "due_date": "2026-02-28",
                    "status": "PENDING",
                    "created_at": "2026-01-31T10:30:00",
                    "tenant_name": "John Doe",
                    "tenant_email": "john@example.com",
                    "property_name": "Sunset Condos",
                    "unit_number": "Unit 101"
               }
          }
     )


class InvoiceListResponse(BaseModel):
     """Schema for paginated invoice list response."""
     invoices: List[InvoiceResponse]
     total: int
     page: int = 1
     page_size: int = 50

     model_config = ConfigDict(
          json_schema_extra={
               "example": {
                    "invoices": [],
                    "total": 0,
                    "page": 1,
                    "page_size": 50
               }
          }
     )
