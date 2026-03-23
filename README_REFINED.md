# See's Candies UCP Gateway – Enterprise Fintech Implementation

A professional-grade reference implementation for bridging autonomous AI agents (UCP 2026) with traditional payment rails. Built with **See's Candies** as the merchant, backed by **legacy payment processor Unified API** simulation, demonstrating Fintech-standard precision in checkout flows, error handling, and transaction settlement.

---

## Quick Start: Postman Collection Sequence

### 1️⃣ Discover Gateway Capabilities
**Endpoint Discovery via UCP Discovery Document**

```http
GET http://localhost:8000/.well-known/ucp
```

**Purpose**: Machine-readable catalog of all UCP capabilities (identity, shopping, checkout, orders).

**Expected Response**:
```json
{
  "version": "1.0.0",
  "service_name": "sees-candies-ucp-gateway",
  "endpoints": [
    { "name": "Begin Identity Link", "path": "/identity/link", "ucp_capability": "ucp.identity.link.v1", ... },
    { "name": "Product Catalog", "path": "/shopping/catalog", "ucp_capability": "ucp.shopping.catalog.v1", ... },
    ...11 endpoints total
  ]
}
```

---

### 2️⃣ OAuth Token Exchange (Identity Linking)
**Step 2a: Initiate OAuth 2.0 Flow**

```http
POST http://localhost:8000/identity/link
Content-Type: application/json

{
  "customer_reference": "sees-shopper-123"
}
```

**Expected Response** (201 Created):
```json
{
  "link_id": "link_1704067200_abcd",
  "login_url": "https://auth.sees-candies.example.com/login?link_id=link_1704067200_abcd",
  "expires_at": "2026-03-05T12:15:00Z"
}
```

**Step 2b: Exchange Authorization Code for Access Token**

```http
POST http://localhost:8000/identity/token
Content-Type: application/json

{
  "code": "link_1704067200_abcd"
}
```

**Expected Response** (200 OK):
```json
{
  "access_token": "tok_1704067300_xyz",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "ucp.shopping ucp.orders",
  "customer_reference": "link_1704067200_abcd"
}
```

**Save**: `access_token` for use in subsequent requests via `Authorization: Bearer <access_token>` header.

---

### 3️⃣ Product Catalog & Cart Management

**Step 3a: Discover Available Products**

```http
GET http://localhost:8000/shopping/catalog
```

**Expected Response** (200 OK):
```json
[
  {
    "id": "sc_truffles_box",
    "name": "See's Assorted Truffles (1 lb)",
    "description": "A classic assortment of rich chocolate truffles from See's Candies.",
    "price_cents": 3299,
    "sku": "SKU-001",
    "inventory_count": 150,
    "currency": "USD"
  },
  ...7 products total (including new Milk Chocolate Bordeaux and Scotchmallow)
]
```

**Step 3b: Create Shopping Cart**

```http
POST http://localhost:8000/shopping/carts
Authorization: Bearer tok_1704067300_xyz
Content-Type: application/json

{
  "items": [
    { "product_id": "sc_truffles_box", "quantity": 1 },
    { "product_id": "sc_milk_chocolate_bordeaux", "quantity": 2 }
  ]
}
```

**Expected Response** (201 Created):
```json
{
  "id": "cart_1",
  "items": [
    { "product_id": "sc_truffles_box", "quantity": 1 },
    { "product_id": "sc_milk_chocolate_bordeaux", "quantity": 2 }
  ],
  "subtotal_cents": 9797,
  "currency": "USD"
}
```

**Step 3c (Optional): Update Cart**

```http
PUT http://localhost:8000/shopping/carts/cart_1
Authorization: Bearer tok_1704067300_xyz
Content-Type: application/json

{
  "items": [
    { "product_id": "sc_scotchmallow", "quantity": 1 }
  ]
}
```

**Step 3d: Retrieve Current Cart State**

```http
GET http://localhost:8000/shopping/carts/cart_1
```

---

### 4️⃣ Checkout with UCP 2026 State Machine

**Step 4a: Initiate Checkout (UCP State Machine Entry)**

```http
POST http://localhost:8000/shopping/checkout
Authorization: Bearer tok_1704067300_xyz
Content-Type: application/json

{
  "cart_id": "cart_1",
  "buyer": {
    "shipping_address": "123 Oak St, Oakland CA 94618",
    "email": "shopper@example.com",
    "phone": "+1-510-555-0123"
  }
}
```

**Expected Response** (200 OK) – Ready for Payment:
```json
{
  "id": "chk_1",
  "cart_id": "cart_1",
  "state": "ready_for_complete",
  "total_cents": 2850,
  "currency": "USD",
  "customer_reference": "link_1704067200_abcd"
}
```

**Alternative Response** (if buyer info missing):
```json
{
  "id": "chk_1",
  "state": "incomplete",
  "total_cents": 2850,
  "currency": "USD",
  "messages": ["Missing required field: shipping_address"]
}
```

**Alternative Response** (if auth token missing):
```json
{
  "id": "chk_1",
  "state": "requires_escalation",
  "total_cents": 2850,
  "currency": "USD",
  "escalation": {
    "reason": "auth_token_required",
    "continue_url": "https://auth.sees-candies.example.com/login?link_id=..."
  }
}
```

**Step 4b: Complete Checkout & Capture Payment (legacy payment processor Authorize & Capture)**

```http
POST http://localhost:8000/shopping/checkout/complete
Authorization: Bearer tok_1704067300_xyz
Content-Type: application/json

{
  "checkout_id": "chk_1"
}
```

**Success Response** (200 OK) – CAPTURED Status:
```json
{
  "checkout": {
    "id": "chk_1",
    "state": "completed",
    "total_cents": 2850,
    "currency": "USD"
  },
  "payment": {
    "transaction_id": "TRN_sees-candies-us_chk_1_1704067400",
    "status": "CAPTURED",
    "response_code": "00",
    "time_created": "2026-03-05T12:10:00Z",
    "amount_cents": 2850,
    "currency": "USD",
    "decline_code": null,
    "message": "Transaction captured successfully by legacy payment processor."
  }
}
```

**Decline Response** (402 Payment Required) – Amount > $500 triggers 1502 error:
```http
HTTP/1.1 402 Payment Required
Content-Type: application/json

{
  "error_code": "payment_declined_insufficient_funds",
  "message": "Transaction declined by legacy payment processor platform (response_code=101, decline_code=1502).",
  "legacy_decline_code": "1502",
  "legacy_response_code": "101"
}
```

---

### 5️⃣ Post-Purchase Order Management

**Step 5a: Retrieve Order Details**

```http
GET http://localhost:8000/orders/ord_1
```

**Expected Response** (200 OK):
```json
{
  "id": "ord_1",
  "checkout_id": "chk_1",
  "created_at": "2026-03-05T12:10:00Z",
  "status": "created",
  "total_cents": 2850,
  "currency": "USD"
}
```

**Step 5b: List All Orders**

```http
GET http://localhost:8000/orders
```

**Step 5c: Webhook – Update Order Status (Fulfillment)**

```http
POST http://localhost:8000/orders/webhooks/status
Content-Type: application/json

{
  "order_id": "ord_1",
  "status": "fulfilled"
}
```

**Expected Response** (202 Accepted):
```json
{
  "order_id": "ord_1",
  "status": "fulfilled"
}
```

---

## Fintech Architecture Highlights

### 1. Authentic legacy payment processor API Integration
- **Transaction IDs**: `TRN_` prefix (e.g., `TRN_sees-candies-us_chk_1_1704067400`)
- **Response Codes**: `00` (success), `101` (decline), industry-standard legacy payment processor semantics
- **Status Values**: `CAPTURED`, `DECLINED`, `PENDING` (per legacy payment processor specification)
- **Timestamps**: ISO-8601 UTC (e.g., `2026-03-05T12:10:00Z`)
- **Decline Codes**: 
  - `1502` – Insufficient Funds (amount > $500)
  - `D001` – Generic Decline (amount > $100)
  - `D002` – Suspected Fraud (amount > $250)

### 2. Strict UCP 2026 State Machine
- **`incomplete`**: Missing required buyer info (shipping_address)
- **`requires_escalation`**: Missing auth token (identity linking required)
- **`ready_for_complete`**: All requirements met, ready for legacy payment processor capture
- **`completed`**: Payment authorized and captured
- **`failed`**: Payment declined by legacy payment processor

### 3. Rich Error Semantics for Agents
- Stable UCP error codes (`payment_declined_insufficient_funds`, etc.)
- Legacy processor decline codes and response codes included for transparency
- HTTP status codes reflect financial semantics (402 Payment Required, etc.)
- Structured `messages` array for missing field guidance

### 4. Professional Product Data
- **7 Premium Confections**: Including new Milk Chocolate Bordeaux ($32.00) and Scotchmallow ($28.50)
- **SKU Management**: Each product has unique inventory SKU
- **Real Inventory**: Stock counts for each item
- **Currency**: USD with cent precision

### 5. Identity & Checkout Integration
- OAuth 2.0-style flow for shopper authentication
- Bearer token expiration (30 minutes)
- Buyer info (shipping address, email, phone) validation at checkout
- Escalation pattern when identity linking required

---

## Testing Payment Scenarios

### Scenario 1: Successful Purchase (Amount < $100)
```bash
curl -X POST http://localhost:8000/shopping/checkout/complete \
  -H "Authorization: Bearer <token>" \
  -d '{"checkout_id": "chk_1"}'
# Expected: 200 OK with CAPTURED status
```

### Scenario 2: Insufficient Funds Decline (Amount > $500)
Create cart with expensive items (e.g., 15× Milk Chocolate Bordeaux = $4,800)
```bash
# Expected: 402 Payment Required with 1502 decline code
```

### Scenario 3: Escalation (Missing Auth)
Initiate checkout without Authorization header
```bash
# Expected: 200 OK with requires_escalation state and continue_url
```

### Scenario 4: Incomplete Checkout (Missing Buyer Info)
Initiate checkout without shipping_address in buyer info
```bash
# Expected: 200 OK with incomplete state and messages array
```

---

## Why See's Candies + Legacy payment processor + UCP Defines the Future

- **Fintech Precision**: Authentic legacy payment processor field names, response codes, and transaction semantics
- **Agent-Ready**: UCP 2026 state machine enables autonomous AI navigation
- **Error Intelligence**: Stable error codes allow agents to handle declines programmatically
- **Merchant Composability**: Same agent logic works across multiple legacy payment processor-backed merchants
- **Settlement Abstraction**: Agents work with UCP concepts; legacy payment processor handles acquiring and risk

