# 🔧 Environment Configuration & Webhook Setup Guide

## Part 1: Environment Variables Configuration

### Step 1: Create .env File

Navigate to the backend directory and create a `.env` file from the template:

```powershell
# Navigate to backend folder
cd c:\Users\Administrator\Desktop\RR\condoease_backend

# Copy the template
Copy-Item .env.example .env

# Or manually create and add the content below
```

### Step 2: Get Maya Sandbox Credentials

**Important:** You need actual credentials from Maya to proceed.

#### Option A: Maya Sandbox Account (Recommended for Testing)

1. **Visit Maya Dashboard:**
   - Go to: https://dashboard.paycom.ph/
   - Sign up or log in with your account

2. **Navigate to API Keys:**
   - Click: Settings > API Keys
   - You'll see:
     - **Sandbox API Key**
     - **Sandbox Secret Key**
     - **Webhook Secret** (for signing)

3. **Note Your Keys:**
   - Save all three keys in a secure location
   - You'll need these in the next step

**Note:** If you don't have a Maya account, sign up at https://paycom.ph/

### Step 3: Fill in .env File

Edit the `.env` file in `condoease_backend/` directory:

```bash
# ========================================
# MAYA PAYMENT SANDBOX CONFIGURATION
# ========================================

# Your Maya Sandbox API Key (from Maya Dashboard)
MAYA_API_KEY=pk_test_YOUR_ACTUAL_API_KEY_HERE

# Your Maya Sandbox Secret Key (from Maya Dashboard)
MAYA_SECRET_KEY=sk_test_YOUR_ACTUAL_SECRET_KEY_HERE

# Your Maya Webhook Secret (from Maya Dashboard)
MAYA_WEBHOOK_SECRET=whsec_YOUR_ACTUAL_WEBHOOK_SECRET_HERE

# Maya Sandbox URL (don't change this)
MAYA_SANDBOX_URL=https://payments-sandbox.paycom.ph

# ========================================
# WEBHOOK CONFIGURATION
# ========================================

# Your backend webhook URL (replace with your actual URL)
# Format: https://your-domain.com/api/webhooks/payments/maya
WEBHOOK_URL=https://your-backend-url.com/api/webhooks/payments/maya

# For local development (with ngrok or similar):
# WEBHOOK_URL=https://xyz.ngrok.io/api/webhooks/payments/maya

# For production:
# WEBHOOK_URL=https://api.yourdomain.com/api/webhooks/payments/maya

# ========================================
# FRONTEND RETURN URLs
# ========================================

# After payment completes, user is redirected to these URLs

# Web app return URL
FRONTEND_RETURN_URL=https://your-frontend-url.com/payment/return

# Mobile app deep link (for Expo/React Native)
MOBILE_APP_RETURN_URL=condoease://payment/return

# For local development web:
# FRONTEND_RETURN_URL=http://localhost:3000/payment/return

# For local development mobile:
# MOBILE_APP_RETURN_URL=exp://localhost:8081/payment/return

# ========================================
# EXISTING CONFIGURATION (Keep as-is)
# ========================================

# JWT Secret for API authentication
JWT_SECRET=your_jwt_secret_key

# Database Configuration
DB_SERVER=your_db_server
DB_PORT=1433
DB_USER=your_db_user
DB_PASS=your_db_password
DB_NAME=your_db_name

# Azure Blob Storage (if using)
AZURE_STORAGE_ACCOUNT=your_storage_account
AZURE_STORAGE_KEY=your_storage_key
AZURE_CONTAINER_NAME=your_container

# Email Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password

# API URLs
API_BASE_URL=https://your-api-url.com
```

### Step 4: Verify .env File

Check that your `.env` file is in the right location:

```powershell
# Should show the .env file
Get-Item c:\Users\Administrator\Desktop\RR\condoease_backend\.env
```

### Step 5: Verify Backend Can Load Environment

```powershell
# Test if .env loads correctly
cd c:\Users\Administrator\Desktop\RR\condoease_backend
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('MAYA_API_KEY:', 'SET' if os.getenv('MAYA_API_KEY') else 'NOT SET')"
```

Expected output: `MAYA_API_KEY: SET`

---

## Part 2: Register Webhook in Maya Dashboard

### Step 1: Access Maya Dashboard

1. **Go to:** https://dashboard.paycom.ph/
2. **Login** with your account credentials
3. **Navigate to:** Settings > Webhooks (or similar section)

### Step 2: Add New Webhook Endpoint

**Location:** Webhooks section in Maya Dashboard

**Fill in these fields:**

```
Webhook URL: https://your-backend-url.com/api/webhooks/payments/maya
```

**For Local Testing with ngrok:**

If testing locally, you can use ngrok:

```powershell
# Install ngrok (if not already installed)
choco install ngrok

# Or download from https://ngrok.com/download

# Start ngrok
ngrok http 8000

# You'll get: https://xyz.ngrok.io

# Use this URL as your webhook URL:
# https://xyz.ngrok.io/api/webhooks/payments/maya
```

**Select Events:**
- ✅ Payment Success
- ✅ Payment Failed  
- ✅ Payment Expired

### Step 3: Configure Webhook Secret

In Maya Dashboard Webhooks section:

1. **Copy the Webhook Secret** provided by Maya
2. **Paste it into your .env file** as `MAYA_WEBHOOK_SECRET`
3. **Save** both files

### Step 4: Test Webhook Connection

Maya Dashboard usually provides a "Send Test Event" option:

1. **Click:** "Send Test Event" or "Test Webhook"
2. **Select Event Type:** Payment Success (or any event)
3. **Click:** Send
4. **Check your backend logs** for webhook receipt

Expected log entry:
```
[INFO] Webhook received: event_type=PAYMENT_SUCCESS checkout_id=chk_...
[INFO] Webhook processed successfully
```

### Step 5: Enable Webhook Events (if needed)

In Maya Dashboard settings:

1. **Navigate to:** Settings > API Events
2. **Enable:**
   - ✅ Webhooks
   - ✅ Payment notifications
   - ✅ Event retries

3. **Configure retry policy:**
   - Recommended: 3 retries with exponential backoff

---

## Part 3: Validate Your Setup

### Checklist

```
✓ Step 1: Environment Variables
  ├─ [ ] .env file created in condoease_backend/
  ├─ [ ] MAYA_API_KEY filled in
  ├─ [ ] MAYA_SECRET_KEY filled in
  ├─ [ ] MAYA_WEBHOOK_SECRET filled in
  └─ [ ] WEBHOOK_URL configured

✓ Step 2: Webhook Registration
  ├─ [ ] Maya Dashboard accessed
  ├─ [ ] Webhook endpoint registered
  ├─ [ ] Webhook secret copied
  ├─ [ ] Events enabled (Success, Failed, Expired)
  └─ [ ] Test event sent successfully

✓ Step 3: Backend Verification
  ├─ [ ] Backend can load .env
  ├─ [ ] MayaService can import
  ├─ [ ] Webhook routes registered
  └─ [ ] Backend starts without errors
```

### Validation Commands

**1. Check .env exists:**
```powershell
Test-Path "c:\Users\Administrator\Desktop\RR\condoease_backend\.env"
# Should return: True
```

**2. Verify environment variables loaded:**
```powershell
cd c:\Users\Administrator\Desktop\RR\condoease_backend
python -c "
from dotenv import load_dotenv
import os
load_dotenv()
vars = ['MAYA_API_KEY', 'MAYA_SECRET_KEY', 'MAYA_WEBHOOK_SECRET', 'WEBHOOK_URL']
for var in vars:
    value = os.getenv(var)
    status = '✓' if value else '✗'
    print(f'{status} {var}: {\"SET\" if value else \"NOT SET\"}')"
```

**3. Test Maya API Connection:**
```powershell
cd c:\Users\Administrator\Desktop\RR\condoease_backend
python -c "
from services.maya_service import MayaService
import os
from dotenv import load_dotenv

load_dotenv()

try:
    # Test API key format
    api_key = os.getenv('MAYA_API_KEY')
    if not api_key or not api_key.startswith('pk_test_'):
        print('✗ Invalid API key format')
    else:
        print('✓ API key format valid')
    
    # Test secret key format
    secret_key = os.getenv('MAYA_SECRET_KEY')
    if not secret_key or not secret_key.startswith('sk_test_'):
        print('✗ Invalid secret key format')
    else:
        print('✓ Secret key format valid')
    
    # Test webhook secret format
    webhook_secret = os.getenv('MAYA_WEBHOOK_SECRET')
    if not webhook_secret or not webhook_secret.startswith('whsec_'):
        print('✗ Invalid webhook secret format')
    else:
        print('✓ Webhook secret format valid')
        
except Exception as e:
    print(f'✗ Error: {e}')"
```

**4. Start backend server:**
```powershell
cd c:\Users\Administrator\Desktop\RR\condoease_backend
python main.py

# Should show (no errors about missing env vars):
# INFO:     Uvicorn running on http://127.0.0.1:8000
```

**5. Check webhook endpoint is registered:**
```powershell
# In a new PowerShell terminal, test the health endpoint
Invoke-WebRequest -Uri "http://localhost:8000/api/webhooks/health" -Method GET

# Should return:
# StatusCode: 200
# Content: {"status":"healthy"}
```

---

## Part 4: Troubleshooting

### Issue: "MAYA_API_KEY not found"

**Solution:**
```powershell
# Verify .env file exists
Get-Content c:\Users\Administrator\Desktop\RR\condoease_backend\.env

# Check for BOM encoding issues (remove if present)
# The file should start directly with MAYA_API_KEY=...
```

### Issue: "Invalid API key format"

**Solution:**
- Sandbox keys MUST start with `pk_test_` and `sk_test_`
- Production keys start with `pk_live_` and `sk_live_`
- Check you're using SANDBOX keys, not production keys

### Issue: "Webhook not being called"

**Solution:**
1. Verify webhook URL is publicly accessible (not localhost)
2. Use ngrok for local testing
3. Check firewall/network settings
4. Verify webhook secret matches in both files
5. Check backend logs for errors

### Issue: "Signature validation failed"

**Solution:**
1. Verify `MAYA_WEBHOOK_SECRET` matches exactly in Maya Dashboard
2. Check that webhook secret has not changed
3. Verify backend has reloaded .env after changes

### Issue: "Backend won't start with .env"

**Solution:**
```powershell
# Check for syntax errors in .env
# Make sure lines are: KEY=value (no spaces around =)

# Example of correct format:
MAYA_API_KEY=pk_test_something
# Example of incorrect format (will fail):
MAYA_API_KEY = pk_test_something
```

---

## Part 5: Testing the Complete Flow

### Local Testing Setup

**Prerequisites:**
- Backend running on http://localhost:8000
- ngrok tunnel to expose webhook (if testing locally)
- Valid Maya sandbox credentials

### Test Script

```powershell
# Test 1: Create a test invoice (manual)
# POST http://localhost:8000/api/invoices/create
# Body:
# {
#   "tenant_id": "test-tenant-123",
#   "amount": 1000,
#   "due_date": "2026-04-30"
# }

# Test 2: Initiate checkout
# POST http://localhost:8000/api/checkout/initiate
# Body:
# {
#   "invoice_id": "returned-from-test-1",
#   "return_url": "http://localhost:3000/payment/return"
# }

# Test 3: Get checkout URL and visit it
# Visit the returned checkout_url in a browser
# This will take you to Maya sandbox payment page

# Test 4: Complete payment in sandbox
# Use test card details (provided by Maya)
# Test card: 4111111111111111
# Expiry: 12/25
# CVC: 123

# Test 5: Verify webhook was received
# Check backend logs for:
# [INFO] Webhook received: event_type=PAYMENT_SUCCESS
# [INFO] Ledger entry created with hash: sha256_...

# Test 6: Verify invoice status changed
# GET http://localhost:8000/api/invoices/{id}
# Should show status: "PAID"
```

---

## Part 6: Production Deployment

### Before Going Live:

1. **Switch to Production Keys:**
   ```bash
   MAYA_API_KEY=pk_live_YOUR_PRODUCTION_KEY
   MAYA_SECRET_KEY=sk_live_YOUR_PRODUCTION_SECRET
   MAYA_WEBHOOK_SECRET=whsec_YOUR_PRODUCTION_SECRET
   MAYA_SANDBOX_URL=https://payments.paycom.ph  # Remove -sandbox
   ```

2. **Update URLs:**
   ```bash
   WEBHOOK_URL=https://your-domain.com/api/webhooks/payments/maya
   FRONTEND_RETURN_URL=https://your-domain.com/payment/return
   MOBILE_APP_RETURN_URL=condoease://payment/return
   ```

3. **Security Checklist:**
   - ✅ Never commit .env to git
   - ✅ Use environment-specific .env files
   - ✅ Rotate webhook secret regularly
   - ✅ Enable HTTPS only
   - ✅ Monitor webhook logs
   - ✅ Set up error alerting

---

## Quick Reference

### Webhook Test Command

```powershell
# Send test webhook to your backend
$headers = @{
    'Content-Type' = 'application/json'
}

$body = @{
    'event' = 'payment.success'
    'data' = @{
        'checkout_id' = 'test_chk_123'
        'status' = 'PAYMENT_SUCCESS'
        'amount' = 1000
    }
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/webhooks/payments/maya" `
    -Method POST `
    -Headers $headers `
    -Body $body
```

### Environment Variables Summary

| Variable | Purpose | Example |
|----------|---------|---------|
| MAYA_API_KEY | Authentication | pk_test_abc123 |
| MAYA_SECRET_KEY | Signature signing | sk_test_def456 |
| MAYA_WEBHOOK_SECRET | Webhook validation | whsec_ghi789 |
| MAYA_SANDBOX_URL | API endpoint | https://payments-sandbox.paycom.ph |
| WEBHOOK_URL | Webhook receiver | https://api.example.com/api/webhooks/payments/maya |
| FRONTEND_RETURN_URL | Web redirect | https://app.example.com/payment/return |
| MOBILE_APP_RETURN_URL | Mobile redirect | condoease://payment/return |

---

**Status:** ✅ Complete Setup Guide  
**Last Updated:** April 9, 2026  
**Version:** 1.0
