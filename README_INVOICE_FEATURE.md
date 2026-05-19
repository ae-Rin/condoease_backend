# 🧾 Invoice Feature - Complete Implementation

This document provides an overview of the new Invoice feature added to the CondoEase backend.

---

## ✨ What Was Added

### New SQLAlchemy Infrastructure

The project now has **SQLAlchemy ORM** alongside the existing raw SQL code:

- ✅ **Models** - Type-safe database models with relationships
- ✅ **Migrations** - Alembic for version-controlled schema changes
- ✅ **Schemas** - Pydantic validation for API requests/responses
- ✅ **Routers** - Modular API endpoint organization
- ✅ **No Breaking Changes** - Existing code continues to work

### Invoice Model Features

The `Invoice` model includes:

- **Core Fields**: `id`, `tenant_id`, `lease_id`, `amount`, `due_date`, `status`, `created_at`
- **Status Enum**: `PENDING`, `PAID`, `OVERDUE`
- **Relationships**: Links to `Tenant` and `Lease` models
- **Helper Methods**: `is_overdue`, `mark_as_paid()`, `mark_as_overdue()`
- **Cascade Deletes**: Invoices are deleted when tenant/lease is deleted

### API Endpoints (8 total)

1. **POST** `/api/invoices` - Create invoice
2. **GET** `/api/invoices` - List with filters (tenant, lease, status, overdue)
3. **GET** `/api/invoices/{id}` - Get single invoice
4. **PUT** `/api/invoices/{id}` - Update invoice
5. **PATCH** `/api/invoices/{id}/mark-paid` - Mark as paid
6. **PATCH** `/api/invoices/{id}/mark-overdue` - Mark as overdue
7. **DELETE** `/api/invoices/{id}` - Delete invoice (admin only)
8. **GET** `/api/invoices/tenant/{id}/summary` - Get tenant summary stats

---

## 📁 Files Created

```
condoease_backend/
├── models/                              # SQLAlchemy ORM models
│   ├── __init__.py
│   ├── base.py                          # Base model class
│   ├── user.py                          # User model
│   ├── tenant.py                        # Tenant model
│   ├── lease.py                         # Lease model
│   ├── invoice.py                       # ✨ Invoice model
│   ├── property.py                      # Property model
│   └── property_unit.py                 # PropertyUnit model
│
├── schemas/                             # Pydantic validation
│   ├── __init__.py
│   └── invoice.py                       # Invoice schemas
│
├── routers/                             # API routes
│   ├── __init__.py
│   └── invoices.py                      # ✨ Invoice endpoints
│
├── alembic/                             # Database migrations
│   ├── versions/
│   │   └── 20260131_000001_create_invoices_table.py
│   ├── env.py
│   └── script.py.mako
│
├── database.py                          # SQLAlchemy session management
├── alembic.ini                          # Alembic configuration
├── test_invoice_setup.py                # Test script
│
├── SETUP_SQLALCHEMY.md                  # 📖 Setup guide
├── INVOICE_API_REFERENCE.md             # 📖 API documentation
└── README_INVOICE_FEATURE.md            # 📖 This file
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd C:\Users\Administrator\Desktop\condoease_backend
pip install -r requirements.txt
```

This installs:
- `SQLAlchemy==2.0.36`
- `alembic==1.14.0`

### 2. Run Migration

```bash
alembic upgrade head
```

This creates the `invoices` table in your database.

### 3. Test Setup

```bash
python test_invoice_setup.py
```

Expected output:
```
✅ SQLAlchemy 2.0.36
✅ Alembic 1.14.0
✅ Models imported successfully
✅ Database connection successful
✅ Invoice model instantiated
✅ 'invoices' table exists in database
🎉 All tests passed!
```

### 4. Start Server

```bash
python main.py
```

The invoice router is automatically registered at startup.

### 5. Test API

```bash
# Get your JWT token first
curl -X POST http://localhost:10000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "your-password"}'

# Create an invoice
curl -X POST http://localhost:10000/api/invoices \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 1,
    "lease_id": 1,
    "amount": 5000.00,
    "due_date": "2026-02-28"
  }'

# List invoices
curl -X GET http://localhost:10000/api/invoices \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| **SETUP_SQLALCHEMY.md** | Complete setup guide with troubleshooting |
| **INVOICE_API_REFERENCE.md** | Full API documentation with examples |
| **README_INVOICE_FEATURE.md** | This overview document |

---

## 🔄 Architecture

### Coexistence with Raw SQL

The new SQLAlchemy code **does not replace** existing raw SQL:

```python
# Existing code (raw SQL) - still works
@app.get("/api/tenants")
def get_all_tenants(token: dict = Depends(verify_token)):
    db = get_db()  # pymssql connection
    cursor = db.cursor(as_dict=True)
    cursor.execute("SELECT * FROM tenants")
    return cursor.fetchall()

# New code (SQLAlchemy) - works alongside
@app.get("/api/invoices")
def list_invoices(db: Session = Depends(get_session)):  # SQLAlchemy session
    return db.query(Invoice).all()
```

Both approaches access the **same database tables**.

### Benefits of SQLAlchemy

| Feature | Raw SQL | SQLAlchemy |
|---------|---------|------------|
| Type Safety | ❌ | ✅ |
| Relationships | Manual joins | Automatic |
| Migrations | Manual scripts | Alembic autogenerate |
| Validation | Manual | Pydantic schemas |
| IDE Support | Limited | Full autocomplete |
| SQL Injection | Manual escaping | Automatic |

---

## 🎯 Use Cases

### 1. Monthly Rent Billing

```python
from datetime import date, timedelta
from models import Lease, Invoice

# Get all active leases
active_leases = db.query(Lease).filter(
    Lease.end_date >= date.today()
).all()

# Create invoices
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

### 2. Overdue Invoice Checker

```python
from datetime import date
from models import Invoice
from models.invoice import InvoiceStatus

# Find overdue invoices
overdue = db.query(Invoice).filter(
    Invoice.status == InvoiceStatus.PENDING,
    Invoice.due_date < date.today()
).all()

# Mark as overdue
for invoice in overdue:
    invoice.mark_as_overdue()

db.commit()
```

### 3. Tenant Payment Report

```python
# Get tenant's payment statistics
summary = requests.get(
    f"http://localhost:10000/api/invoices/tenant/{tenant_id}/summary",
    headers={"Authorization": f"Bearer {token}"}
).json()

print(f"Total Owed: ${summary['pending']['amount']}")
print(f"Overdue: ${summary['overdue']['amount']}")
print(f"Payment Rate: {summary['paid']['count'] / summary['total_invoices'] * 100}%")
```

---

## 🔐 Security

### Authentication

All endpoints require JWT authentication:

```python
@router.post("/api/invoices")
def create_invoice(
    invoice_data: InvoiceCreate,
    db: Session = Depends(get_session),
    token: dict = Depends(verify_token)  # ← JWT validation
):
    # token contains: {"id": user_id, "role": user_role}
    ...
```

### Authorization

Delete endpoint is restricted to admins/managers:

```python
role = token.get("role")
if role not in ["admin", "manager"]:
    raise HTTPException(403, "Only admins and managers can delete invoices")
```

### Data Validation

Pydantic schemas validate all inputs:

```python
class InvoiceCreate(BaseModel):
    tenant_id: int = Field(..., gt=0)  # Must be positive
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    due_date: date  # Must be valid date
```

### SQL Injection Protection

SQLAlchemy automatically parameterizes queries:

```python
# Safe - SQLAlchemy handles escaping
db.query(Invoice).filter(Invoice.tenant_id == tenant_id).all()

# vs raw SQL (vulnerable if not careful)
cursor.execute(f"SELECT * FROM invoices WHERE tenant_id = {tenant_id}")  # ❌ Don't do this
```

---

## 🧪 Testing

### Unit Tests

```python
# test_invoice_setup.py
python test_invoice_setup.py
```

### Manual Testing

```bash
# Postman collection or cURL commands
# See INVOICE_API_REFERENCE.md for examples
```

### Integration Testing

```python
# Create test data
tenant = Tenant(first_name="Test", last_name="User", email="test@example.com")
lease = Lease(tenant_id=tenant.tenant_id, rent_price=5000)
invoice = Invoice(tenant_id=tenant.tenant_id, lease_id=lease.id, amount=5000)

db.add_all([tenant, lease, invoice])
db.commit()

# Test relationships
assert invoice.tenant.first_name == "Test"
assert invoice.lease.rent_price == 5000
```

---

## 🔮 Future Enhancements

Potential additions to the invoice system:

1. **Payment Processing**
   - Integrate payment gateways (Stripe, PayPal, GCash)
   - Record payment transactions
   - Generate receipts

2. **Automated Billing**
   - Scheduled monthly invoice generation
   - Automatic overdue detection
   - Email notifications

3. **Late Fees**
   - Configurable late fee rules
   - Automatic fee calculation
   - Grace period settings

4. **Payment Plans**
   - Installment support
   - Partial payments
   - Payment history tracking

5. **Reporting**
   - Revenue reports
   - Collection rate analytics
   - Tenant payment trends

6. **Multi-Currency**
   - Support for different currencies
   - Exchange rate handling

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

### "Table 'invoices' already exists"

If you manually created the table:

```bash
alembic stamp head
```

### "Cannot import name 'invoices_router'"

Make sure SQLAlchemy is installed. The import is wrapped in a try/except in `main.py`.

### Database connection fails

Check `.env` file:

```env
DB_SERVER=your-server.database.windows.net
DB_PORT=1433
DB_USER=your-username
DB_PASS=your-password
DB_NAME=your-database
```

---

## 📞 Support

For issues or questions:

1. Check **SETUP_SQLALCHEMY.md** for detailed setup instructions
2. Check **INVOICE_API_REFERENCE.md** for API usage
3. Run `python test_invoice_setup.py` to diagnose issues
4. Check server logs for error messages

---

## ✅ Checklist

Before deploying to production:

- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Run migrations: `alembic upgrade head`
- [ ] Test setup: `python test_invoice_setup.py`
- [ ] Test endpoints with Postman/curl
- [ ] Update `.env` with production database credentials
- [ ] Set up automated backups
- [ ] Configure monitoring/logging
- [ ] Document any custom business logic
- [ ] Train users on new invoice features

---

## 📊 Summary

| Metric | Value |
|--------|-------|
| **New Models** | 6 (User, Tenant, Lease, Property, PropertyUnit, Invoice) |
| **New Endpoints** | 8 invoice-related endpoints |
| **New Files** | 20+ files (models, schemas, routers, migrations, docs) |
| **Lines of Code** | ~2000+ lines |
| **Documentation** | 3 comprehensive guides |
| **Breaking Changes** | 0 (fully backward compatible) |

---

**Created:** January 31, 2026  
**Status:** ✅ Ready for Production  
**Version:** 1.0.0
