# API Reference – See's Candies UCP Gateway

Complete reference for all endpoints, request/response schemas, and error codes.

## Base URL

```
http://localhost:8000
```

## Discovery

### Get UCP Discovery Catalog

Returns a machine-readable catalog of all available endpoints and their capabilities.

```http
GET /.well-known/ucp
```

**Response (200 OK)**

```json
{
  "version": "1.0.0",
  "service_name": "sees-candies-ucp-gateway",
  "description": "See's Candies reference implementation for the Unified Commerce Protocol with a legacy payment processor used for payments settlement.",
  "endpoints": [
    {
      "name": "Begin Identity Link",
      "method": "POST",
      "path": "/identity/link",
      "summary": "Starts a mock OAuth2 flow to link a shopper identity.",
      "ucp_capability": "ucp.identity.link.v1",
      "request_schema_ref": "schema://ucp.identity.link.request.v1",
      "response_schema_ref": "schema://ucp.identity.link.response.v1"
    },
    // ... 10 more endpoints
  ]
}
```

---

## Identity

### Begin Identity Link

Initiates a mock OAuth 2.0 authorization flow for identity linking.

```http
POST /identity/link
Content-Type: application/json

{
  "customer_reference": "sees-shopper-123"
}
```

**Parameters**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `customer_reference` | string | Yes | Opaque reference for the shopper (e.g., email, wallet id, or external customer id) |

**Response (201 Created)**

```json
{
  "link_id": "link_1706000000_12345",
  "login_url": "https://auth.sees-candies.example.com/login?link_id=link_1706000000_12345",
  "expires_at": "2026-03-05T12:15:00Z"
}
```

**Fields**

| Field | Type | Description |
|-------|------|-------------|
| `link_id` | string | Synthetic identifier for the link operation |
| `login_url` | string | URL where the shopper should be redirected for login/consent |
| `expires_at` | ISO 8601 timestamp | When this login URL expires |

---

### Exchange Code for Token

Exchanges an authorization code for an OAuth 2.0-style access token.

```http
POST /identity/token
Content-Type: application/json

{
  "code": "link_1706000000_12345"
}
```

**Parameters**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | Yes | Authorization code from the login redirect (use `link_id` from previous step) |

**Response (200 OK)**

```json
{
  "access_token": "tok_1706000100_54321",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "ucp.shopping ucp.orders",
  "customer_reference": "link_1706000000_12345"
}
```

**Fields**

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | OAuth 2.0 bearer token for subsequent API calls |
| `token_type` | string | Always `Bearer` |
| `expires_in` | integer | Token lifetime in seconds (30 minutes) |
| `scope` | string | Space-delimited granted scopes |
| `customer_reference` | string | Echo of the bound customer reference |

**Errors**

| Status | Error Code | Description |
|--------|------------|-------------|
| 400 | `invalid_or_expired_code` | Code is invalid or has expired |

---

## Shopping

### List Products

Retrieve the See's Candies product catalog.

```http
GET /shopping/catalog
```

**Response (200 OK)**

```json
[
  {
    "id": "sc_truffles_box",
    "name": "See's Assorted Truffles (1 lb)",
    "description": "A classic assortment of rich chocolate truffles from See's Candies.",
    "price_cents": 3299,
    "currency": "USD"
  },
  {
    "id": "sc_lollypops_variety",
    "name": "See's Lollypops Variety Pack",
    "description": "Caramel, chocolate, vanilla, and butterscotch lollypops.",
    "price_cents": 1599,
    "currency": "USD"
  },
  // ... more products
]
```

---

### Create Cart

Create a new shopping cart with one or more items.

```http
POST /shopping/carts
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "items": [
    {
      "product_id": "sc_truffles_box",
      "quantity": 1
    },
    {
      "product_id": "sc_peanut_brittle",
      "quantity": 2
    }
  ]
}
```

**Parameters**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `items` | array | Yes | List of cart items |
| `items[].product_id` | string | Yes | Product identifier |
| `items[].quantity` | integer | Yes | Quantity (1-100) |

**Headers**

| Header | Description |
|--------|-------------|
| `Authorization` | Optional: Bearer token from identity linking (recommended) |

**Response (201 Created)**

```json
{
  "id": "cart_1",
  "items": [
    {
      "product_id": "sc_truffles_box",
      "quantity": 1
    },
    {
      "product_id": "sc_peanut_brittle",
      "quantity": 2
    }
  ],
  "subtotal_cents": 7097,
  "currency": "USD"
}
```

**Fields**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique cart identifier |
| `items` | array | Cart items |
| `subtotal_cents` | integer | Total price in cents (not including tax/shipping) |
| `currency` | string | ISO 4217 currency code |

---

### Update Cart

Replace the contents of an existing cart.

```http
PUT /shopping/carts/{cart_id}
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "items": [
    {
      "product_id": "sc_dark_chocolate",
      "quantity": 3
    }
  ]
}
```

**Parameters**

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `cart_id` | string | Path | Unique cart identifier |
| `items` | array | Body | New list of cart items |

**Response (200 OK)**

Same schema as Create Cart response.

**Errors**

| Status | Error Code | Description |
|--------|------------|-------------|
| 404 | `cart_not_found` | Cart does not exist |

---

### Get Cart

Retrieve the current state of a cart.

```http
GET /shopping/carts/{cart_id}
```

**Parameters**

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `cart_id` | string | Path | Unique cart identifier |

**Response (200 OK)**

Same schema as Create Cart response.

**Errors**

| Status | Error Code | Description |
|--------|------------|-------------|
| 404 | `cart_not_found` | Cart does not exist |

---

## Checkout

### Initiate Checkout

Start the checkout state machine for a cart. This endpoint may return either a `ready_for_complete` state (if authenticated) or a `requires_escalation` state (if identity linking is needed).

```http
POST /shopping/checkout
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "cart_id": "cart_1"
}
```

**Parameters**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cart_id` | string | Yes | Unique cart identifier |

**Headers**

| Header | Description |
|--------|-------------|
| `Authorization` | Bearer token (optional but recommended to avoid escalation) |

**Response (200 OK) – Ready for Complete**

```json
{
  "id": "chk_1",
  "cart_id": "cart_1",
  "state": "ready_for_complete",
  "total_cents": 7097,
  "currency": "USD",
  "customer_reference": "link_1706000000_12345"
}
```

**Response (200 OK) – Requires Escalation**

```json
{
  "id": "chk_1",
  "cart_id": "cart_1",
  "state": "requires_escalation",
  "total_cents": 7097,
  "currency": "USD",
  "escalation": {
    "reason": "identity_link_required",
    "login_url": "https://auth.sees-candies.example.com/login?link_id=..."
  }
}
```

**Fields**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique checkout identifier |
| `cart_id` | string | Associated cart identifier |
| `state` | enum | `ready_for_complete` or `requires_escalation` |
| `total_cents` | integer | Total amount in cents |
| `currency` | string | ISO 4217 currency code |
| `customer_reference` | string | Linked customer identifier (when authenticated) |
| `escalation` | object | Escalation details (when state is `requires_escalation`) |

**Errors**

| Status | Error Code | Description |
|--------|------------|-------------|
| 404 | `cart_not_found` | Cart does not exist |

---

### Complete Checkout

Complete the checkout and process payment via the legacy payment processor.

```http
POST /shopping/checkout/complete
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "checkout_id": "chk_1"
}
```

**Parameters**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `checkout_id` | string | Yes | Unique checkout identifier |

**Headers**

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer token from identity linking |

**Response (200 OK)**

```json
{
  "checkout": {
    "id": "chk_1",
    "cart_id": "cart_1",
    "state": "completed",
    "total_cents": 7097,
    "currency": "USD",
    "customer_reference": "link_1706000000_12345",
    "totals": {
      "subtotal_cents": 6600,
      "tax_cents": 528,
      "grand_total_cents": 7128,
      "currency": "USD"
    }
  },
  "payment": {
    "transaction_id": "TRN_SEES_1234567890",
    "status": "CAPTURED",
    "response_code": "00",
    "time_created": "2026-03-14T12:00:00+00:00",
    "amount_cents": 7128,
    "currency": "USD",
    "message": "Transaction captured successfully by the legacy payment processor."
  }
}
```

**Payment status and response codes (legacy processor)**

| Status | Description |
|--------|-------------|
| `CAPTURED` | Payment authorized and captured successfully |
| `DECLINED` | Payment declined (e.g. insufficient funds) |
| `REJECTED` | Request rejected (e.g. mandatory field missing) |

| response_code | Meaning |
|----------------|---------|
| `00` | Success |
| `101` | Declined (e.g. insufficient funds; simulated when amount > $500) |
| `502` | Rejected (mandatory field missing or invalid) |

**Errors**

| Status | Error Code | Description |
|--------|------------|-------------|
| 401 | `missing_or_invalid_authorization` | Authorization header missing or invalid |
| 404 | `checkout_not_found` | Checkout does not exist |
| 404 | `cart_not_found` | Associated cart does not exist |
| 409 | `checkout_not_ready_for_complete` | Checkout is not in `ready_for_complete` state |
| 402 | `payment_declined_insufficient_funds` | Legacy processor declined (simulated when amount > $500) |
| 402 | `payment_declined_unknown_reason` | Legacy processor declined for another reason |
| 502 | `payment_rejected_mandatory_field_missing` | Legacy processor rejected request (missing/invalid field) |

---

## Orders

### List Orders

Retrieve all orders in the system.

```http
GET /orders
```

**Response (200 OK)**

```json
[
  {
    "id": "ord_1",
    "status": "created",
    "total_cents": 7097,
    "currency": "USD"
  },
  {
    "id": "ord_2",
    "status": "fulfilled",
    "total_cents": 2499,
    "currency": "USD"
  }
]
```

---

### Get Order

Retrieve details for a specific order.

```http
GET /orders/{order_id}
```

**Parameters**

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `order_id` | string | Path | Unique order identifier |

**Response (200 OK)**

```json
{
  "id": "ord_1",
  "checkout_id": "chk_1",
  "created_at": "2026-03-05T12:00:00Z",
  "status": "created",
  "total_cents": 7097,
  "currency": "USD"
}
```

**Fields**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique order identifier |
| `checkout_id` | string | Associated checkout identifier |
| `created_at` | ISO 8601 timestamp | Order creation time |
| `status` | enum | `created`, `fulfilled`, or `cancelled` |
| `total_cents` | integer | Order total in cents |
| `currency` | string | ISO 4217 currency code |

**Errors**

| Status | Error Code | Description |
|--------|------------|-------------|
| 404 | `order_not_found` | Order does not exist |

---

### Update Order Status (Webhook)

Receive webhooks to update order status (e.g., fulfillment updates).

```http
POST /orders/webhooks/status
Content-Type: application/json

{
  "order_id": "ord_1",
  "status": "fulfilled"
}
```

**Parameters**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `order_id` | string | Yes | Unique order identifier |
| `status` | enum | Yes | New status: `created`, `fulfilled`, or `cancelled` |

**Response (202 Accepted)**

```json
{
  "order_id": "ord_1",
  "status": "fulfilled"
}
```

**Errors**

| Status | Error Code | Description |
|--------|------------|-------------|
| 404 | `order_not_found` | Order does not exist |
| 400 | `invalid_status` | Status is not a valid value |

---

## Error Handling

All errors follow the UCP error response schema:

```json
{
  "error_code": "stable_error_identifier",
  "message": "Human-readable error description",
  "details": {}
}
```

**Common HTTP Status Codes**

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 201 | Created |
| 202 | Accepted (async operation) |
| 400 | Bad Request – malformed parameters |
| 401 | Unauthorized – missing/invalid authentication |
| 402 | Payment Required – payment declined |
| 404 | Not Found – resource does not exist |
| 409 | Conflict – invalid state transition |
| 422 | Unprocessable Entity – validation error |
| 502 | Bad Gateway – downstream service error |

**Example Error Response (Payment Declined)**

```json
{
  "error_code": "payment_declined_insufficient_funds",
  "message": "Transaction declined by legacy payment processor platform (response_code=101, reason=insufficient_funds).",
  "legacy_status": "DECLINED",
  "legacy_response_code": "101"
}
```

---

## Authentication

### Bearer Token

Use the access token from the identity linking flow:

```http
Authorization: Bearer <access_token>
```

Example:

```bash
curl -H "Authorization: Bearer tok_1706000100_54321" \
  http://localhost:8000/shopping/carts
```

### Token Expiration

Access tokens expire after 30 minutes. When a token expires:

1. The API returns **401 Unauthorized**
2. Re-authenticate using the identity flow (Begin Link → Exchange Code)

---

## Rate Limiting

Currently not implemented. Planned for future versions.

---

## Webhooks

### Supported Webhooks

- `POST /orders/webhooks/status` – Order status updates

### Webhook Signature Verification

Not currently implemented. Planned for future versions.

---

## Pagination

Currently not implemented. All list endpoints return all results. Planned for future versions.

---

## Sandbox/Production

The gateway currently runs in **sandbox mode** with simulated legacy payment processor behavior. For production:

1. Update `gateway/processors/legacy_processor_adapter.py` with real legacy payment processor API credentials
2. Configure environment variables for API keys
3. Enable webhook signature verification
4. Implement database persistence (currently in-memory)

---

## SDKs & Client Libraries

Currently no official SDKs are provided. Integrate directly via HTTP calls with any HTTP client library.

Future releases may include:

- JavaScript/TypeScript SDK
- Python SDK
- Go SDK

---

## Support & Feedback

For issues, questions, or feature requests:

1. Check the **DEVELOPMENT.md** guide
2. Review **TESTING.md** for test examples
3. See **architecture.md** for design details

---

## Changelog

### v1.0.0 (2026-03-05)
- Initial release
- Identity linking (OAuth2 mock)
- Shopping (catalog, carts, checkout)
- Orders (CRUD + webhooks)
- Legacy payment processor settlement

