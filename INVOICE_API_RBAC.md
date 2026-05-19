# Invoice API – Role-Based Access Control

This document describes the invoice management endpoints and their role-based access rules.

---

## Endpoints

All endpoints use the prefix **`/api/invoices`** and require **JWT authentication** (`Authorization: Bearer <token>`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/invoices/tenant/{tenant_id}` | List invoices for a tenant |
| GET | `/api/invoices/month/{year}/{month}` | List invoices for a given month |
| GET | `/api/invoices/{invoice_id}` | Get a single invoice by ID |

---

## Role-Based Access

### Tenant

- **Own invoices only**
- Can call:
  - `GET /api/invoices/tenant/{tenant_id}` only when `tenant_id` is their own
  - `GET /api/invoices/month/{year}/{month}` and only see their invoices for that month
  - `GET /api/invoices/{invoice_id}` only for their own invoices
- **403 Forbidden** if they try to access another tenant’s invoices

### Admin / Manager

- **All invoices**
- Can call any of the three endpoints for any tenant/month/invoice
- No tenant-based restriction

### Unit Owner

- **Invoices for “related” tenants only**
- “Related” = tenants who have a lease on a property where `registered_owner` is this owner
- Can call:
  - `GET /api/invoices/tenant/{tenant_id}` only for such tenants
  - `GET /api/invoices/month/{year}/{month}` and only see invoices for those tenants
  - `GET /api/invoices/{invoice_id}` only for invoices belonging to those tenants
- **403 Forbidden** for invoices of tenants not on their properties

### Agent

- Treated like **tenant** for now: only their own tenant record (if any) and thus only their own invoices when applicable.  
  (If your design gives agents a different scope, adjust `_get_accessible_tenant_ids` accordingly.)

---

## Endpoint Details

### 1. GET `/api/invoices/tenant/{tenant_id}`

Returns a **paginated list** of invoices for the given tenant.

**Query parameters (optional):**

- `page` (default: 1)
- `page_size` (default: 50, max: 100)
- `status`: `PENDING` \| `PAID` \| `OVERDUE`

**Access:**  
Caller must be allowed to see that tenant’s invoices (see roles above).  
If not allowed → **403 Forbidden**.  
If tenant does not exist → **404 Not Found**.

**Response:** `InvoiceListResponse`  
`invoices`, `total`, `page`, `page_size`.

---

### 2. GET `/api/invoices/month/{year}/{month}`

Returns a **paginated list** of invoices whose **due date** falls in the given calendar month.

**Path parameters:**

- `year`: e.g. `2026`
- `month`: 1–12

**Query parameters (optional):**

- `page` (default: 1)
- `page_size` (default: 50, max: 100)
- `status`: `PENDING` \| `PAID` \| `OVERDUE`

**Access:**  
Results are filtered by role:

- **Tenant:** only their invoices in that month
- **Admin/Manager:** all invoices in that month
- **Owner:** only invoices for tenants on their properties

**Response:** `InvoiceListResponse`  
`invoices`, `total`, `page`, `page_size`.

**Errors:**  
- Invalid month (e.g. 0 or 13) → **400 Bad Request**  
- Otherwise same as other invoice endpoints (401/403/404 as applicable).

---

### 3. GET `/api/invoices/{invoice_id}`

Returns **one invoice** by ID, with related tenant/lease/property/unit info.

**Access:**  
Caller must be allowed to see this invoice (same rules as above).  
If not found → **404 Not Found**.  
If not allowed → **403 Forbidden**.

**Response:** `InvoiceResponse`  
e.g. `id`, `tenant_id`, `lease_id`, `amount`, `due_date`, `status`, `created_at`, and optional `tenant_name`, `tenant_email`, `property_name`, `unit_number`.

---

## Response Schemas (existing)

- **InvoiceResponse** – single invoice (used by GET `/api/invoices/{invoice_id}` and inside lists).
- **InvoiceListResponse** – `invoices: List[InvoiceResponse]`, `total`, `page`, `page_size` (used by tenant and month endpoints).

No new Pydantic response schemas were added; these endpoints reuse the existing ones.

---

## Security Summary

- All three endpoints require a valid JWT (`verify_token`).
- Access is enforced in code via:
  - `_get_accessible_tenant_ids(token)` – which tenant IDs the user may see
  - `_can_access_tenant_invoices(db, token, tenant_id)` – for tenant-scoped requests
  - `_can_access_invoice(db, token, invoice)` – for single-invoice requests
- **Tenant:** only own `tenant_id`.
- **Admin/Manager:** all tenants.
- **Owner:** only tenants with leases on properties they own (`Property.registered_owner`).

---

## Example Requests

```bash
# List invoices for tenant 1 (must be allowed for this tenant)
curl -X GET "http://localhost:10000/api/invoices/tenant/1?page=1&page_size=10" \
  -H "Authorization: Bearer <token>"

# Invoices for February 2026 (filtered by role)
curl -X GET "http://localhost:10000/api/invoices/month/2026/2?page=1" \
  -H "Authorization: Bearer <token>"

# Single invoice (must be allowed for this invoice)
curl -X GET "http://localhost:10000/api/invoices/5" \
  -H "Authorization: Bearer <token>"
```

---

## Implementation Notes

- **PropertyOwner** model was added so owner access can be resolved from JWT `user_id` to `owner_id` and then to properties and leases.
- The generic **GET `/api/invoices`** (list with query filters) also applies the same role-based tenant filtering so tenants and owners only see allowed invoices.
- **GET `/api/invoices/tenant/{tenant_id}/summary`** uses the same RBAC as **GET `/api/invoices/tenant/{tenant_id}`** (must be allowed to see that tenant).
