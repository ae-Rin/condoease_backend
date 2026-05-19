# Maya Sandbox Payment Integration Guide

## Overview

This guide describes the stable backend payment flow for CondoEase using Maya payment gateway sandbox integration.

## Architecture

### Payment Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PAYMENT FLOW DIAGRAM                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. CLIENT REQUEST CHECKOUT                                    │
│     └─> POST /api/checkout/initiate                           │
│         {invoice_id, return_url}                              │
│                                                                 │
│  2. BACKEND CREATES MAYA SESSION                              │
│     └─> MayaService.create_checkout()                         │
│         Returns: {checkout_url, checkout_id}                  │
│                                                                 │
│  3. CLIENT REDIRECTS TO MAYA                                  │
│     └─> https://payments-sandbox.paycom.ph/checkout/...      │
│                                                                 │
│  4. MAYA PROCESSES PAYMENT                                    │
│     └─> User enters payment details                           │
│     └─> Payment processed                                     │
│                                                                 │
│  5. MAYA SENDS WEBHOOK                                        │
│     └─> POST /api/webhooks/payments/maya                      │
│         Signature: X-Maya-Signature (HMAC-SHA256)             │
│                                                                 │
│  6. BACKEND VALIDATES & CONFIRMS                              │
│     └─> WebhookProcessor.validate_and_process_webhook()      │
│         • Verify signature                                    │
│         • Validate payload                                    │
│         • Mark invoice PAID                                   │
│         • Create ledger entry with hash                       │
│                                                                 │
│  7. CLIENT REDIRECT (AFTER WEBHOOK)                           │
│     └─> Redirect to return_url                               │
│     └─> Client polls /api/invoices/{id} for status           │
│                                                                 │
│  8. BLOCKCHAIN CONFIRMATION                                   │
│     └─> Ledger entry created (immutable)                      │
│     └─> Transaction hash available for verification           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. MayaService (services/maya_service.py)

Handles all Maya API interactions:

- **create_checkout()** - Create sandbox checkout session
- **validate_webhook_signature()** - Verify webhook signature (HMAC-SHA256)
- **parse_webhook_payload()** - Extract and validate webhook data
- **get_payment_status()** - Query payment status from Maya

### 2. WebhookProcessor (services/webhook_service.py)

Validates and processes payment webhooks:

- Validates webhook signature using secret key
- Parses webhook payload
- Routes to handler based on payment status
- Creates immutable ledger entries
- Handles idempotency (safe for retries)

### 3. Webhook Routes (routers/webhooks.py)

**POST /api/webhooks/payments/maya**
- Main webhook handler
- Validates X-Maya-Signature header
- Processes payment events
- Returns confirmation

**GET /api/webhooks/health**
- Health check for webhook endpoint

### 4. Checkout Routes (routers/checkout.py)

**POST /api/checkout/initiate**
- Initialize payment checkout
- Create Maya session
- Return checkout URL for redirect

**POST /api/checkout/status**
- Query checkout/payment status
- Optional polling endpoint

## Environment Configuration

Required environment variables:

```bash
# Maya API Credentials (from sandbox dashboard)
MAYA_API_KEY=your_sandbox_api_key
MAYA_SECRET_KEY=your_sandbox_secret_key
MAYA_WEBHOOK_SECRET=your_webhook_secret

# API URLs
MAYA_SANDBOX_URL=https://payments-sandbox.paycom.ph
WEBHOOK_URL=https://your-backend.com/api/webhooks/payments/maya

# Frontend URLs
FRONTEND_RETURN_URL=https://your-frontend.com/payment/return
MOBILE_APP_RETURN_URL=condoease://payment/return
```

## Implementation Guide

### Step 1: Get Maya API Keys

1. Sign up at Maya Payments (https://www.paymaya.com/)
2. Create sandbox account
3. Generate API keys from dashboard
4. Copy API Key, Secret Key, and Webhook Secret

### Step 2: Configure Environment

```bash
# .env file
MAYA_API_KEY=sk_test_...
MAYA_SECRET_KEY=pk_test_...
MAYA_WEBHOOK_SECRET=whsec_...
WEBHOOK_URL=https://api.condoease.ph/api/webhooks/payments/maya
```

### Step 3: Register Webhook in Maya Dashboard

1. Go to Maya dashboard > Webhooks
2. Register webhook URL: `{WEBHOOK_URL}`
3. Select events: PAYMENT_SUCCESS, PAYMENT_FAILED, PAYMENT_EXPIRED
4. Note the secret (MAYA_WEBHOOK_SECRET)

### Step 4: Client Integration

#### Web/Frontend

```javascript
// 1. Initiate checkout
const response = await fetch('/api/checkout/initiate', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: JSON.stringify({
    invoice_id: 1,
    return_url: window.location.href
  })
});

const { checkout_url } = await response.json();

// 2. Redirect to Maya
window.location.href = checkout_url;

// 3. After payment, user returns to return_url
// Poll for payment status
const interval = setInterval(async () => {
  const status = await fetch(`/api/invoices/1`);
  const invoice = await status.json();
  
  if (invoice.status === 'PAID') {
    clearInterval(interval);
    // Show success
  }
}, 2000);
```

#### Mobile (React Native)

See condoease-mobile implementation below.

## Payment Status Flow

### Successful Payment

```
PENDING → (User pays) → Webhook PAYMENT_SUCCESS → PAID → Ledger Entry Created
```

1. Invoice starts as PENDING
2. User completes payment on Maya
3. Maya calls webhook with PAYMENT_SUCCESS
4. Backend validates signature
5. Invoice marked as PAID
6. Immutable ledger entry created with hash
7. Hash available for blockchain confirmation

### Failed/Expired Payment

```
PENDING → (Payment fails) → Webhook PAYMENT_FAILED/EXPIRED → PENDING (stays pending)
```

User can retry payment.

## Ledger & Blockchain Confirmation

After successful payment:

1. **Ledger Entry Created**
   ```python
   transaction_hash = SHA256(invoice_id|tenant_id|amount|timestamp)
   previous_hash = last_ledger_entry.transaction_hash or "0"
   ```

2. **Immutable Chain**
   - Ledger entries are append-only
   - Each entry references previous hash
   - No update/delete allowed

3. **Verification**
   - Compute hash and compare with stored
   - Check chain integrity
   - Verify blockchain confirmation

## Error Handling

### Webhook Validation Errors

```
Missing X-Maya-Signature → 401 Unauthorized
Invalid Signature → 400 Bad Request (logged)
Invalid Payload → 400 Bad Request
Missing invoice_id/tenant_id → 400 Bad Request
```

### Payment Processing Errors

```
Invoice Not Found → Webhook logged, user retries
Tenant Mismatch → Webhook logged, user retries
Ledger Conflict → Invoice already has ledger entry
```

All errors are logged for audit trail.

## Testing

### Local Testing

1. Use Maya sandbox credentials
2. Test with sandbox cards (provided by Maya)
3. Webhooks can be tested with webhook.site or similar

### Test Scenarios

**Successful Payment:**
```bash
curl -X POST http://localhost:8000/api/checkout/initiate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": 1,
    "return_url": "http://localhost:3000/payment/return"
  }'
```

**Webhook Simulation:**
```bash
# Signature: HMAC-SHA256(secret, body)
BODY='{"status":"PAYMENT_SUCCESS","amount":{"value":5000,"currency":"PHP"},"metadata":{"invoice_id":"1","tenant_id":"1"}}'
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "webhook_secret" -hex | cut -d' ' -f2)

curl -X POST http://localhost:8000/api/webhooks/payments/maya \
  -H "X-Maya-Signature: $SIGNATURE" \
  -H "Content-Type: application/json" \
  -d "$BODY"
```

## Security Considerations

1. **Signature Validation**
   - Always verify X-Maya-Signature
   - Use constant-time comparison to prevent timing attacks
   - Reject invalid signatures

2. **Webhook Secret**
   - Keep MAYA_WEBHOOK_SECRET secure
   - Rotate periodically
   - Never commit to version control

3. **Idempotency**
   - Webhook handlers are idempotent
   - Safe to retry on network failures
   - Already-paid invoices return existing hash

4. **Invoice Validation**
   - Verify invoice exists
   - Check tenant ownership
   - Validate amount matches
   - Prevent double-payment

5. **Ledger Immutability**
   - No update/delete API for ledger
   - Only append on payment confirm
   - Chain integrity verified on read

## Troubleshooting

### Webhook Not Being Called

1. Check webhook URL in Maya dashboard
2. Verify firewall allows inbound connections
3. Check X-Maya-Signature header is being sent
4. Test with webhook.site to see raw requests

### Signature Validation Failing

1. Verify MAYA_WEBHOOK_SECRET is correct
2. Check raw request body (not parsed JSON)
3. Verify signature algorithm (HMAC-SHA256)
4. Check headers for typos

### Invoice Not Updating After Payment

1. Check webhook logs
2. Verify invoice_id in webhook metadata
3. Check tenant_id matches
4. Look for database transaction errors

### Ledger Entry Not Created

1. Check invoice is marked PAID
2. Verify amount matches invoice
3. Check for unique constraint on invoice_id
4. Review ledger_service error logs

## API Reference

See:
- `INVOICE_API_REFERENCE.md` - Invoice endpoints
- `PAYMENT_LEDGER.md` - Ledger verification
- Inline documentation in `routers/webhooks.py`
- Inline documentation in `routers/checkout.py`

## Related Files

- `services/maya_service.py` - Maya API integration
- `services/webhook_service.py` - Webhook validation
- `routers/webhooks.py` - Webhook endpoints
- `routers/checkout.py` - Checkout endpoints
- `models/payment_ledger.py` - Ledger model
- `models/invoice.py` - Invoice model
