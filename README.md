## agent-commerce-bridge-ucp

A reference implementation of a **See's Candies Full-Lifecycle UCP Gateway** backed by a simulated **legacy payment processor API**.  
It exposes UCP 2026-compliant flows for discovery, identity, shopping, checkout (state machine), and orders.

### Sequence Guide (Postman / Agent Flow)

This guide shows the exact HTTP calls and order for a full See’s Candies purchase through the UCP gateway.

#### 1. Discovery – GET `/.well-known/ucp`

- **Method**: `GET`
- **URL**: `http://localhost:8000/.well-known/ucp`
- **Purpose**: Discover all UCP capabilities (identity, shopping, checkout, orders) in a machine-readable catalog.

The response enumerates:
- Identity flows (`/oauth/token`, `/identity/link`, `/identity/token`)
- Shopping/catalog/cart (`/ucp/catalog`, `/ucp/cart`, `/shopping/carts/{cart_id}`)
- Checkout state machine (`/ucp/checkout-sessions`, `/ucp/complete`)
- Orders and webhooks (`/orders`, `/orders/{order_id}`, `/orders/webhooks/status`)

#### 2. Mock Identity – POST `/oauth/token` (Identity Linking)

- **Method**: `POST`
- **URL**: `http://localhost:8000/oauth/token`
- **Body**: none required (mock implementation)

**Response (200)**:

```json
{
  "auth_token": "<jwt-like-token>",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

Use this `auth_token` for all subsequent UCP calls:
- Header: `Authorization: Bearer <auth_token>`

This token satisfies the UCP 2026 requirement for an `auth_token` in the checkout state machine.

#### 3. Catalog – GET `/ucp/catalog` (Browsing See’s Products)

- **Method**: `GET`
- **URL**: `http://localhost:8000/ucp/catalog`
- **Headers**: `Authorization` is optional for browsing.

**Response**: List of 5 See’s Candies 1 lb products, all at \$33.00:

- Milk Chocolate Bordeaux (#540318)
- Scotchmallow (#506542)
- Peanut Brittle
- Assorted Chocolates
- Toffee-ettes

Each product includes:
- `id`, `name`, `description`
- `price_cents` (3300)
- `sku`
- `inventory_count`

#### 4. Cart – POST `/ucp/cart` (Adding Items)

- **Method**: `POST`
- **URL**: `http://localhost:8000/ucp/cart`
- **Headers**:
  - `Authorization: Bearer <auth_token>` (recommended)
- **Body (JSON)** example:

```json
{
  "items": [
    { "product_id": "540318", "quantity": 1 },
    { "product_id": "peanut_brittle", "quantity": 1 }
  ]
}
```

**Response (201)**:

```json
{
  "id": "cart_1",
  "items": [
    { "product_id": "540318", "quantity": 1 },
    { "product_id": "peanut_brittle", "quantity": 1 }
  ],
  "currency": "USD",
  "totals": {
    "subtotal_cents": 6600,
    "tax_cents": 528,
    "grand_total_cents": 7128,
    "currency": "USD"
  }
}
```

- `totals` implements an **8% tax** (`tax_cents`) over the catalog subtotal.

You can subsequently inspect the cart at:
- `GET http://localhost:8000/shopping/carts/{cart_id}`

#### 5. Checkout Session – POST `/ucp/checkout-sessions` (UCP State Machine)

- **Method**: `POST`
- **URL**: `http://localhost:8000/ucp/checkout-sessions`
- **Headers**:
  - `Authorization: Bearer <auth_token>` – controls state transitions.
- **Body (JSON)**:

```json
{
  "cart_id": "cart_1",
  "buyer": {
    "name": "See's Shopper",
    "shipping_address": "210 El Camino Real, South San Francisco, CA 94080",
    "email": "shopper@example.com"
  }
}
```

**State machine semantics (UCP 2026 aligned)**:

- **`incomplete`** – Missing `buyer` or `shipping_address`
  - Response example:
    ```json
    {
      "state": "incomplete",
      "messages": [
        {
          "code": "buyer.shipping_address.missing",
          "severity": "error",
          "text": "Shipping address is required to initiate checkout."
        }
      ]
    }
    ```
  - Fix by supplying the required buyer fields and retry.

- **`requires_escalation`** – Missing `auth_token`
  - Trigger: Omit the `Authorization` header.
  - Response includes:
    - `state`: `requires_escalation`
    - `escalation.continue_url`: mock login URL (e.g. `https://auth.sees-candies.example.com/ucp/login`)
    - `messages` entry with `severity`: `escalation` describing the next step.

- **`ready_for_complete`** – All data present (buyer, shipping_address, auth_token)
  - With complete buyer info and `Authorization: Bearer <auth_token>`, the response includes:
    - `state`: `ready_for_complete`
    - `totals`: UCP totals object (with 8% tax)
    - `messages` entry (severity `info`) indicating you may call `POST /ucp/complete`.

Example success response (truncated):

```json
{
  "id": "chk_1",
  "cart_id": "cart_1",
  "state": "ready_for_complete",
  "currency": "USD",
  "total_cents": 7128,
  "totals": {
    "subtotal_cents": 6600,
    "tax_cents": 528,
    "grand_total_cents": 7128,
    "currency": "USD"
  },
  "messages": [
    {
      "code": "checkout.ready_for_complete",
      "severity": "info",
      "text": "Checkout session is ready for completion via POST /ucp/complete."
    }
  ]
}
```

#### 6. Legacy Payment Processor Settlement – POST `/ucp/complete` (Authorize & Capture)

- **Method**: `POST`
- **URL**: `http://localhost:8000/ucp/complete`
- **Headers**:
  - `Authorization: Bearer <auth_token>`
- **Body (JSON)**:

```json
{
  "checkout_id": "chk_1"
}
```

This calls the legacy payment processor adapter to perform an **Authorize & Capture** operation mapped to legacy processor fields:
- `transaction_id` (format: `TRN_...`)
- `status` (`CAPTURED`, `DECLINED`, or `REJECTED`)
- `response_code`

**Success case**:

- For amounts **≤ \$500.00**:
  - `response_code`: `"00"`
  - `status`: `"CAPTURED"`
  - UCP response includes:
    - `checkout.state`: `"completed"`
    - `payment.transaction_id`, `payment.status`, `payment.response_code`, and metadata.

**Insufficient funds**:

- For amounts **> \$500.00**:
  - The legacy payment processor simulates decline:
    - `response_code`: `"101"`
    - `status`: `"DECLINED"`
  - The gateway raises a `LegacyProcessorError` and maps it to a UCP error:
    - HTTP **402**
    - Body:
      ```json
      {
        "error_code": "payment_declined_insufficient_funds",
        "message": "Transaction declined by legacy payment processor platform (response_code=101, reason=insufficient_funds).",
        "legacy_status": "DECLINED",
        "legacy_response_code": "101"
      }
      ```

**Mandatory field missing**:

- If the legacy processor request is malformed (e.g., `merchant_id`, `currency`, `reference`, or `amount_cents` missing/invalid):
  - The legacy payment processor simulates rejection:
    - `response_code`: `"502"`
    - `status`: `"REJECTED"`
  - The gateway emits:
    - UCP error_code: `payment_rejected_mandatory_field_missing`
    - HTTP **502**

### Why Legacy Payment Processor + UCP (2026) is Fintech-Grade

- **Protocol-precise error semantics**
  - Legacy processor outcomes (`CAPTURED`, `DECLINED`, `REJECTED`) and `response_code`s (`00`, `101`, `502`) are preserved and mapped to UCP error codes.
  - Agents can distinguish **insufficient funds** from **request-level rejections**, enabling smarter retry and routing strategies.

- **UCP 2026-aligned checkout state machine**
  - Explicit states: `incomplete`, `requires_escalation`, `ready_for_complete`, `completed`, `failed`.
  - Each state carries structured `messages` with `severity` (`error`, `escalation`, `info`), making it trivial for agents to understand next steps.

- **Merchant abstraction with real-world data**
  - See’s Candies products and pricing (real 1 lb offerings) are exposed via UCP catalog and cart semantics.
  - Tax and totals are computed in a dedicated `totals` object, reflecting how production gateways present monetary breakdowns.

- **Composable for future acquiring**
  - By separating:
    - UCP (control plane & protocol: discovery, identity, carts, checkout, orders)
    - Legacy payment processor (settlement & acquiring semantics: transaction_id, response_code, status),
  - the same UCP agent logic can span multiple acquirers or merchants, while keeping **legacy processor rails** underneath. 
