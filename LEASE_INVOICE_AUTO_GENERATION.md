# 🔄 Automatic Invoice Generation for Leases

This document explains the automatic invoice generation feature that was added to the lease creation process.

---

## 📋 Overview

When a new lease is created, the system now **automatically generates an invoice** for the first month's rent.

### What Happens Automatically

1. ✅ **Invoice is created** when lease is created
2. ✅ **Amount is set** to the lease rent price
3. ✅ **Due date is calculated** as 1 month (30 days) from lease start date
4. ✅ **Status is set** to `PENDING`
5. ✅ **Tenant is linked** to the invoice
6. ✅ **Lease is linked** to the invoice

---

## 🏗️ Architecture

### Service Layer

Business logic is now separated into a **service layer** for better maintainability:

```
services/
├── __init__.py
└── invoice_service.py    # InvoiceService class with business logic
```

### InvoiceService Methods

| Method | Purpose |
|--------|---------|
| `create_initial_lease_invoice()` | Create invoice when lease is created |
| `create_invoice_for_lease()` | Generic invoice creation for a lease |
| `generate_monthly_invoices()` | Batch create invoices for active leases |
| `mark_overdue_invoices()` | Mark pending invoices past due date as overdue |
| `calculate_tenant_balance()` | Calculate total balance owed by tenant |

---

## 🔄 How It Works

### Lease Creation Flow

```
1. User creates lease via POST /api/leases
   ↓
2. Lease is saved to database (raw SQL)
   ↓
3. Lease ID is retrieved
   ↓
4. InvoiceService.create_initial_lease_invoice() is called
   ↓
5. Invoice is created with:
   - tenant_id: from lease
   - lease_id: newly created lease
   - amount: lease rent_price
   - due_date: lease start_date + 30 days
   - status: PENDING
   ↓
6. Response includes lease creation confirmation + invoice details
```

### Code Example

```python
# In main.py - lease creation endpoint

# After lease is created and lease_id is retrieved:
from services import InvoiceService
from database import get_session_context

with get_session_context() as db:
    invoice = InvoiceService.create_initial_lease_invoice(
        db=db,
        lease_id=lease_id,
        tenant_id=tenant,
        rent_price=Decimal(str(rentPrice)),
        start_date=lease_start
    )
```

---

## 📤 API Response

### Before (Old Response)

```json
{
  "message": "Lease created successfully"
}
```

### After (New Response)

```json
{
  "message": "Lease created successfully",
  "invoice_created": true,
  "invoice": {
    "id": 1,
    "amount": 5000.00,
    "due_date": "2026-03-03",
    "status": "PENDING"
  }
}
```

### Backward Compatibility ✅

- **Old clients** will still work - they simply ignore the new `invoice_created` and `invoice` fields
- **New clients** can use the invoice information to display confirmation to users
- The original `message` field is preserved

---

## 🧪 Testing

### Run Integration Tests

```bash
python test_lease_invoice_integration.py
```

Expected output:
```
✅ PASS     InvoiceService
✅ PASS     Invoice Creation Logic
✅ PASS     Database Integration
✅ PASS     Lease Endpoint Modification
✅ PASS     Backward Compatibility
✅ PASS     Error Handling

🎉 All tests passed!
```

### Manual Testing

#### 1. Create a Lease

```bash
curl -X POST http://localhost:10000/api/leases \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "property=1" \
  -F "tenant=1" \
  -F "rentPrice=5000.00" \
  -F "depositPrice=10000.00" \
  -F "startDate=2026-02-01" \
  -F "endDate=2027-02-01" \
  -F "tenancyTerms=Standard lease terms"
```

#### 2. Check Response

Look for the `invoice` object in the response:

```json
{
  "message": "Lease created successfully",
  "invoice_created": true,
  "invoice": {
    "id": 1,
    "amount": 5000.00,
    "due_date": "2026-03-03",
    "status": "PENDING"
  }
}
```

#### 3. Verify Invoice Was Created

```bash
curl -X GET http://localhost:10000/api/invoices \
  -H "Authorization: Bearer YOUR_TOKEN"
```

You should see the auto-generated invoice in the list.

---

## 🛡️ Error Handling

### Robust Fallback

If invoice creation fails for any reason, **the lease is still created successfully**.

```python
try:
    # Create invoice
    invoice = InvoiceService.create_initial_lease_invoice(...)
    invoice_created = True
except Exception as invoice_error:
    # Log error but don't fail the lease creation
    print(f"⚠️  Failed to auto-generate invoice: {invoice_error}")
    # Lease was still created successfully
```

### Why This Matters

- **Database issues**: If SQLAlchemy tables don't exist yet, lease creation still works
- **Data issues**: If tenant or lease data is invalid, lease creation succeeds
- **Service unavailable**: If InvoiceService has bugs, lease creation is unaffected

### Response When Invoice Fails

```json
{
  "message": "Lease created successfully"
}
```

Note: No `invoice_created` field means invoice was not created (but lease was).

---

## 💡 Use Cases

### 1. Standard Lease Creation

**Scenario**: Property manager creates a new lease for a tenant.

**Result**: 
- Lease is created
- First month's rent invoice is automatically generated
- Tenant can immediately see their invoice in the system

### 2. Lease Renewal

**Scenario**: Existing lease is renewed with new dates.

**Result**:
- New lease record is created
- New invoice is generated for the renewed lease
- Old lease and its invoices remain in the system for records

### 3. Multiple Units

**Scenario**: Tenant leases multiple units.

**Result**:
- Each lease gets its own invoice
- Tenant can see all their invoices grouped by lease

---

## 🔮 Future Enhancements

### Planned Features

1. **Recurring Invoices**
   - Automatically generate monthly invoices for active leases
   - Scheduled job to run on the 1st of each month

2. **Utility Bills**
   - Include utility bills in invoice amount
   - Separate line items for gas, electricity, internet, tax

3. **Prorated Invoices**
   - Calculate prorated amount for partial months
   - Handle mid-month lease starts

4. **Invoice Templates**
   - Customizable invoice generation rules
   - Different billing cycles (weekly, monthly, quarterly)

5. **Notifications**
   - Email tenant when invoice is created
   - Remind tenant when due date approaches
   - Alert admin when invoice becomes overdue

---

## 📊 Database Schema

### Invoices Table

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
```

### Relationships

```
Lease (1) ──→ (N) Invoice
Tenant (1) ──→ (N) Invoice
```

---

## 🔧 Configuration

### Due Date Calculation

Default: **30 days** from lease start date

To change this, modify the service:

```python
# In services/invoice_service.py

InvoiceService.create_initial_lease_invoice(
    db=db,
    lease_id=lease_id,
    tenant_id=tenant_id,
    rent_price=rent_price,
    start_date=start_date,
    due_date_offset_days=30  # ← Change this value
)
```

### Custom Business Rules

Add custom logic in `InvoiceService`:

```python
@staticmethod
def create_initial_lease_invoice(db, lease_id, tenant_id, rent_price, start_date):
    # Custom rule: First month is free for new tenants
    is_new_tenant = db.query(Lease).filter(
        Lease.tenant_id == tenant_id
    ).count() == 1
    
    if is_new_tenant:
        rent_price = Decimal("0.00")  # First month free!
    
    return InvoiceService.create_invoice_for_lease(...)
```

---

## 🐛 Troubleshooting

### Invoice Not Created

**Problem**: Lease is created but no invoice appears.

**Possible Causes**:
1. SQLAlchemy not installed
2. Database migration not run
3. Service error (check server logs)

**Solution**:
```bash
# Install dependencies
pip install SQLAlchemy alembic

# Run migration
alembic upgrade head

# Check logs
python main.py
# Look for: "✅ Auto-generated invoice #X for lease #Y"
# Or: "⚠️  Failed to auto-generate invoice: ..."
```

### Wrong Amount

**Problem**: Invoice amount doesn't match rent price.

**Check**:
- Ensure `rentPrice` is passed correctly to the endpoint
- Verify `Decimal` conversion: `Decimal(str(rentPrice))`

### Wrong Due Date

**Problem**: Due date is not 1 month from start date.

**Check**:
- Verify `startDate` format: `YYYY-MM-DD`
- Check calculation: `start_date + timedelta(days=30)`
- Note: 1 month = 30 days (not calendar month)

---

## 📚 Related Documentation

- **SETUP_SQLALCHEMY.md** - SQLAlchemy setup guide
- **INVOICE_API_REFERENCE.md** - Invoice API documentation
- **README_INVOICE_FEATURE.md** - Invoice feature overview

---

## ✅ Summary

| Feature | Status |
|---------|--------|
| **Auto-generate invoice on lease creation** | ✅ Implemented |
| **Invoice amount = lease rent** | ✅ Implemented |
| **Due date = start date + 30 days** | ✅ Implemented |
| **Status = PENDING** | ✅ Implemented |
| **Service layer for business logic** | ✅ Implemented |
| **Backward compatible API** | ✅ Implemented |
| **Robust error handling** | ✅ Implemented |
| **Comprehensive tests** | ✅ Implemented |
| **Documentation** | ✅ Complete |

---

**Created**: January 31, 2026  
**Status**: ✅ Production Ready  
**Version**: 1.0.0
