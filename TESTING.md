# Testing Guide – See's Candies UCP Gateway

This guide covers manual testing, integration testing, and test scenarios for the UCP gateway.

## Manual Testing (Postman/cURL)

See the **Testing Workflows** section in `DEVELOPMENT.md` for step-by-step cURL examples.

## Integration Testing

### Unit test example

Create `tests/test_identity.py`:

```python
import pytest
from gateway.services.identity import start_identity_link, IdentityLinkRequest

@pytest.mark.asyncio
async def test_identity_link_creates_link_id():
    request = IdentityLinkRequest(customer_reference="test-customer-123")
    response = await start_identity_link(request)
    
    assert response.link_id is not None
    assert response.login_url is not None
    assert response.expires_at is not None
```

### Integration test example

Create `tests/test_full_flow.py`:

```python
import pytest
from fastapi.testclient import TestClient
from gateway.main import app

client = TestClient(app)

def test_full_checkout_flow():
    # 1. Discover
    response = client.get("/.well-known/ucp")
    assert response.status_code == 200
    
    # 2. Link identity
    response = client.post("/identity/link", json={
        "customer_reference": "test-shopper"
    })
    assert response.status_code == 201
    link_id = response.json()["link_id"]
    
    # 3. Exchange for token
    response = client.post("/identity/token", json={"code": link_id})
    assert response.status_code == 200
    token = response.json()["access_token"]
    
    # 4. Create cart
    response = client.post("/shopping/carts", 
        headers={"Authorization": f"Bearer {token}"},
        json={"items": [{"product_id": "sc_truffles_box", "quantity": 1}]}
    )
    assert response.status_code == 201
    cart_id = response.json()["id"]
    
    # 5. Initiate checkout
    response = client.post("/shopping/checkout",
        headers={"Authorization": f"Bearer {token}"},
        json={"cart_id": cart_id}
    )
    assert response.status_code == 200
    checkout_id = response.json()["id"]
    assert response.json()["state"] == "ready_for_complete"
    
    # 6. Complete checkout
    response = client.post("/shopping/checkout/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"checkout_id": checkout_id}
    )
    assert response.status_code == 200
    assert response.json()["checkout"]["state"] == "completed"
    assert response.json()["payment"]["status"] == "CAPTURED"
```

### Payment decline test

Create `tests/test_payment_declines.py`:

```python
import pytest
from fastapi.testclient import TestClient
from gateway.main import app

client = TestClient(app)

def test_payment_decline_insufficient_funds():
    """
    Create cart with items totaling > $500.00
    This triggers legacy processor decline (insufficient_funds, response_code 101)
    """
    # Setup: identity and cart
    # (see full_flow test above for setup)
    
    # Create cart with high-value items
    response = client.post("/shopping/carts",
        headers={"Authorization": f"Bearer {token}"},
        json={"items": [
            {"product_id": "sc_dark_chocolate", "quantity": 5}  # 5 × $24.99 = $124.95
        ]}
    )
    cart_id = response.json()["id"]
    
    # Initiate and complete checkout
    response = client.post("/shopping/checkout",
        headers={"Authorization": f"Bearer {token}"},
        json={"cart_id": cart_id}
    )
    checkout_id = response.json()["id"]
    
    response = client.post("/shopping/checkout/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"checkout_id": checkout_id}
    )
    
    # Expect 402 Payment Required with UCP error
    assert response.status_code == 402
    assert response.json()["error_code"] == "payment_declined_insufficient_funds"
    assert response.json()["legacy_response_code"] == "101"

def test_payment_decline_suspected_fraud():
    """
    Optional: When the legacy processor adapter supports suspected_fraud (e.g. D002),
    create a cart that triggers it and assert payment_declined_suspected_fraud.
    Currently the gateway only simulates insufficient_funds (amount > $500) with
    legacy_response_code "101". This test is a placeholder until that decline reason is implemented.
    """
    # Similar setup...
    # When implemented: create cart that triggers suspected_fraud decline
    # assert response.status_code == 402
    # assert response.json()["error_code"] == "payment_declined_suspected_fraud"
    # assert response.json()["legacy_response_code"] == "101"
    pass
```

### Escalation flow test

Create `tests/test_escalation.py`:

```python
import pytest
from fastapi.testclient import TestClient
from gateway.main import app

client = TestClient(app)

def test_checkout_escalation_without_auth():
    """
    If no Authorization header, checkout should return requires_escalation
    """
    # Create cart without authentication
    response = client.post("/shopping/carts",
        json={"items": [{"product_id": "sc_truffles_box", "quantity": 1}]}
    )
    cart_id = response.json()["id"]
    
    # Initiate checkout WITHOUT auth header
    response = client.post("/shopping/checkout",
        json={"cart_id": cart_id}
    )
    
    assert response.status_code == 200
    assert response.json()["state"] == "requires_escalation"
    assert response.json()["escalation"]["login_url"] is not None
    assert "login_url" in response.json()["escalation"]
```

### Order webhook test

Create `tests/test_orders.py`:

```python
import pytest
from fastapi.testclient import TestClient
from gateway.main import app

client = TestClient(app)

def test_order_status_webhook():
    """
    Send webhook to update order status from fulfilled to completed
    """
    # Setup: complete a checkout first (see full_flow test)
    # This creates an order
    
    # List orders to get order_id
    response = client.get("/orders")
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) > 0
    order_id = orders[0]["id"]
    
    # Send webhook to update status
    response = client.post("/orders/webhooks/status",
        json={
            "order_id": order_id,
            "status": "fulfilled"
        }
    )
    
    assert response.status_code == 202  # Accepted
    
    # Verify status was updated
    response = client.get(f"/orders/{order_id}")
    assert response.json()["status"] == "fulfilled"
```

## Running Tests

### Setup pytest

```bash
pip install pytest pytest-asyncio httpx
```

### Create test structure

```
agent-commerce-bridge-ucp/
├── tests/
│   ├── __init__.py
│   ├── test_identity.py
│   ├── test_shopping.py
│   ├── test_orders.py
│   └── test_full_flow.py
```

### Run all tests

```bash
pytest tests/
```

### Run specific test

```bash
pytest tests/test_full_flow.py::test_full_checkout_flow
```

### Run with verbose output

```bash
pytest tests/ -v
```

### Generate coverage report

```bash
pip install pytest-cov
pytest tests/ --cov=gateway --cov-report=html
```

## Test Scenarios

### Happy Path
- ✓ Complete identity link → token exchange → cart creation → checkout → payment
- ✓ Product catalog retrieval
- ✓ Cart CRUD operations
- ✓ Order retrieval and listing

### Edge Cases
- ✓ Payment decline on amount threshold (e.g. > $500 → insufficient_funds)
- ✓ Invalid authorization code (expired)
- ✓ Missing Authorization header (escalation flow)
- ✓ Non-existent cart/checkout/order (404)
- ✓ Invalid status transitions (409)
- ✓ Malformed request payload (422)

### Load Testing

For basic load testing, use Apache Bench or similar:

```bash
# Install Apache Bench (macOS)
brew install httpd

# Run 1000 requests, 10 concurrent
ab -n 1000 -c 10 http://localhost:8000/.well-known/ucp
```

For detailed load testing, consider `locust`:

```bash
pip install locust
```

Create `locustfile.py`:

```python
from locust import HttpUser, task, between

class UcpGatewayUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def discover(self):
        self.client.get("/.well-known/ucp")
    
    @task(1)
    def list_products(self):
        self.client.get("/shopping/catalog")
```

Run:

```bash
locust -f locustfile.py --host=http://localhost:8000
```

## Monitoring & Observability

### Enable logging

Add to `gateway/main.py`:

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.post("/shopping/checkout/complete")
async def complete_checkout(payload: CheckoutCompleteRequest, request: Request):
    logger.info(f"Completing checkout {payload.checkout_id}")
    # ... rest of function
```

### Add request tracing

Install `opentelemetry`:

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi
```

## Best Practices

1. **Isolate tests** – Use fixtures to reset state between tests
2. **Test async functions** – Use `@pytest.mark.asyncio`
3. **Mock external dependencies** – Replace legacy payment processor calls with mocks in tests
4. **Test error paths** – Verify error responses and status codes
5. **Use descriptive names** – Test names should explain what they're testing
6. **Keep tests fast** – Avoid network calls, sleep, etc.
7. **Document test scenarios** – Explain what each test validates

## CI/CD Integration

Add to your CI pipeline (GitHub Actions, GitLab CI, etc.):

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install -r gateway/requirements.txt pytest pytest-asyncio
      - run: pytest tests/
```

