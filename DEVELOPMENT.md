# Development Guide – See's Candies UCP Gateway

This guide covers setup, running, testing, and extending the See's Candies UCP Gateway.

## Prerequisites

- **Python 3.9+**
- **pip** (Python package installer)

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd agent-commerce-bridge-ucp
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r gateway/requirements.txt
```

## Running the Application

### Development mode (with auto-reload)

```bash
cd gateway
python main.py
```

The API will be available at `http://localhost:8000`.

### Access interactive API documentation

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Project Structure

```
agent-commerce-bridge-ucp/
├── gateway/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app, discovery, error handlers
│   ├── requirements.txt                 # Python dependencies
│   ├── services/
│   │   ├── __init__.py
│   │   ├── identity.py                  # OAuth2-style identity linking
│   │   ├── shopping.py                  # Products, carts, checkout
│   │   └── orders.py                    # Post-purchase order management
│   └── processors/
│       ├── __init__.py
│       └── legacy_processor_adapter.py   # Legacy payment processor API adapter
├── spec/
│   └── architecture.md                  # System design and flow diagrams
├── README.md                            # User-facing documentation
├── DEVELOPMENT.md                       # This file
└── LICENSE                              # MIT License
```

## API Endpoints

All endpoints are documented in the **Architecture** section of `README.md`. For a quick overview:

### Discovery
- `GET /.well-known/ucp` – Returns catalog of UCP capabilities

### Identity
- `POST /identity/link` – Begin OAuth2-style identity linking
- `POST /identity/token` – Exchange code for access token

### Shopping
- `GET /shopping/catalog` – List See's Candies products
- `POST /shopping/carts` – Create cart
- `PUT /shopping/carts/{cart_id}` – Update cart
- `GET /shopping/carts/{cart_id}` – Retrieve cart

### Checkout
- `POST /shopping/checkout` – Initiate checkout
- `POST /shopping/checkout/complete` – Complete checkout with legacy payment processor settlement

### Orders
- `GET /orders` – List all orders
- `GET /orders/{order_id}` – Get single order
- `POST /orders/webhooks/status` – Update order status via webhook

## Testing Workflows

### Full end-to-end flow (using curl or Postman)

1. **Discover capabilities**
   ```bash
   curl http://localhost:8000/.well-known/ucp
   ```

2. **Begin identity linking**
   ```bash
   curl -X POST http://localhost:8000/identity/link \
     -H "Content-Type: application/json" \
     -d '{"customer_reference": "sees-shopper-123"}'
   ```
   Save the `link_id` from the response.

3. **Exchange code for token**
   ```bash
   curl -X POST http://localhost:8000/identity/token \
     -H "Content-Type: application/json" \
     -d '{"code": "<link_id>"}'
   ```
   Save the `access_token` for subsequent requests.

4. **Get product catalog**
   ```bash
   curl http://localhost:8000/shopping/catalog
   ```

5. **Create cart**
   ```bash
   curl -X POST http://localhost:8000/shopping/carts \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <access_token>" \
     -d '{
       "items": [
         {"product_id": "sc_truffles_box", "quantity": 1}
       ]
     }'
   ```
   Save the `id` (cart_id).

6. **Initiate checkout**
   ```bash
   curl -X POST http://localhost:8000/shopping/checkout \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <access_token>" \
     -d '{"cart_id": "<cart_id>"}'
   ```
   Save the `id` (checkout_id) from the response.

7. **Complete checkout**
   ```bash
   curl -X POST http://localhost:8000/shopping/checkout/complete \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <access_token>" \
     -d '{"checkout_id": "<checkout_id>"}'
   ```
   This triggers the legacy payment processor payment processing.

## Understanding the Code

### `main.py`
- Initializes the FastAPI application
- Registers service routers (identity, shopping, orders)
- Implements discovery endpoint (`/.well-known/ucp`)
- Defines error handlers for legacy payment processor declines and validation errors

### `services/identity.py`
- Mocks OAuth2 authorization flow
- Issues short-lived access tokens
- Provides helper to validate Bearer tokens

### `services/shopping.py`
- Maintains product catalog
- Implements cart CRUD operations
- Manages checkout state machine (incomplete → ready_for_complete → completed)
- Integrates with legacy payment processor adapter for payment settlement
- Handles escalation pattern when identity linking is required

### `services/orders.py`
- Stores order records created from completed checkouts
- Provides order retrieval endpoints
- Implements webhook endpoint for status updates (fulfilled/cancelled)

### `processors/legacy_processor_adapter.py`
- Simulates legacy payment processor `authorize-and-capture` behavior
- Uses transaction amount threshold to simulate decline (e.g. amount > $500 → insufficient funds)
- Maps legacy processor decline codes to UCP error semantics

## Extending the System

### Adding a new product

Edit `gateway/services/shopping.py` in the `_PRODUCTS` dictionary:

```python
_PRODUCTS: Dict[str, Product] = {
    # ... existing products ...
    "sc_new_product": Product(
        id="sc_new_product",
        name="New Product Name",
        description="Product description",
        price_cents=9999,  # Price in cents (e.g., 99.99)
    ),
}
```

### Adding a new checkout state

Edit `gateway/services/shopping.py` in the `CheckoutState` enum:

```python
class CheckoutState(str, Enum):
    # ... existing states ...
    NEW_STATE = "new_state"
```

Then update the state machine logic in the `initiate_checkout()` and `complete_checkout()` functions.

### Integrating with a real payment processor

Replace the simulated `authorize_and_capture()` function in `gateway/processors/legacy_processor_adapter.py` with a real API call:

```python
def authorize_and_capture(
    request: LegacyAuthorizeAndCaptureRequest,
) -> LegacyAuthorizeAndCaptureResult:
    # Call real legacy payment processor API
    # response = legacy_client.authorize_and_capture(...)
    # Return mapped result
    pass
```

### Adding OAuth2 with real identity provider

Replace the mock token storage in `gateway/services/identity.py` with real integrations:

```python
async def exchange_code_for_token(
    payload: TokenExchangeRequest,
) -> TokenResponse:
    # Call OAuth2 provider (e.g., Auth0, Okta, Google)
    # token = oauth_provider.exchange_code(payload.code)
    # Store in database or cache
    pass
```

## Deployment

### Using Docker

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t sees-candies-ucp-gateway .
docker run -p 8000:8000 sees-candies-ucp-gateway
```

### Using a production ASGI server

```bash
pip install gunicorn
gunicorn gateway.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Troubleshooting

### Module not found errors

Ensure you're running from the project root and the virtual environment is activated:

```bash
source venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:/Users/sandeeppuniya/dev-pm/agent-commerce-bridge-ucp"
```

### Port 8000 already in use

Change the port in `gateway/main.py`:

```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,  # Change to different port
        reload=True,
    )
```

### Database persistence

Currently, all data is stored in-memory and will be lost on restart. For persistence, integrate a database:

1. Install `sqlalchemy` and a database driver (e.g., `psycopg2` for PostgreSQL)
2. Define ORM models in a new `gateway/models/` directory
3. Update services to use database sessions instead of in-memory dictionaries

## Contributing

When contributing:

1. Follow **PEP 8** style guidelines
2. Add type hints to all functions
3. Document new endpoints in `architecture.md`
4. Test end-to-end flows before committing
5. Update this guide if adding new features

## License

This project is licensed under the **MIT License** – see `LICENSE` for details.

