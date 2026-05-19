# Invoice API Quick Reference

Complete API reference for the Invoice endpoints.

---

## 🔐 Authentication

All endpoints require JWT authentication:

```
Authorization: Bearer <your-jwt-token>
```

Get token from `/api/login` endpoint.

---

## 📋 Endpoints

### 1. Create Invoice

**POST** `/api/invoices`

Create a new invoice for a tenant's lease.

**Request Body:**
```json
{
  "tenant_id": 1,
  "lease_id": 1,
  "amount": 5000.00,
  "due_date": "2026-02-28",
  "status": "PENDING"
}
```

**Response:** `201 Created`
```json
{
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
```

**Validation:**
- `tenant_id` must exist in database
- `lease_id` must exist and belong to the tenant
- `amount` must be positive
- `status` must be one of: `PENDING`, `PAID`, `OVERDUE`

---

### 2. List Invoices

**GET** `/api/invoices`

Retrieve paginated list of invoices with optional filters.

**Query Parameters:**
- `tenant_id` (optional): Filter by tenant ID
- `lease_id` (optional): Filter by lease ID
- `status` (optional): Filter by status (`PENDING`, `PAID`, `OVERDUE`)
- `overdue_only` (optional): Show only overdue invoices (default: `false`)
- `page` (optional): Page number (default: `1`)
- `page_size` (optional): Items per page (default: `50`, max: `100`)

**Examples:**
```
GET /api/invoices
GET /api/invoices?tenant_id=1
GET /api/invoices?status=PENDING&page=1&page_size=20
GET /api/invoices?overdue_only=true
```

**Response:** `200 OK`
```json
{
  "invoices": [
    {
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
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

---

### 3. Get Invoice by ID

**GET** `/api/invoices/{invoice_id}`

Retrieve a specific invoice with full details.

**Example:**
```
GET /api/invoices/1
```

**Response:** `200 OK`
```json
{
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
```

**Error:** `404 Not Found`
```json
{
  "detail": "Invoice with ID 999 not found"
}
```

---

### 4. Update Invoice

**PUT** `/api/invoices/{invoice_id}`

Update invoice details. Only provided fields will be updated.

**Request Body:**
```json
{
  "amount": 5500.00,
  "due_date": "2026-03-15",
  "status": "PAID"
}
```

All fields are optional. Common use cases:
- Update amount: `{"amount": 5500.00}`
- Change due date: `{"due_date": "2026-03-15"}`
- Mark as paid: `{"status": "PAID"}`

**Response:** `200 OK`
```json
{
  "id": 1,
  "tenant_id": 1,
  "lease_id": 1,
  "amount": 5500.00,
  "due_date": "2026-03-15",
  "status": "PAID",
  "created_at": "2026-01-31T10:30:00",
  "tenant_name": "John Doe",
  "tenant_email": "john@example.com",
  "property_name": "Sunset Condos",
  "unit_number": "Unit 101"
}
```

---

### 5. Mark Invoice as Paid

**PATCH** `/api/invoices/{invoice_id}/mark-paid`

Convenience endpoint to mark an invoice as paid.

**Example:**
```
PATCH /api/invoices/1/mark-paid
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "status": "PAID",
  ...
}
```

---

### 6. Mark Invoice as Overdue

**PATCH** `/api/invoices/{invoice_id}/mark-overdue`

Mark an invoice as overdue.

**Example:**
```
PATCH /api/invoices/1/mark-overdue
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "status": "OVERDUE",
  ...
}
```

---

### 7. Delete Invoice

**DELETE** `/api/invoices/{invoice_id}`

Permanently delete an invoice. **Admin/Manager only.**

**Example:**
```
DELETE /api/invoices/1
```

**Response:** `204 No Content`

**Error:** `403 Forbidden`
```json
{
  "detail": "Only admins and managers can delete invoices"
}
```

---

### 8. Get Tenant Invoice Summary

**GET** `/api/invoices/tenant/{tenant_id}/summary`

Get summary statistics for a tenant's invoices.

**Example:**
```
GET /api/invoices/tenant/1/summary
```

**Response:** `200 OK`
```json
{
  "tenant_id": 1,
  "tenant_name": "John Doe",
  "total_invoices": 10,
  "total_amount": 50000.00,
  "paid": {
    "count": 5,
    "amount": 25000.00
  },
  "pending": {
    "count": 3,
    "amount": 15000.00
  },
  "overdue": {
    "count": 2,
    "amount": 10000.00
  }
}
```

---

## 🔍 Status Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `204` | No Content (successful deletion) |
| `400` | Bad Request (validation error) |
| `401` | Unauthorized (missing/invalid token) |
| `403` | Forbidden (insufficient permissions) |
| `404` | Not Found |
| `500` | Internal Server Error |

---

## 📝 Invoice Status Flow

```
PENDING → PAID     (payment received)
PENDING → OVERDUE  (past due date)
OVERDUE → PAID     (late payment received)
```

---

## 🧪 Testing with cURL

### Create Invoice
```bash
curl -X POST http://localhost:10000/api/invoices \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 1,
    "lease_id": 1,
    "amount": 5000.00,
    "due_date": "2026-02-28"
  }'
```

### List Invoices
```bash
curl -X GET "http://localhost:10000/api/invoices?tenant_id=1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Mark as Paid
```bash
curl -X PATCH http://localhost:10000/api/invoices/1/mark-paid \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Get Summary
```bash
curl -X GET http://localhost:10000/api/invoices/tenant/1/summary \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 🧪 Testing with Postman

1. **Set Authorization:**
   - Type: Bearer Token
   - Token: `<your-jwt-from-login>`

2. **Import Collection:**
   - Create a new collection "Invoice API"
   - Add requests for each endpoint above

3. **Environment Variables:**
   - `base_url`: `http://localhost:10000`
   - `token`: `<your-jwt-token>`

---

## 💡 Common Use Cases

### Monthly Rent Billing
```python
# Create monthly invoice for all active leases
from datetime import date, timedelta
from models import Lease, Invoice

active_leases = db.query(Lease).filter(
    Lease.end_date >= date.today()
).all()

for lease in active_leases:
    invoice = Invoice(
        tenant_id=lease.tenant_id,
        lease_id=lease.id,
        amount=lease.rent_price,
        due_date=date.today() + timedelta(days=30)
    )
    db.add(invoice)

db.commit()
```

### Find Overdue Invoices
```python
from datetime import date
from models import Invoice
from models.invoice import InvoiceStatus

overdue = db.query(Invoice).filter(
    Invoice.status == InvoiceStatus.PENDING,
    Invoice.due_date < date.today()
).all()

for invoice in overdue:
    invoice.mark_as_overdue()

db.commit()
```

### Tenant Payment History
```python
tenant_invoices = db.query(Invoice).filter(
    Invoice.tenant_id == tenant_id
).order_by(Invoice.due_date.desc()).all()

paid_count = sum(1 for inv in tenant_invoices if inv.status == InvoiceStatus.PAID)
payment_rate = (paid_count / len(tenant_invoices)) * 100
```

---

## 🚨 Error Handling

All errors return JSON with a `detail` field:

```json
{
  "detail": "Error message here"
}
```

**Common Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| `Missing token` | No Authorization header | Add `Authorization: Bearer <token>` |
| `Invalid token` | Expired/malformed JWT | Login again to get new token |
| `Tenant with ID X not found` | Invalid tenant_id | Verify tenant exists |
| `Lease does not belong to tenant` | Mismatched tenant/lease | Check lease ownership |
| `Only admins can delete` | Insufficient permissions | Use admin account |

---

## 📊 Database Schema

```sql
CREATE TABLE invoices (
    id INT PRIMARY KEY IDENTITY(1,1),
    tenant_id INT NOT NULL,
    lease_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    due_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at DATETIME NOT NULL DEFAULT GETDATE(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (lease_id) REFERENCES leases(id) ON DELETE CASCADE
);

CREATE INDEX ix_invoices_tenant_id ON invoices(tenant_id);
CREATE INDEX ix_invoices_lease_id ON invoices(lease_id);
CREATE INDEX ix_invoices_due_date ON invoices(due_date);
CREATE INDEX ix_invoices_status ON invoices(status);
```

---

## 🔗 Related Endpoints

- `POST /api/login` - Get JWT token
- `GET /api/tenants` - List all tenants
- `GET /api/leases` - List all leases
- `GET /api/tenantdetails/{tenant_id}` - Get tenant details

---

**Last Updated:** January 31, 2026
