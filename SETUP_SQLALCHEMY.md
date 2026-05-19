# SQLAlchemy & Invoice Model Setup Guide

This guide walks you through setting up SQLAlchemy, running migrations, and using the new Invoice model.

---

## 📋 Prerequisites

- Python 3.8+ installed
- Access to Azure SQL database
- `.env` file configured with database credentials

---

## 🚀 Installation Steps

### 1. Install Dependencies

```bash
# Navigate to the backend directory
cd C:\Users\Administrator\Desktop\condoease_backend

# Install SQLAlchemy and Alembic
pip install SQLAlchemy==2.0.36 alembic==1.14.0

# Or install all requirements
pip install -r requirements.txt
```

### 2. Verify Database Connection

Test that SQLAlchemy can connect to your database:

```bash
python -c "from database import check_connection; print('Connected!' if check_connection() else 'Failed')"
```

### 3. Run Database Migration

Create the `invoices` table in your database:

```bash
# Run the migration
alembic upgrade head

# You should see output like:
# INFO  [alembic.runtime.migration] Running upgrade  -> 20260131_000001, Create invoices table
```

### 4. Verify Migration

Check that the table was created:

```sql
-- Run in Azure SQL Studio or your SQL client
SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'invoices';
```

---

## 📁 What Was Created

### New Directory Structure

```
condoease_backend/
├── models/                    # SQLAlchemy ORM models
│   ├── __init__.py
│   ├── base.py               # Base model class
│   ├── user.py               # User model
│   ├── tenant.py             # Tenant model
│   ├── lease.py              # Lease model
│   ├── invoice.py            # ✨ NEW: Invoice model
│   ├── property.py           # Property model
│   └── property_unit.py      # PropertyUnit model
│
├── schemas/                   # Pydantic validation schemas
│   ├── __init__.py
│   └── invoice.py            # Invoice request/response schemas
│
├── routers/                   # API route handlers
│   ├── __init__.py
│   └── invoices.py           # ✨ NEW: Invoice CRUD endpoints
│
├── alembic/                   # Database migrations
│   ├── versions/
│   │   └── 20260131_000001_create_invoices_table.py
│   ├── env.py
│   └── script.py.mako
│
├── database.py               # SQLAlchemy session management
├── alembic.ini               # Alembic configuration
└── requirements.txt          # Updated with SQLAlchemy + Alembic
```

---

## 🗄️ Invoice Model Schema

### Database Table: `invoices`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT (PK) | Auto-incrementing primary key |
| `tenant_id` | INT (FK) | Foreign key to `tenants.tenant_id` |
| `lease_id` | INT (FK) | Foreign key to `leases.id` |
| `amount` | DECIMAL(12,2) | Invoice amount |
| `due_date` | DATE | Payment due date |
| `status` | ENUM | `PENDING`, `PAID`, or `OVERDUE` |
| `created_at` | DATETIME | Timestamp of creation |

### Relationships

- **Tenant**: `Invoice.tenant` → `Tenant` (many-to-one)
- **Lease**: `Invoice.lease` → `Lease` (many-to-one)

---

## 🔌 API Endpoints

All endpoints require JWT authentication (`Authorization: Bearer <token>`).

### Create Invoice
```http
POST /api/invoices
Content-Type: application/json

{
  "tenant_id": 1,
  "lease_id": 1,
  "amount": 5000.00,
  "due_date": "2026-02-28",
  "status": "PENDING"
}
```

### List Invoices (with filters)
```http
GET /api/invoices?tenant_id=1&status=PENDING&page=1&page_size=50
```

### Get Invoice by ID
```http
GET /api/invoices/1
```

### Update Invoice
```http
PUT /api/invoices/1
Content-Type: application/json

{
  "status": "PAID"
}
```

### Mark Invoice as Paid
```http
PATCH /api/invoices/1/mark-paid
```

### Mark Invoice as Overdue
```http
PATCH /api/invoices/1/mark-overdue
```

### Delete Invoice (Admin/Manager only)
```http
DELETE /api/invoices/1
```

### Get Tenant Invoice Summary
```http
GET /api/invoices/tenant/1/summary
```

**Response:**
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

## 💻 Usage Examples

### Using SQLAlchemy in Routes

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from database import get_session
from models import Invoice, Tenant

@app.get("/my-invoices")
def get_my_invoices(db: Session = Depends(get_session), token: dict = Depends(verify_token)):
    tenant_id = token.get("id")
    invoices = db.query(Invoice).filter(Invoice.tenant_id == tenant_id).all()
    return {"invoices": invoices}
```

### Creating an Invoice Programmatically

```python
from datetime import date, timedelta
from models import Invoice
from models.invoice import InvoiceStatus

# Create invoice
invoice = Invoice(
    tenant_id=1,
    lease_id=1,
    amount=5000.00,
    due_date=date.today() + timedelta(days=30),
    status=InvoiceStatus.PENDING
)

db.add(invoice)
db.commit()
db.refresh(invoice)

print(f"Created invoice #{invoice.id}")
```

### Querying with Relationships

```python
from models import Invoice, Tenant, Lease

# Get invoice with tenant info
invoice = db.query(Invoice).filter(Invoice.id == 1).first()
tenant = invoice.tenant  # Access related tenant via relationship
lease = invoice.lease    # Access related lease

print(f"Invoice for {tenant.first_name} {tenant.last_name}")
```

---

## 🔄 Future Migrations

### Generate a New Migration

When you modify models, generate a migration automatically:

```bash
alembic revision --autogenerate -m "Add payment_method to invoices"
```

### Apply Migrations

```bash
alembic upgrade head
```

### Rollback Migration

```bash
alembic downgrade -1
```

### View Migration History

```bash
alembic history
```

---

## 🧪 Testing the Setup

### Test Database Connection

```python
from database import check_connection

if check_connection():
    print("✅ Database connected successfully")
else:
    print("❌ Database connection failed")
```

### Test Invoice Creation

```python
from database import get_session_context
from models import Invoice
from datetime import date

with get_session_context() as db:
    invoice = Invoice(
        tenant_id=1,
        lease_id=1,
        amount=5000.00,
        due_date=date(2026, 2, 28)
    )
    db.add(invoice)
    print(f"✅ Created invoice #{invoice.id}")
```

### Test API Endpoints

```bash
# Using curl (replace <TOKEN> with your JWT)
curl -X POST http://localhost:10000/api/invoices \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 1,
    "lease_id": 1,
    "amount": 5000.00,
    "due_date": "2026-02-28"
  }'
```

---

## ⚠️ Important Notes

### Coexistence with Raw SQL

The new SQLAlchemy models **coexist** with the existing raw SQL code in `main.py`. You can:

1. **Keep using raw SQL** for existing endpoints (no changes needed)
2. **Use SQLAlchemy** for new features (like invoices)
3. **Gradually migrate** old endpoints to SQLAlchemy

### No Breaking Changes

- Existing routes in `main.py` are **not affected**
- Database schema remains compatible
- Both approaches can access the same tables

### Performance Considerations

- SQLAlchemy adds a small overhead but provides safety and convenience
- Use `joinedload()` for eager loading to avoid N+1 queries
- The connection pool is configured for optimal performance

---

## 🐛 Troubleshooting

### "No module named 'sqlalchemy'"

```bash
pip install SQLAlchemy==2.0.36
```

### "alembic: command not found"

```bash
pip install alembic==1.14.0
```

### Migration fails with "table already exists"

If you manually created the table, mark the migration as complete:

```bash
alembic stamp head
```

### Connection timeout

Check your `.env` file has correct database credentials:

```env
DB_SERVER=your-server.database.windows.net
DB_PORT=1433
DB_USER=your-username
DB_PASS=your-password
DB_NAME=your-database
```

---

## 📚 Additional Resources

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [FastAPI with SQLAlchemy](https://fastapi.tiangolo.com/tutorial/sql-databases/)

---

## ✅ Next Steps

1. ✅ Install dependencies: `pip install -r requirements.txt`
2. ✅ Run migration: `alembic upgrade head`
3. ✅ Register invoice router in `main.py` (see below)
4. ✅ Test endpoints with Postman or curl
5. 🚀 Build frontend UI for invoice management

---

## 🔗 Registering the Invoice Router

Add this to your `main.py` (near the end, before `if __name__ == "__main__"`):

```python
# Import the invoice router
from routers import invoices_router

# Register the router
app.include_router(invoices_router)
```

That's it! Your invoice API is now ready to use. 🎉
