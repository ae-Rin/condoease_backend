# models/invoice.py
import enum
from sqlalchemy import Column, Integer, Numeric, Date, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import relationship
from .base import Base


class InvoiceStatus(str, enum.Enum):
     """Enumeration for invoice payment status."""
     PENDING = "PENDING"
     PAID = "PAID"
     OVERDUE = "OVERDUE"


class Invoice(Base):
     """
     Invoice model - billing records for tenants based on their leases.
     
     This model tracks rent payments, utility bills, and other charges
     associated with a tenant's lease agreement.
     """
     __tablename__ = "invoices"

     id = Column(Integer, primary_key=True, autoincrement=True)
     
     # Foreign keys
     tenant_id = Column(
          Integer, 
          ForeignKey("tenants.tenant_id", ondelete="CASCADE"), 
          nullable=False,
          index=True
     )
     lease_id = Column(
          Integer, 
          ForeignKey("leases.id", ondelete="CASCADE"), 
          nullable=False,
          index=True
     )
     
     # Invoice details
     amount = Column(Numeric(12, 2), nullable=False)
     due_date = Column(Date, nullable=False, index=True)
     status = Column(
          Enum(InvoiceStatus, name="invoice_status", create_constraint=True),
          default=InvoiceStatus.PENDING,
          nullable=False,
          index=True
     )
     
     # Timestamps
     created_at = Column(DateTime, server_default=func.now(), nullable=False)
     
     # Relationships
     tenant = relationship("Tenant", back_populates="invoices")
     lease = relationship("Lease", back_populates="invoices")
     payment_ledger_entry = relationship(
          "PaymentLedger",
          back_populates="invoice",
          uselist=False,
          cascade="all, delete-orphan"
     )
     
     def __repr__(self):
          return f"<Invoice(id={self.id}, amount={self.amount}, status='{self.status.value}', due_date={self.due_date})>"
     
     @property
     def is_overdue(self) -> bool:
          """Check if invoice is past due date and unpaid."""
          from datetime import date
          return self.status == InvoiceStatus.PENDING and self.due_date < date.today()
     
     def mark_as_paid(self) -> None:
          """Mark the invoice as paid."""
          self.status = InvoiceStatus.PAID
     
     def mark_as_overdue(self) -> None:
          """Mark the invoice as overdue."""
          self.status = InvoiceStatus.OVERDUE
