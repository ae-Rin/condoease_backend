# Payment Ledger (Blockchain-like)

Immutable, chain-linked record of confirmed payments. When an invoice is marked PAID, a ledger entry is appended with a SHA-256 hash; verification recomputes the hash and checks the chain.

---

## Model: PaymentLedger

| Column            | Type     | Description                                      |
|-------------------|----------|--------------------------------------------------|
| `id`              | PK       | Auto-increment                                  |
| `invoice_id`     | FK       | Reference to `invoices.id` (unique, one per invoice) |
| `transaction_hash`| String(64)| SHA-256 hex of payload                          |
| `previous_hash`   | String(64)| Hash of previous ledger entry; `"0"` for genesis |
| `timestamp`       | DateTime | When the payment was recorded                   |

- **Immutability:** No update/delete API for ledger rows; only append on payment confirm.
- **Chain:** Each row’s `previous_hash` equals the previous row’s `transaction_hash` (genesis uses `"0"`).

---

## Hash Computation

**Payload (canonical string):**

```text
invoice_id|tenant_id|amount|timestamp
```

- `amount`: two decimal places (e.g. `"5000.00"`).
- `timestamp`: ISO format.

**Algorithm:** `SHA-256(payload).hexdigest()` → 64-char hex string.

---

## When a Payment Is Confirmed

1. Invoice is set to PAID (e.g. PATCH `/api/invoices/{id}/mark-paid` or PUT with `status: PAID`).
2. **Compute** `transaction_hash = SHA256(invoice_id|tenant_id|amount|timestamp)`.
3. **Set** `previous_hash` = last ledger row’s `transaction_hash`, or `"0"` if ledger is empty.
4. **Insert** one new row into `payment_ledger` (no updates/deletes).

Duplicate append for the same invoice is avoided (unique on `invoice_id`); repeated “mark paid” is idempotent.

---

## Verification

### Single entry (by invoice)

- **Input:** `invoice_id` (or ledger `id`).
- **Steps:**
  1. Load ledger row and linked invoice.
  2. Recompute hash from `invoice_id`, `tenant_id`, `amount`, `timestamp` (using stored `timestamp`).
  3. Compare with stored `transaction_hash`.
  4. If `previous_hash != "0"`, check that it equals the previous row’s `transaction_hash`.
- **Result:** `(verified: bool, message: str)`.

### Full chain

- Iterate all ledger rows in order; for each row, recompute hash and check:
  - Stored `transaction_hash` matches computed hash.
  - `previous_hash` matches the previous row’s `transaction_hash` (genesis: `"0"`).
- **Result:** `(all_valid, message, entries_checked)`.

---

## API Endpoints

- **GET** `/api/invoices/{invoice_id}/ledger/verify`  
  - Verifies the ledger entry for that invoice (same RBAC as viewing the invoice).  
  - Response: `{ "verified": bool, "message": str, "invoice_id": int }`.

- **GET** `/api/invoices/ledger/verify-chain`  
  - Verifies the entire ledger chain.  
  - Response: `{ "verified": bool, "message": str, "entries_checked": int }`.

---

## Service API (services/ledger_service.py)

| Function                     | Purpose |
|-----------------------------|--------|
| `compute_transaction_hash(invoice_id, tenant_id, amount, timestamp)` | Returns 64-char SHA-256 hex. |
| `get_previous_hash(db)`     | Last row’s `transaction_hash`, or `"0"`. |
| `append_payment_record(db, invoice_id, tenant_id, amount, timestamp=None)` | Appends one immutable row; raises if ledger entry for `invoice_id` already exists. |
| `verify_ledger_entry(db, ledger_id=None, invoice_id=None)` | Recompute and compare; optional chain check. Returns `(bool, str)`. |
| `verify_full_chain(db)`     | Verify all rows and chain. Returns `(bool, str, int)`. |

---

## Migration

- **Alembic:** `alembic/versions/20260131_000002_create_payment_ledger_table.py`
- **Apply:** `alembic upgrade head`

---

## Immutability

- **Application:** No update/delete of `PaymentLedger`; only insert via `append_payment_record` when payment is confirmed.
- **Database:** `invoice_id` has a unique constraint; FK to `invoices.id` with `ON DELETE RESTRICT` so invoices with ledger entries cannot be deleted without first handling the ledger (e.g. by design you don’t delete them).

This gives a blockchain-like, tamper-evident log of confirmed payments with a verification function that recomputes the hash and returns the verification result.
