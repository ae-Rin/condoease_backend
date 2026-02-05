# services/ledger_service.py
"""
Payment Ledger Service - blockchain-like immutable payment records.

When a payment is confirmed (invoice marked PAID):
1. Compute SHA-256 hash from invoice_id + tenant_id + amount + timestamp
2. Store record with reference to previous record's hash (chain)
3. Ledger records are append-only; no update/delete

Verification: recompute hash and compare with stored hash; optionally verify chain.
"""
import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models import PaymentLedger, Invoice


# Genesis block: no previous record
GENESIS_HASH = "0"


def _normalize_amount(amount: Decimal) -> str:
     """Normalize amount to canonical string for hashing (2 decimal places)."""
     return f"{float(amount):.2f}"


def _normalize_timestamp(ts: datetime) -> str:
     """Normalize timestamp to ISO format for deterministic hashing."""
     return ts.isoformat()


def compute_transaction_hash(
     invoice_id: int,
     tenant_id: int,
     amount: Decimal,
     timestamp: datetime
) -> str:
     """
     Compute SHA-256 hash for a payment record.

     Input string: invoice_id|tenant_id|amount|timestamp (canonical format).
     Returns 64-char hex string.
     """
     payload = "|".join([
          str(invoice_id),
          str(tenant_id),
          _normalize_amount(amount),
          _normalize_timestamp(timestamp)
     ])
     return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_previous_hash(db: Session) -> str:
     """Get the transaction_hash of the most recent ledger entry, or GENESIS_HASH if empty."""
     last = db.query(PaymentLedger).order_by(desc(PaymentLedger.id)).limit(1).first()
     if last is None:
          return GENESIS_HASH
     return last.transaction_hash


def append_payment_record(
     db: Session,
     invoice_id: int,
     tenant_id: int,
     amount: Decimal,
     timestamp: Optional[datetime] = None
) -> PaymentLedger:
     """
     Append an immutable payment record to the ledger (when payment is confirmed).

     - Computes transaction_hash from invoice_id + tenant_id + amount + timestamp
     - Sets previous_hash to the last record's transaction_hash (or "0")
     - Does NOT update or delete existing records (immutability)

     Raises:
          ValueError: If invoice_id already has a ledger entry (double record).
     """
     if timestamp is None:
          timestamp = datetime.utcnow()

     existing = db.query(PaymentLedger).filter(PaymentLedger.invoice_id == invoice_id).first()
     if existing:
          raise ValueError(f"Ledger entry already exists for invoice_id={invoice_id}")

     transaction_hash = compute_transaction_hash(invoice_id, tenant_id, amount, timestamp)
     previous_hash = get_previous_hash(db)

     entry = PaymentLedger(
          invoice_id=invoice_id,
          transaction_hash=transaction_hash,
          previous_hash=previous_hash,
          timestamp=timestamp
     )
     db.add(entry)
     db.flush()
     return entry


def verify_ledger_entry(
     db: Session,
     ledger_id: Optional[int] = None,
     invoice_id: Optional[int] = None
) -> Tuple[bool, str]:
     """
     Verify a ledger entry by recomputing the hash and comparing.

     Pass either ledger_id or invoice_id to identify the entry.

     Returns:
          (success: bool, message: str)
          - (True, "Verification passed") if hash matches
          - (False, reason) if hash mismatch, missing record, or chain broken
     """
     if ledger_id is not None:
          entry = db.query(PaymentLedger).filter(PaymentLedger.id == ledger_id).first()
     elif invoice_id is not None:
          entry = db.query(PaymentLedger).filter(PaymentLedger.invoice_id == invoice_id).first()
     else:
          return False, "Must provide ledger_id or invoice_id"

     if entry is None:
          return False, "Ledger entry not found"

     invoice = db.query(Invoice).filter(Invoice.id == entry.invoice_id).first()
     if invoice is None:
          return False, "Invoice not found"

     computed = compute_transaction_hash(
          entry.invoice_id,
          invoice.tenant_id,
          invoice.amount,
          entry.timestamp
     )

     if computed != entry.transaction_hash:
          return False, f"Hash mismatch: stored={entry.transaction_hash[:16]}..., computed={computed[:16]}..."

     # Optionally verify chain: previous_hash should match previous record's transaction_hash
     if entry.previous_hash != GENESIS_HASH:
          prev_entry = (
               db.query(PaymentLedger)
               .filter(PaymentLedger.id < entry.id)
               .order_by(desc(PaymentLedger.id))
               .limit(1)
               .first()
          )
          if prev_entry is None:
               return False, "Previous chain link not found"
          if prev_entry.transaction_hash != entry.previous_hash:
               return False, "Chain broken: previous_hash does not match previous record"

     return True, "Verification passed"


def verify_full_chain(db: Session) -> Tuple[bool, str, int]:
     """
     Verify the entire ledger chain from first to last entry.

     Returns:
          (all_valid: bool, message: str, entries_checked: int)
     """
     entries = db.query(PaymentLedger).order_by(PaymentLedger.id).all()
     if not entries:
          return True, "Chain is empty (no entries)", 0

     prev_hash = GENESIS_HASH
     checked = 0

     for entry in entries:
          if entry.previous_hash != prev_hash:
               return False, f"Chain broken at id={entry.id}: previous_hash mismatch", checked
          invoice = db.query(Invoice).filter(Invoice.id == entry.invoice_id).first()
          if not invoice:
               return False, f"Invoice not found for ledger id={entry.id}", checked
          computed = compute_transaction_hash(
               entry.invoice_id,
               invoice.tenant_id,
               invoice.amount,
               entry.timestamp
          )
          if computed != entry.transaction_hash:
               return False, f"Hash mismatch at ledger id={entry.id}", checked
          prev_hash = entry.transaction_hash
          checked += 1

     return True, "Full chain verification passed", checked
