# models/payment_ledger.py
"""
PaymentLedger model - blockchain-like immutable record of confirmed payments.

Each record stores a SHA-256 hash of (invoice_id + tenant_id + amount + timestamp)
and a reference to the previous record's hash, forming a chain.
Records are append-only; modification is prevented at the application layer.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base


class PaymentLedger(Base):
     """
     Immutable payment ledger entry. Created when an invoice is marked PAID.
     Chain is formed via previous_hash -> next record's previous_hash.
     """
     __tablename__ = "payment_ledger"

     id = Column(Integer, primary_key=True, autoincrement=True)
     invoice_id = Column(
          Integer,
          ForeignKey("invoices.id", ondelete="RESTRICT"),  # Prevent delete if ledger exists
          nullable=False,
          unique=True,  # One ledger entry per invoice payment
          index=True
     )
     transaction_hash = Column(String(64), nullable=False, unique=True, index=True)  # SHA-256 hex length
     previous_hash = Column(String(64), nullable=False, index=True)  # "0" for genesis
     timestamp = Column(DateTime, server_default=func.now(), nullable=False)

     # Relationships
     invoice = relationship("Invoice", back_populates="payment_ledger_entry", uselist=False)

     def __repr__(self):
          return f"<PaymentLedger(id={self.id}, invoice_id={self.invoice_id}, hash={self.transaction_hash[:16]}...)>"
