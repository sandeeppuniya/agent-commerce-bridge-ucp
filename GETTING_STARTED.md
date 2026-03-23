# Getting Started – See's Candies UCP Gateway

Quick start guide to run the See's Candies UCP Gateway in 5 minutes.

## 1. Prerequisites

Ensure you have:
- **Python 3.9+** installed
- **pip** (Python package installer)
- **curl** or **Postman** (for testing)

```bash
python3 --version  # Should be 3.9+
pip3 --version     # Should be available
```

## 2. Clone & Setup

```bash
# Clone the repository (or download the code)
cd /Users/sandeeppuniya/dev-pm/agent-commerce-bridge-ucp

# Create a virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r gateway/requirements.txt
```

## 3. Run the Server

```bash
cd gateway
python main.py
```

You should see output like:

```
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

## 4. Test the API

### Option A: Using curl

**Discover capabilities:**

```bash
curl http://localhost:8000/.well-known/ucp
```

### Option B: Using Postman

1. Open **Postman**
2. Import the collection or follow the **step-by-step guide in README.md**

### Option C: Using Swagger UI

Open your browser:
```
http://localhost:8000/docs
```

You can test all endpoints directly in the interactive UI.

## 5. Full Workflow (3 minutes)

Here's a complete purchase flow:

### Step 1: Discover endpoints
```bash
curl http://localhost:8000/.well-known/ucp | jq .
```

### Step 2: Link identity
```bash
curl -X POST http://localhost:8000/identity/link \
  -H "Content-Type: application/json" \
  -d '{"customer_reference": "shopper123"}' | jq .
```

Save the `link_id` from the response.

### Step 3: Exchange for token
```bash
curl -X POST http://localhost:8000/identity/token \
  -H "Content-Type: application/json" \
  -d '{"code": "PASTE_LINK_ID_HERE"}' | jq .
```

Save the `access_token` from the response.

### Step 4: Get products
```bash
curl http://localhost:8000/shopping/catalog | jq .
```

### Step 5: Create cart
```bash
curl -X POST http://localhost:8000/shopping/carts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer PASTE_ACCESS_TOKEN_HERE" \
  -d '{
    "items": [
      {"product_id": "sc_truffles_box", "quantity": 1}
    ]
  }' | jq .
```

Save the `id` (cart_id) from the response.

### Step 6: Checkout
```bash
curl -X POST http://localhost:8000/shopping/checkout \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer PASTE_ACCESS_TOKEN_HERE" \
  -d '{"cart_id": "PASTE_CART_ID_HERE"}' | jq .
```

Save the `id` (checkout_id) from the response. You should see:
```json
{
  "state": "ready_for_complete",
  ...
}
```

### Step 7: Complete purchase
```bash
curl -X POST http://localhost:8000/shopping/checkout/complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer PASTE_ACCESS_TOKEN_HERE" \
  -d '{"checkout_id": "PASTE_CHECKOUT_ID_HERE"}' | jq .
```

You should see:
```json
{
  "checkout": {
    "state": "completed",
    ...
  },
  "payment": {
    "status": "CAPTURED",
    ...
  }
}
```

**🎉 Congratulations! You've completed a full purchase flow.**

## 6. Next Steps

### Explore Further

- **API Reference**: See `API_REFERENCE.md` for all 11 endpoints
- **Architecture**: Read `spec/architecture.md` for system design
- **Development**: Follow `DEVELOPMENT.md` for setup and extension
- **Testing**: Check `TESTING.md` for test examples

### Try Different Scenarios

**Test a payment decline** (amount > $500):
```bash
# Create cart with expensive items
curl -X POST http://localhost:8000/shopping/carts \
  -H "Authorization: Bearer TOKEN" \
  -d '{
    "items": [{"product_id": "sc_dark_chocolate", "quantity": 5}]
  }'
```

This creates a cart worth $124.95, which will decline at checkout with error:
```json
{
  "error_code": "payment_declined_insufficient_funds",
  "message": "Transaction declined by legacy payment processor platform (response_code=101, reason=insufficient_funds).",
  "legacy_status": "DECLINED",
  "legacy_response_code": "101"
}
```

**Test escalation** (checkout without auth):
```bash
# Initiate checkout WITHOUT Authorization header
curl -X POST http://localhost:8000/shopping/checkout \
  -H "Content-Type: application/json" \
  -d '{"cart_id": "cart_1"}'
```

This returns a `requires_escalation` response with a `login_url`.

### Run Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

(See `TESTING.md` for more test examples.)

## 7. Documentation Map

| File | Purpose | Read Time |
|------|---------|-----------|
| **README.md** | Overview + Postman guide | 10 min |
| **API_REFERENCE.md** | Complete API docs | 15 min |
| **DEVELOPMENT.md** | Setup + extension | 20 min |
| **TESTING.md** | Testing guide | 15 min |
| **spec/architecture.md** | System design | 10 min |
| **PROJECT_STATUS.md** | Completeness audit | 5 min |

## 8. Troubleshooting

### Port 8000 already in use

Change the port in `gateway/main.py`:
```python
uvicorn.run(..., port=8001, ...)
```

### Module not found errors

```bash
export PYTHONPATH="${PYTHONPATH}:/Users/sandeeppuniya/dev-pm/agent-commerce-bridge-ucp"
```

### Virtual environment not activated

```bash
source venv/bin/activate
```

### Import errors on startup

```bash
pip install -r gateway/requirements.txt --upgrade
```

## 9. What's Next?

### For Users
- Integrate the gateway into your AI agent
- Use the API reference to understand endpoints
- Follow the Postman guide for manual testing

### For Developers
- Review `DEVELOPMENT.md` for architecture
- Check `TESTING.md` for testing strategies
- Extend with database, real legacy payment processor API, etc.

### For Operators
- Deploy with Docker (see `DEVELOPMENT.md`)
- Set up monitoring and logging
- Configure production legacy payment processor credentials

## 10. Key Concepts

### UCP Discovery
The gateway exposes a `/.well-known/ucp` endpoint that describes all capabilities. This allows AI agents to dynamically discover and use the API.

### Identity Linking
OAuth2-style flow where shoppers link their identity before checking out.

### Checkout State Machine
Checkouts progress through states:
- `incomplete` → identity required
- `requires_escalation` → shopper must authenticate
- `ready_for_complete` → ready for payment
- `completed` → payment successful
- `failed` → payment declined

### Legacy Processor Integration
The gateway simulates legacy payment processor Unified API for payment processing. Real legacy payment processor credentials can be used in production.

### Error Mapping
Legacy processor response codes (e.g. `101` decline, `502` rejected) are included in error responses and mapped to UCP error codes for intelligent agent decision-making.

## 11. Quick Reference

| Task | Command |
|------|---------|
| Start server | `cd gateway && python main.py` |
| View API docs | `http://localhost:8000/docs` |
| List endpoints | `curl http://localhost:8000/.well-known/ucp` |
| Run tests | `pytest tests/ -v` |
| Install deps | `pip install -r gateway/requirements.txt` |

---

**🚀 Ready to build with the UCP Gateway? Start with the API Reference or jump into development with DEVELOPMENT.md!**

