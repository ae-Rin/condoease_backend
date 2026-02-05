# services/invoice_service.py
"""
Invoice Service - Business logic layer for invoice operations.

This service handles invoice creation, updates, and business rules
separate from the API layer.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session

from models import Invoice, Tenant, Lease
from models.invoice import InvoiceStatus


class InvoiceService:
     """Service class for invoice-related business logic."""
     
     @staticmethod
     def create_invoice_for_lease(
          db: Session,
          lease_id: int,
          tenant_id: int,
          amount: Decimal,
          start_date: date,
          due_date_offset_days: int = 30
     ) -> Invoice:
          """
          Create an invoice for a lease.
          
          Args:
               db: SQLAlchemy database session
               lease_id: ID of the lease
               tenant_id: ID of the tenant
               amount: Invoice amount
               start_date: Lease start date
               due_date_offset_days: Days from start_date to set due_date (default: 30)
          
          Returns:
               Created Invoice object
          
          Raises:
               ValueError: If tenant or lease doesn't exist
          """
          # Verify tenant exists
          tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
          if not tenant:
               raise ValueError(f"Tenant with ID {tenant_id} not found")
          
          # Verify lease exists
          lease = db.query(Lease).filter(Lease.id == lease_id).first()
          if not lease:
               raise ValueError(f"Lease with ID {lease_id} not found")
          
          # Calculate due date
          due_date = start_date + timedelta(days=due_date_offset_days)
          
          # Create invoice
          invoice = Invoice(
               tenant_id=tenant_id,
               lease_id=lease_id,
               amount=amount,
               due_date=due_date,
               status=InvoiceStatus.PENDING
          )
          
          db.add(invoice)
          db.flush()  # Flush to get the ID without committing
          
          return invoice
     
     @staticmethod
     def create_initial_lease_invoice(
          db: Session,
          lease_id: int,
          tenant_id: int,
          rent_price: Decimal,
          start_date: date
     ) -> Invoice:
          """
          Create the initial invoice when a lease is created.
          
          This is automatically called when a new lease is created.
          The invoice amount is set to the rent price, and the due date
          is set to 1 month from the lease start date.
          
          Args:
               db: SQLAlchemy database session
               lease_id: ID of the newly created lease
               tenant_id: ID of the tenant
               rent_price: Monthly rent price from the lease
               start_date: Lease start date
          
          Returns:
               Created Invoice object
          """
          return InvoiceService.create_invoice_for_lease(
               db=db,
               lease_id=lease_id,
               tenant_id=tenant_id,
               amount=rent_price,
               start_date=start_date,
               due_date_offset_days=30  # 1 month from start date
          )
     
     @staticmethod
     def generate_monthly_invoices(
          db: Session,
          lease_id: Optional[int] = None
     ) -> list[Invoice]:
          """
          Generate monthly invoices for active leases.
          
          This can be called by a scheduled job to automatically
          create invoices for all active leases.
          
          Args:
               db: SQLAlchemy database session
               lease_id: Optional specific lease ID (if None, processes all active leases)
          
          Returns:
               List of created Invoice objects
          """
          today = date.today()
          
          # Query for active leases
          query = db.query(Lease).filter(Lease.end_date >= today)
          
          if lease_id:
               query = query.filter(Lease.id == lease_id)
          
          active_leases = query.all()
          
          created_invoices = []
          
          for lease in active_leases:
               # Check if invoice already exists for this month
               existing = db.query(Invoice).filter(
                    Invoice.lease_id == lease.id,
                    Invoice.due_date >= today,
                    Invoice.due_date < today + timedelta(days=31)
               ).first()
               
               if not existing:
                    invoice = InvoiceService.create_invoice_for_lease(
                         db=db,
                         lease_id=lease.id,
                         tenant_id=lease.tenant_id,
                         amount=lease.rent_price,
                         start_date=today,
                         due_date_offset_days=30
                    )
                    created_invoices.append(invoice)
          
          return created_invoices
     
     @staticmethod
     def mark_overdue_invoices(db: Session) -> int:
          """
          Mark all pending invoices past their due date as OVERDUE.
          
          This should be called by a scheduled job daily.
          
          Args:
               db: SQLAlchemy database session
          
          Returns:
               Number of invoices marked as overdue
          """
          today = date.today()
          
          overdue_invoices = db.query(Invoice).filter(
               Invoice.status == InvoiceStatus.PENDING,
               Invoice.due_date < today
          ).all()
          
          count = 0
          for invoice in overdue_invoices:
               invoice.mark_as_overdue()
               count += 1
          
          return count
     
     @staticmethod
     def calculate_tenant_balance(db: Session, tenant_id: int) -> dict:
          """
          Calculate the total balance owed by a tenant.
          
          Args:
               db: SQLAlchemy database session
               tenant_id: ID of the tenant
          
          Returns:
               Dictionary with balance information
          """
          invoices = db.query(Invoice).filter(Invoice.tenant_id == tenant_id).all()
          
          pending = [inv for inv in invoices if inv.status == InvoiceStatus.PENDING]
          overdue = [inv for inv in invoices if inv.status == InvoiceStatus.OVERDUE]
          paid = [inv for inv in invoices if inv.status == InvoiceStatus.PAID]
          
          return {
               "tenant_id": tenant_id,
               "total_owed": float(sum(inv.amount for inv in pending + overdue)),
               "pending_amount": float(sum(inv.amount for inv in pending)),
               "overdue_amount": float(sum(inv.amount for inv in overdue)),
               "paid_amount": float(sum(inv.amount for inv in paid)),
               "total_invoices": len(invoices),
               "pending_count": len(pending),
               "overdue_count": len(overdue),
               "paid_count": len(paid)
          }
