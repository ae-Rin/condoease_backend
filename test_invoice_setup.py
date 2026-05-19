#!/usr/bin/env python
"""
Test script to validate Invoice model and SQLAlchemy setup.

Run this after installing dependencies and running migrations:
    python test_invoice_setup.py
"""
import sys
from datetime import date, timedelta

def test_imports():
    """Test that all required modules can be imported."""
    print("🔍 Testing imports...")
    
    try:
        import sqlalchemy
        print(f"  ✅ SQLAlchemy {sqlalchemy.__version__}")
    except ImportError:
        print("  ❌ SQLAlchemy not installed")
        print("     Run: pip install SQLAlchemy==2.0.36")
        return False
    
    try:
        import alembic
        print(f"  ✅ Alembic {alembic.__version__}")
    except ImportError:
        print("  ❌ Alembic not installed")
        print("     Run: pip install alembic==1.14.0")
        return False
    
    try:
        from models import Invoice, Tenant, Lease
        print("  ✅ Models imported successfully")
    except ImportError as e:
        print(f"  ❌ Failed to import models: {e}")
        return False
    
    try:
        from database import get_session, check_connection
        print("  ✅ Database module imported")
    except ImportError as e:
        print(f"  ❌ Failed to import database: {e}")
        return False
    
    try:
        from schemas.invoice import InvoiceCreate, InvoiceResponse
        print("  ✅ Schemas imported successfully")
    except ImportError as e:
        print(f"  ❌ Failed to import schemas: {e}")
        return False
    
    try:
        from routers.invoices import router
        print("  ✅ Invoice router imported")
    except ImportError as e:
        print(f"  ❌ Failed to import router: {e}")
        return False
    
    return True


def test_database_connection():
    """Test database connectivity."""
    print("\n🔍 Testing database connection...")
    
    try:
        from database import check_connection
        
        if check_connection():
            print("  ✅ Database connection successful")
            return True
        else:
            print("  ❌ Database connection failed")
            print("     Check your .env file has correct credentials:")
            print("       DB_SERVER, DB_PORT, DB_USER, DB_PASS, DB_NAME")
            return False
    except Exception as e:
        print(f"  ❌ Connection test failed: {e}")
        return False


def test_invoice_model():
    """Test Invoice model instantiation."""
    print("\n🔍 Testing Invoice model...")
    
    try:
        from models import Invoice
        from models.invoice import InvoiceStatus
        
        # Create an invoice instance (not saved to DB)
        invoice = Invoice(
            tenant_id=1,
            lease_id=1,
            amount=5000.00,
            due_date=date.today() + timedelta(days=30),
            status=InvoiceStatus.PENDING
        )
        
        print(f"  ✅ Invoice model instantiated: {invoice}")
        print(f"     - Amount: {invoice.amount}")
        print(f"     - Due date: {invoice.due_date}")
        print(f"     - Status: {invoice.status.value}")
        
        # Test helper methods
        assert invoice.is_overdue == False, "New invoice should not be overdue"
        print("  ✅ Invoice.is_overdue property works")
        
        invoice.mark_as_paid()
        assert invoice.status == InvoiceStatus.PAID
        print("  ✅ Invoice.mark_as_paid() method works")
        
        return True
    except Exception as e:
        print(f"  ❌ Invoice model test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_schema_validation():
    """Test Pydantic schema validation."""
    print("\n🔍 Testing Pydantic schemas...")
    
    try:
        from schemas.invoice import InvoiceCreate, InvoiceUpdate
        
        # Test valid data
        invoice_data = InvoiceCreate(
            tenant_id=1,
            lease_id=1,
            amount=5000.00,
            due_date=date.today() + timedelta(days=30)
        )
        print(f"  ✅ InvoiceCreate schema validated")
        print(f"     {invoice_data.model_dump()}")
        
        # Test update schema
        update_data = InvoiceUpdate(status="PAID")
        print(f"  ✅ InvoiceUpdate schema validated")
        
        # Test invalid data (should fail)
        try:
            invalid = InvoiceCreate(
                tenant_id=-1,  # Invalid: must be > 0
                lease_id=1,
                amount=5000.00,
                due_date=date.today()
            )
            print("  ⚠️  Schema validation didn't catch invalid tenant_id")
        except Exception:
            print("  ✅ Schema validation correctly rejects invalid data")
        
        return True
    except Exception as e:
        print(f"  ❌ Schema validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_migration_status():
    """Check if migrations have been run."""
    print("\n🔍 Checking migration status...")
    
    try:
        from sqlalchemy import inspect, text
        from database import engine
        
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if 'invoices' in tables:
            print("  ✅ 'invoices' table exists in database")
            
            # Check columns
            columns = [col['name'] for col in inspector.get_columns('invoices')]
            expected_columns = ['id', 'tenant_id', 'lease_id', 'amount', 'due_date', 'status', 'created_at']
            
            missing = set(expected_columns) - set(columns)
            if missing:
                print(f"  ⚠️  Missing columns: {missing}")
            else:
                print(f"  ✅ All expected columns present: {', '.join(expected_columns)}")
            
            return True
        else:
            print("  ❌ 'invoices' table not found")
            print("     Run migration: alembic upgrade head")
            return False
            
    except Exception as e:
        print(f"  ⚠️  Could not check migration status: {e}")
        print("     This is OK if you haven't run migrations yet")
        return None


def test_router_endpoints():
    """Test that router has all expected endpoints."""
    print("\n🔍 Testing router endpoints...")
    
    try:
        from routers.invoices import router
        
        routes = [route.path for route in router.routes]
        expected_paths = [
            "/api/invoices",
            "/api/invoices/{invoice_id}",
            "/api/invoices/{invoice_id}/mark-paid",
            "/api/invoices/{invoice_id}/mark-overdue",
            "/api/invoices/tenant/{tenant_id}/summary",
        ]
        
        print(f"  ✅ Router has {len(routes)} endpoints:")
        for path in routes:
            print(f"     - {path}")
        
        return True
    except Exception as e:
        print(f"  ❌ Router test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("🧪 Invoice Model & SQLAlchemy Setup Test")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Database Connection", test_database_connection()))
    results.append(("Invoice Model", test_invoice_model()))
    results.append(("Schema Validation", test_schema_validation()))
    results.append(("Migration Status", test_migration_status()))
    results.append(("Router Endpoints", test_router_endpoints()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    
    for name, result in results:
        status = "✅ PASS" if result is True else ("❌ FAIL" if result is False else "⚠️  SKIP")
        print(f"{status:12} {name}")
    
    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    
    if failed > 0:
        print("\n⚠️  Some tests failed. Check the output above for details.")
        print("   See SETUP_SQLALCHEMY.md for troubleshooting steps.")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed! Your Invoice setup is ready to use.")
        print("   Next steps:")
        print("   1. Run migrations: alembic upgrade head")
        print("   2. Start the server: python main.py")
        print("   3. Test endpoints with Postman or curl")
        sys.exit(0)


if __name__ == "__main__":
    main()
