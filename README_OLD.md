## agent-commerce-bridge-ucp

A reference implementation for bridging autonomous AI agents (UCP) with traditional payment rails, tailored here as a **See's Candies Full-Lifecycle UCP Gateway** backed by a simulated **legacy payment processor Unified API**.

### Step-by-step Postman sequence

- **Step 1 – Discover capabilities**
  - **Method**: `GET`
  - **URL**: `http://localhost:8000/.well-known/ucp`
  - **Goal**: Let an agent (or Postman collection) discover the full set of UCP capabilities: identity, shopping, checkout, and orders.

- **Step 2 – Link identity (mock OAuth 2.0)**
  - **2a. Begin link**
    - **Method**: `POST`
    - **URL**: `http://localhost:8000/identity/link`
    - **Body (JSON)**:
      ```json
      {
        "customer_reference": "sees-shopper-123"
      }
      ```
    - **Result**: You receive a `link_id`, `login_url`, and `expires_at`. In a real deployment, the shopper would be redirected to `login_url`.
  - **2b. Exchange code for token**
    - **Method**: `POST`
    - **URL**: `http://localhost:8000/identity/token`
    - **Body (JSON)**:
      ```json
      {
        "code": "<link_id from step 2a>"
      }
      ```
    - **Result**: You receive an `access_token`. Use this as a Bearer token for shopping, checkout, and orders:
      - Header: `Authorization: Bearer <access_token>`

- **Step 3 – Build cart with See’s Candies products**
  - **3a. Discover catalog**
    - **Method**: `GET`
    - **URL**: `http://localhost:8000/shopping/catalog`
    - **Result**: List of 5 See’s Candies products (ids such as `sc_truffles_box`, `sc_peanut_brittle`, etc.).
  - **3b. Create cart**
    - **Method**: `POST`
    - **URL**: `http://localhost:8000/shopping/carts`
    - **Headers**:
      - `Authorization: Bearer <access_token>` (optional but recommended)
    - **Body (JSON)**:
      ```json
      {
        "items": [
          { "product_id": "sc_truffles_box", "quantity": 1 },
          { "product_id": "sc_peanut_brittle", "quantity": 2 }
        ]
      }
      ```
    - **Result**: A cart summary including `id`, `items`, and `subtotal_cents`.
  - **3c. (Optional) Update cart**
    - **Method**: `PUT`
    - **URL**: `http://localhost:8000/shopping/carts/{cart_id}`
    - **Body (JSON)**: new `items` array, same shape as above.
  - **3d. Fetch cart**
    - **Method**: `GET`
    - **URL**: `http://localhost:8000/shopping/carts/{cart_id}`

- **Step 4 – Execute legacy payment processor-backed checkout**
  - **4a. Initiate checkout**
    - **Method**: `POST`
    - **URL**: `http://localhost:8000/shopping/checkout`
    - **Headers**:
      - Option 1 (recommended first-class flow): `Authorization: Bearer <access_token>`
      - Option 2 (to see escalation behavior): omit the `Authorization` header.
    - **Body (JSON)**:
      ```json
      {
        "cart_id": "<cart_id from step 3>"
      }
      ```
    - **Result**:
      - If `Authorization` is **present and valid**: checkout state becomes `ready_for_complete`.
      - If `Authorization` is **missing or invalid**: checkout state becomes `requires_escalation` and includes an `escalation.login_url`. This is the UCP-compliant `requires_escalation` pattern.
  - **4b. Complete checkout (legacy payment processor authorize & capture)**
    - **Precondition**: The checkout state is `ready_for_complete`.
    - **Method**: `POST`
    - **URL**: `http://localhost:8000/shopping/checkout/complete`
    - **Headers**:
      - `Authorization: Bearer <access_token>`
    - **Body (JSON)**:
      ```json
      {
        "checkout_id": "<checkout_id from step 4a>"
      }
      ```
    - **Result**:
      - On success: checkout state transitions to `completed` and the `payment` object contains:
        - `status` = `approved`
        - `legacy_transaction_id`, `auth_code`, and a success `message`.
      - On simulated Legacy processor decline: the API returns a structured **UCP error** with:
        - `error_code` such as `payment_declined_insufficient_funds` or `payment_declined_suspected_fraud`
        - `legacy_decline_code` (e.g. `D001`, `D002`)
        - `message` from the Legacy Payment Processor Adapter

### Order management and webhooks

- **List orders**
  - `GET http://localhost:8000/orders`
- **Get single order**
  - `GET http://localhost:8000/orders/{order_id}`
- **Status webhook (mock)**
  - `POST http://localhost:8000/orders/webhooks/status`
  - Body example:
    ```json
    {
      "order_id": "ord_1",
      "status": "fulfilled"
    }
    ```

### Why Legacy payment processor + UCP is the future of Merchant Acquiring

- **Protocol-native for agents**
  - **UCP** gives AI agents a stable, machine-readable contract for discovery, identity, shopping, checkout, and orders.
  - Capabilities exposed via `/.well-known/ucp` make it trivial for tools and agents to self-configure against a merchant gateway.

- **Abstracted settlement with legacy payment processor**
  - The gateway encapsulates **legacy payment processor’s API** as a processor behind UCP’s checkout state machine.
  - Agents reason about UCP concepts (carts, checkouts, escalation, orders), while the gateway handles mapping to **legacy payment processor authorize & capture** semantics.

- **Rich error semantics for intelligent automation**
  - Legacy processor decline codes are translated into **UCP-flavored error codes** (`payment_declined_insufficient_funds`, `payment_declined_suspected_fraud`, etc.) so agents can adapt flows intelligently.
  - This moves merchant acquiring from “opaque error strings” to **structured, automatable decision signals**.

- **Composable across channels and merchants**
  - Because UCP defines common patterns (identity linking, cart/checkout lifecycle, webhooks), the same agent logic can orchestrate across multiple legacy payment processor-backed merchants with minimal change.
  - legacy payment processor remains the high-scale acquiring and risk layer, while UCP becomes the **unifying control plane** for autonomous commerce.
