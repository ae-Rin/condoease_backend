# routers/invoices.py
"""
Invoice API routes for CondoEase backend.

Provides CRUD operations for managing tenant invoices.
Role-based access:
- Tenant: can only access own invoices
- Admin / Manager / Unit Owner: can view related invoices
"""
from calendar import monthrange
from datetime import date
from typing import Optional, List, Set
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database import get_session
from models import Invoice, Tenant, Lease, Property, PropertyUnit, PropertyOwner
from services.ledger_service import append_payment_record, verify_ledger_entry, verify_full_chain
from schemas.invoice import (
     InvoiceCreate,
     InvoiceUpdate,
     InvoiceResponse,
     InvoiceListResponse,
     InvoiceStatusEnum,
)

# Import existing auth dependency from main.py
# Note: In production, move verify_token to a dependencies module
from main import verify_token

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


# ---------------------------------------------------------------------------
# Role-based access control helpers
# ---------------------------------------------------------------------------

def _get_tenant_id_for_user(db: Session, user_id: int) -> Optional[int]:
     """Get tenant_id for a user (role=tenant). Returns None if user is not a tenant."""
     tenant = db.query(Tenant).filter(Tenant.user_id == user_id).first()
     return tenant.tenant_id if tenant else None


def _get_owner_id_for_user(db: Session, user_id: int) -> Optional[int]:
     """Get owner_id for a user (role=owner). Returns None if user is not an owner."""
     owner = db.query(PropertyOwner).filter(PropertyOwner.user_id == user_id).first()
     return owner.owner_id if owner else None


def _get_accessible_tenant_ids(db: Session, token: dict) -> Optional[Set[int]]:
     """
     Get set of tenant_ids the current user can access.
     - Admin/Manager: None (meaning all tenants)
     - Tenant: {own tenant_id}
     - Owner: set of tenant_ids who have leases on this owner's properties
     """
     role = token.get("role")
     user_id = token.get("id")
     if not user_id:
          return set()

     if role in ("admin", "manager"):
          return None  # None = all tenants

     if role == "tenant":
          tenant_id = _get_tenant_id_for_user(db, user_id)
          return {tenant_id} if tenant_id is not None else set()

     if role == "owner":
          owner_id = _get_owner_id_for_user(db, user_id)
          if owner_id is None:
               return set()
          # Tenant IDs who have leases on properties owned by this owner
          leases = (
               db.query(Lease.tenant_id)
               .join(Property, Lease.property_id == Property.id)
               .filter(Property.registered_owner == owner_id)
               .distinct()
               .all()
          )
          return {row[0] for row in leases}

     return set()


def _can_access_tenant_invoices(db: Session, token: dict, tenant_id: int) -> bool:
     """Check if current user can access invoices for the given tenant_id."""
     allowed = _get_accessible_tenant_ids(db, token)
     if allowed is None:
          return True  # Admin/manager: all
     return tenant_id in allowed


def _can_access_invoice(db: Session, token: dict, invoice: Invoice) -> bool:
     """Check if current user can access the given invoice."""
     allowed = _get_accessible_tenant_ids(db, token)
     if allowed is None:
          return True  # Admin/manager: all
     return invoice.tenant_id in allowed


@router.post(
     "",
     response_model=InvoiceResponse,
     status_code=status.HTTP_201_CREATED,
     summary="Create a new invoice"
)
def create_invoice(
     invoice_data: InvoiceCreate,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Create a new invoice for a tenant's lease.
     
     - **tenant_id**: ID of the tenant being billed
     - **lease_id**: ID of the associated lease
     - **amount**: Invoice amount (must be positive)
     - **due_date**: Payment due date
     - **status**: Payment status (defaults to PENDING)
     """
     # Verify tenant exists
     tenant = db.query(Tenant).filter(Tenant.tenant_id == invoice_data.tenant_id).first()
     if not tenant:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Tenant with ID {invoice_data.tenant_id} not found"
          )
     
     # Verify lease exists and belongs to tenant
     lease = db.query(Lease).filter(Lease.id == invoice_data.lease_id).first()
     if not lease:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Lease with ID {invoice_data.lease_id} not found"
          )
     
     if lease.tenant_id != invoice_data.tenant_id:
          raise HTTPException(
               status_code=status.HTTP_400_BAD_REQUEST,
               detail="Lease does not belong to the specified tenant"
          )
     
     # Create invoice
     invoice = Invoice(
          tenant_id=invoice_data.tenant_id,
          lease_id=invoice_data.lease_id,
          amount=invoice_data.amount,
          due_date=invoice_data.due_date,
          status=invoice_data.status,
     )
     
     db.add(invoice)
     db.commit()
     db.refresh(invoice)
     
     return _build_invoice_response(invoice, db)


@router.get(
     "",
     response_model=InvoiceListResponse,
     summary="List all invoices with filters"
)
def list_invoices(
     tenant_id: Optional[int] = Query(None, description="Filter by tenant ID"),
     lease_id: Optional[int] = Query(None, description="Filter by lease ID"),
     status: Optional[InvoiceStatusEnum] = Query(None, description="Filter by status"),
     overdue_only: bool = Query(False, description="Show only overdue invoices"),
     page: int = Query(1, ge=1, description="Page number"),
     page_size: int = Query(50, ge=1, le=100, description="Items per page"),
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Retrieve a paginated list of invoices with optional filters.

     **Role-based access:**
     - **Tenant**: Only own invoices (tenant_id filter ignored if different).
     - **Admin / Manager**: All invoices.
     - **Unit Owner**: Only invoices for tenants on their properties.

     Filters:
     - **tenant_id**: Show invoices for specific tenant
     - **lease_id**: Show invoices for specific lease
     - **status**: Filter by payment status (PENDING, PAID, OVERDUE)
     - **overdue_only**: Show only overdue invoices
     """
     query = db.query(Invoice)

     # Role-based filter: restrict to accessible tenant_ids
     allowed_tenant_ids = _get_accessible_tenant_ids(db, token)
     if allowed_tenant_ids is not None:
          if not allowed_tenant_ids:
               return InvoiceListResponse(invoices=[], total=0, page=page, page_size=page_size)
          query = query.filter(Invoice.tenant_id.in_(allowed_tenant_ids))
          # If tenant role and they passed tenant_id, must be their own
          if token.get("role") == "tenant" and tenant_id is not None:
               my_tenant_id = _get_tenant_id_for_user(db, token.get("id"))
               if tenant_id != my_tenant_id:
                    return InvoiceListResponse(invoices=[], total=0, page=page, page_size=page_size)

     # Apply filters
     if tenant_id:
          query = query.filter(Invoice.tenant_id == tenant_id)

     if lease_id:
          query = query.filter(Invoice.lease_id == lease_id)
     
     if status:
          query = query.filter(Invoice.status == status)
     
     if overdue_only:
          query = query.filter(
               and_(
                    Invoice.status == InvoiceStatusEnum.PENDING,
                    Invoice.due_date < date.today()
               )
          )
     
     # Get total count
     total = query.count()
     
     # Apply pagination
     offset = (page - 1) * page_size
     invoices = query.order_by(Invoice.due_date.desc()).offset(offset).limit(page_size).all()
     
     # Build responses with related data
     invoice_responses = [_build_invoice_response(inv, db) for inv in invoices]
     
     return InvoiceListResponse(
          invoices=invoice_responses,
          total=total,
          page=page,
          page_size=page_size
     )


# ---------------------------------------------------------------------------
# Invoice management endpoints (role-based access)
# ---------------------------------------------------------------------------

@router.get(
     "/tenant/{tenant_id}",
     response_model=InvoiceListResponse,
     summary="Get invoices for a tenant"
)
def get_invoices_by_tenant(
     tenant_id: int,
     page: int = Query(1, ge=1, description="Page number"),
     page_size: int = Query(50, ge=1, le=100, description="Items per page"),
     status: Optional[InvoiceStatusEnum] = Query(None, description="Filter by status"),
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Get all invoices for a specific tenant.

     **Role-based access:**
     - **Tenant**: Can only access own invoices (tenant_id must match logged-in tenant).
     - **Admin / Manager**: Can view any tenant's invoices.
     - **Unit Owner**: Can view invoices for tenants who have leases on their properties.
     """
     if not _can_access_tenant_invoices(db, token, tenant_id):
          raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="You do not have permission to view invoices for this tenant"
          )

     tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
     if not tenant:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Tenant with ID {tenant_id} not found"
          )

     query = db.query(Invoice).filter(Invoice.tenant_id == tenant_id)
     if status is not None:
          query = query.filter(Invoice.status == status)

     total = query.count()
     offset = (page - 1) * page_size
     invoices = query.order_by(Invoice.due_date.desc()).offset(offset).limit(page_size).all()
     invoice_responses = [_build_invoice_response(inv, db) for inv in invoices]

     return InvoiceListResponse(
          invoices=invoice_responses,
          total=total,
          page=page,
          page_size=page_size
     )


@router.get(
     "/month/{year}/{month}",
     response_model=InvoiceListResponse,
     summary="Get invoices for a month"
)
def get_invoices_by_month(
     year: int,
     month: int,
     page: int = Query(1, ge=1, description="Page number"),
     page_size: int = Query(50, ge=1, le=100, description="Items per page"),
     status: Optional[InvoiceStatusEnum] = Query(None, description="Filter by status"),
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Get all invoices with due date in the given year/month.

     **Role-based access:**
     - **Tenant**: Only own invoices for that month.
     - **Admin / Manager**: All invoices for that month.
     - **Unit Owner**: Invoices for tenants who have leases on their properties.
     """
     if month < 1 or month > 12:
          raise HTTPException(
               status_code=status.HTTP_400_BAD_REQUEST,
               detail="Month must be between 1 and 12"
          )

     first_day = date(year, month, 1)
     last_day = date(year, month, monthrange(year, month)[1])

     query = db.query(Invoice).filter(
          and_(
               Invoice.due_date >= first_day,
               Invoice.due_date <= last_day
          )
     )

     allowed_tenant_ids = _get_accessible_tenant_ids(db, token)
     if allowed_tenant_ids is not None:
          if not allowed_tenant_ids:
               return InvoiceListResponse(invoices=[], total=0, page=page, page_size=page_size)
          query = query.filter(Invoice.tenant_id.in_(allowed_tenant_ids))

     if status is not None:
          query = query.filter(Invoice.status == status)

     total = query.count()
     offset = (page - 1) * page_size
     invoices = query.order_by(Invoice.due_date.desc()).offset(offset).limit(page_size).all()
     invoice_responses = [_build_invoice_response(inv, db) for inv in invoices]

     return InvoiceListResponse(
          invoices=invoice_responses,
          total=total,
          page=page,
          page_size=page_size
     )


# ---------------------------------------------------------------------------
# Payment ledger verification (blockchain-like)
# ---------------------------------------------------------------------------

@router.get(
     "/ledger/verify-chain",
     summary="Verify full payment ledger chain"
)
def verify_ledger_chain(
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token),
):
     """
     Recompute hashes for all ledger entries and verify the chain.
     Returns verification result and number of entries checked.
     """
     valid, message, count = verify_full_chain(db)
     return {
          "verified": valid,
          "message": message,
          "entries_checked": count,
     }


@router.get(
     "/{invoice_id}/ledger/verify",
     summary="Verify payment ledger entry for an invoice"
)
def verify_invoice_ledger(
     invoice_id: int,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token),
):
     """
     Recompute hash from invoice_id + tenant_id + amount + timestamp
     and compare with stored hash. Also verifies previous_hash chain link.
     """
     invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
     if not invoice:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Invoice with ID {invoice_id} not found"
          )
     if not _can_access_invoice(db, token, invoice):
          raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="You do not have permission to view this invoice"
          )
     valid, message = verify_ledger_entry(db, invoice_id=invoice_id)
     return {
          "verified": valid,
          "message": message,
          "invoice_id": invoice_id,
     }


@router.get(
     "/{invoice_id}",
     response_model=InvoiceResponse,
     summary="Get invoice by ID"
)
def get_invoice(
     invoice_id: int,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Retrieve a specific invoice by ID with related tenant and lease information.

     **Role-based access:**
     - **Tenant**: Can only access own invoices.
     - **Admin / Manager**: Can access any invoice.
     - **Unit Owner**: Can access invoices for tenants on their properties.
     """
     invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

     if not invoice:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Invoice with ID {invoice_id} not found"
          )

     if not _can_access_invoice(db, token, invoice):
          raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="You do not have permission to view this invoice"
          )

     return _build_invoice_response(invoice, db)


@router.put(
     "/{invoice_id}",
     response_model=InvoiceResponse,
     summary="Update invoice"
)
def update_invoice(
     invoice_id: int,
     invoice_data: InvoiceUpdate,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Update an existing invoice.
     
     Only provided fields will be updated. Common use cases:
     - Mark invoice as PAID
     - Update amount or due date
     - Mark as OVERDUE
     """
     invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
     
     if not invoice:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Invoice with ID {invoice_id} not found"
          )
     
     # Update fields if provided
     if invoice_data.amount is not None:
          invoice.amount = invoice_data.amount
     
     if invoice_data.due_date is not None:
          invoice.due_date = invoice_data.due_date
     
     if invoice_data.status is not None:
          invoice.status = invoice_data.status
          # When marking as PAID, append to payment ledger (blockchain-like)
          if invoice_data.status == InvoiceStatusEnum.PAID:
               try:
                    append_payment_record(
                         db,
                         invoice.id,
                         invoice.tenant_id,
                         invoice.amount,
                         timestamp=None,
                    )
               except ValueError:
                    pass  # Ledger entry already exists for this invoice

     db.commit()
     db.refresh(invoice)

     return _build_invoice_response(invoice, db)


@router.patch(
     "/{invoice_id}/mark-paid",
     response_model=InvoiceResponse,
     summary="Mark invoice as paid"
)
def mark_invoice_paid(
     invoice_id: int,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Convenience endpoint to mark an invoice as PAID.
     On success, appends an immutable record to the payment ledger (blockchain-like).
     """
     invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

     if not invoice:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Invoice with ID {invoice_id} not found"
          )

     invoice.mark_as_paid()
     try:
          append_payment_record(
               db,
               invoice.id,
               invoice.tenant_id,
               invoice.amount,
               timestamp=None,
          )
     except ValueError:
          pass  # Ledger entry already exists (idempotent)

     db.commit()
     db.refresh(invoice)

     return _build_invoice_response(invoice, db)


@router.patch(
     "/{invoice_id}/mark-overdue",
     response_model=InvoiceResponse,
     summary="Mark invoice as overdue"
)
def mark_invoice_overdue(
     invoice_id: int,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Convenience endpoint to mark an invoice as OVERDUE.
     """
     invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
     
     if not invoice:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Invoice with ID {invoice_id} not found"
          )
     
     invoice.mark_as_overdue()
     db.commit()
     db.refresh(invoice)
     
     return _build_invoice_response(invoice, db)


@router.delete(
     "/{invoice_id}",
     status_code=status.HTTP_204_NO_CONTENT,
     summary="Delete invoice"
)
def delete_invoice(
     invoice_id: int,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
):
     """
     Delete an invoice by ID.
     
     Note: This permanently removes the invoice record.
     """
     role = token.get("role")
     if role not in ["admin", "manager"]:
          raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="Only admins and managers can delete invoices"
          )
     
     invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
     
     if not invoice:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Invoice with ID {invoice_id} not found"
          )
     
     db.delete(invoice)
     db.commit()
     
     return None


@router.get(
     "/tenant/{tenant_id}/summary",
     summary="Get tenant invoice summary"
)
def get_tenant_invoice_summary(
     tenant_id: int,
     db: Session = Depends(get_session),
     token: dict = Depends(verify_token)
     ):
     """
     Get summary statistics for a tenant's invoices.

     **Role-based access:** Same as GET /tenant/{tenant_id}.

     Returns:
     - Total invoices
     - Total amount owed
     - Paid invoices count and amount
     - Pending invoices count and amount
     - Overdue invoices count and amount
     """
     if not _can_access_tenant_invoices(db, token, tenant_id):
          raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="You do not have permission to view invoice summary for this tenant"
          )

     tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
     if not tenant:
          raise HTTPException(
               status_code=status.HTTP_404_NOT_FOUND,
               detail=f"Tenant with ID {tenant_id} not found"
          )
     
     invoices = db.query(Invoice).filter(Invoice.tenant_id == tenant_id).all()
     
     total_count = len(invoices)
     total_amount = sum(inv.amount for inv in invoices)
     
     paid = [inv for inv in invoices if inv.status == InvoiceStatusEnum.PAID]
     pending = [inv for inv in invoices if inv.status == InvoiceStatusEnum.PENDING]
     overdue = [inv for inv in invoices if inv.status == InvoiceStatusEnum.OVERDUE]
     
     return {
          "tenant_id": tenant_id,
          "tenant_name": f"{tenant.first_name} {tenant.last_name}",
          "total_invoices": total_count,
          "total_amount": float(total_amount),
          "paid": {
               "count": len(paid),
               "amount": float(sum(inv.amount for inv in paid))
          },
          "pending": {
               "count": len(pending),
               "amount": float(sum(inv.amount for inv in pending))
          },
          "overdue": {
               "count": len(overdue),
               "amount": float(sum(inv.amount for inv in overdue))
          }
     }


def _build_invoice_response(invoice: Invoice, db: Session) -> InvoiceResponse:
     """
     Helper function to build InvoiceResponse with related data.
     """
     # Get tenant info
     tenant = db.query(Tenant).filter(Tenant.tenant_id == invoice.tenant_id).first()
     
     # Get lease and property info
     lease = db.query(Lease).filter(Lease.id == invoice.lease_id).first()
     property_name = None
     unit_number = None
     
     if lease:
          if lease.property_id:
               property_obj = db.query(Property).filter(Property.id == lease.property_id).first()
               if property_obj:
                    property_name = property_obj.property_name
          
          if lease.property_unit_id:
               unit = db.query(PropertyUnit).filter(PropertyUnit.id == lease.property_unit_id).first()
               if unit:
                    unit_number = unit.unit_number
     
     return InvoiceResponse(
          id=invoice.id,
          tenant_id=invoice.tenant_id,
          lease_id=invoice.lease_id,
          amount=invoice.amount,
          due_date=invoice.due_date,
          status=invoice.status,
          created_at=invoice.created_at,
          tenant_name=f"{tenant.first_name} {tenant.last_name}" if tenant else None,
          tenant_email=tenant.email if tenant else None,
          property_name=property_name,
          unit_number=unit_number,
     )
