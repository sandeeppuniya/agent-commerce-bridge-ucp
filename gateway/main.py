from typing import List, Literal, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from gateway.processors.legacy_processor_adapter import LegacyProcessorError
from gateway.services.identity import router as identity_router
from gateway.services.orders import router as orders_router
from gateway.services.shopping import (
    CartSummary,
    CheckoutCompleteRequest,
    CheckoutCompleteResponse,
    CheckoutInitiateRequest,
    CheckoutSession,
    Product,
    CreateCartRequest,
    list_products,
    create_cart,
    initiate_checkout,
    complete_checkout,
    router as shopping_router,
)


class DiscoveryEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Human-readable name of the endpoint.")
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = Field(
        ..., description="HTTP method."
    )
    path: str = Field(..., description="Path of the endpoint.")
    summary: str = Field(..., description="Short functional summary.")
    ucp_capability: str = Field(
        ..., description="Identifier for the UCP capability this endpoint implements."
    )
    request_schema_ref: Optional[str] = Field(
        None,
        description="Optional reference (e.g. JSON Schema ID) for the request payload.",
    )
    response_schema_ref: Optional[str] = Field(
        None,
        description="Optional reference (e.g. JSON Schema ID) for the response payload.",
    )


class DiscoveryCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(..., description="Catalog version.")
    service_name: str = Field(..., description="Logical name of this gateway service.")
    description: str = Field(..., description="High-level service description.")
    endpoints: List[DiscoveryEndpoint] = Field(
        ..., description="List of UCP-compliant endpoints."
    )


class UcpErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(..., description="Stable UCP error identifier.")
    message: str = Field(..., description="Human-readable description.")
    legacy_status: Optional[str] = Field(
        None, description="Raw status returned by the legacy payment processor (e.g., CAPTURED, DECLINED, REJECTED)."
    )
    legacy_response_code: Optional[str] = Field(
        None,
        description="Legacy processor response code for debugging (e.g., '00' for success, '101' for insufficient funds, '502' for mandatory field missing).",
    )


app = FastAPI(
    title="See's Candies UCP Gateway (legacy payment processor-backed)",
    description=(
        "Full-lifecycle UCP gateway for See's Candies, including discovery, identity "
        "linking, shopping, checkout, and post-purchase order management. "
        "Final settlement is simulated using legacy payment processor API semantics."
    ),
    version="1.0.0",
)

app.include_router(identity_router)
app.include_router(shopping_router)
app.include_router(orders_router)


class OAuthTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_token: str = Field(..., description="Mock JWT-style token for use in Authorization header.")
    token_type: str = Field(default="Bearer", description="Token type.")
    expires_in: int = Field(
        default=3600, description="Token lifetime in seconds from issue time."
    )


@app.post(
    "/oauth/token",
    response_model=OAuthTokenResponse,
    summary="Mock Identity endpoint issuing a JWT-style auth_token.",
    tags=["identity"],
)
async def oauth_token() -> OAuthTokenResponse:
    """
    Issues a mock JWT-style auth_token suitable for use with the UCP 2026
    checkout state machine.

    Clients should send:
        Authorization: Bearer <auth_token>
    on subsequent /ucp/* requests.
    """
    from time import time

    auth_token = f"eyJhbGciOiJub25lIn0.mock-sees-candies-{int(time())}.signature"
    return OAuthTokenResponse(auth_token=auth_token)


@app.get(
    "/.well-known/ucp",
    response_model=DiscoveryCatalog,
    summary="UCP Discovery document for this See's Candies gateway.",
    tags=["discovery"],
)
async def get_ucp_discovery() -> DiscoveryCatalog:
    """
    Returns a machine-readable catalog describing this gateway's capabilities
    across identity, shopping, checkout, and order management.
    """
    return DiscoveryCatalog(
        version="1.0.0",
        service_name="sees-candies-ucp-gateway",
        description=(
            "See's Candies reference implementation for the Unified Commerce Protocol "
            "with a legacy payment processor used for payments settlement."
        ),
        endpoints=[
            DiscoveryEndpoint(
                name="Mock OAuth Token",
                method="POST",
                path="/oauth/token",
                summary="Issues a mock JWT auth_token for UCP 2026 flows.",
                ucp_capability="ucp.identity.oauth.token.v1",
                request_schema_ref="schema://ucp.identity.oauth.token.request.v1",
                response_schema_ref="schema://ucp.identity.oauth.token.response.v1",
            ),
            DiscoveryEndpoint(
                name="Begin Identity Link",
                method="POST",
                path="/identity/link",
                summary="Starts a mock OAuth2 flow to link a shopper identity.",
                ucp_capability="ucp.identity.link.v1",
                request_schema_ref="schema://ucp.identity.link.request.v1",
                response_schema_ref="schema://ucp.identity.link.response.v1",
            ),
            DiscoveryEndpoint(
                name="Exchange Code for Token",
                method="POST",
                path="/identity/token",
                summary="Exchanges a mock authorization code for an access token.",
                ucp_capability="ucp.identity.token.v1",
                request_schema_ref="schema://ucp.identity.token.request.v1",
                response_schema_ref="schema://ucp.identity.token.response.v1",
            ),
            DiscoveryEndpoint(
                name="Product Catalog",
                method="GET",
                path="/ucp/catalog",
                summary="Lists See's Candies products available for shopping (UCP view).",
                ucp_capability="ucp.shopping.catalog.v1",
                request_schema_ref=None,
                response_schema_ref="schema://ucp.shopping.catalog.v1",
            ),
            DiscoveryEndpoint(
                name="Create Cart",
                method="POST",
                path="/ucp/cart",
                summary="Creates a cart with one or more See's Candies items (UCP view).",
                ucp_capability="ucp.shopping.cart.create.v1",
                request_schema_ref="schema://ucp.shopping.cart.create.request.v1",
                response_schema_ref="schema://ucp.shopping.cart.summary.v1",
            ),
            DiscoveryEndpoint(
                name="Get Cart",
                method="GET",
                path="/shopping/carts/{cart_id}",
                summary="Retrieves current cart contents and totals.",
                ucp_capability="ucp.shopping.cart.get.v1",
                request_schema_ref=None,
                response_schema_ref="schema://ucp.shopping.cart.summary.v1",
            ),
            DiscoveryEndpoint(
                name="Initiate Checkout",
                method="POST",
                path="/ucp/checkout-sessions",
                summary="Starts the UCP 2026 checkout state machine.",
                ucp_capability="ucp.checkout.initiate.v1",
                request_schema_ref="schema://ucp.checkout.initiate.request.v1",
                response_schema_ref="schema://ucp.checkout.session.v1",
            ),
            DiscoveryEndpoint(
                name="Complete Checkout",
                method="POST",
                path="/ucp/complete",
                summary="Transitions checkout from ready_for_complete to completed via legacy payment processor settlement.",
                ucp_capability="ucp.checkout.complete.v1",
                request_schema_ref="schema://ucp.checkout.complete.request.v1",
                response_schema_ref="schema://ucp.checkout.complete.response.v1",
            ),
            DiscoveryEndpoint(
                name="Get Order",
                method="GET",
                path="/orders/{order_id}",
                summary="Retrieves an order for post-purchase management.",
                ucp_capability="ucp.orders.get.v1",
                request_schema_ref=None,
                response_schema_ref="schema://ucp.orders.order.v1",
            ),
            DiscoveryEndpoint(
                name="List Orders",
                method="GET",
                path="/orders",
                summary="Lists all orders in this mock environment.",
                ucp_capability="ucp.orders.list.v1",
                request_schema_ref=None,
                response_schema_ref="schema://ucp.orders.order_list.v1",
            ),
            DiscoveryEndpoint(
                name="Order Status Webhook",
                method="POST",
                path="/orders/webhooks/status",
                summary="Receives status updates (fulfilled/cancelled) from downstream systems.",
                ucp_capability="ucp.orders.webhook.status.v1",
                request_schema_ref="schema://ucp.orders.webhook.status.request.v1",
                response_schema_ref=None,
            ),
        ],
    )


@app.get(
    "/ucp/catalog",
    response_model=List[Product],
    summary="UCP 2026 view of the See's Candies product catalog.",
    tags=["ucp", "shopping"],
)
async def ucp_catalog() -> List[Product]:
    """
    Thin UCP routing layer over the shopping service's catalog.
    """
    return await list_products()


@app.post(
    "/ucp/cart",
    response_model=CartSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a UCP 2026 cart with See's Candies items.",
    tags=["ucp", "shopping"],
)
async def ucp_create_cart(
    payload: CreateCartRequest, request: Request
) -> CartSummary:
    """
    UCP-flavored entry point for cart creation, delegating to the shopping service.
    """
    return await create_cart(payload, request)


@app.post(
    "/ucp/checkout-sessions",
    response_model=CheckoutSession,
    summary="Create a UCP 2026 checkout session (state machine entry).",
    tags=["ucp", "checkout"],
)
async def ucp_checkout_sessions(
    payload: CheckoutInitiateRequest, request: Request
) -> CheckoutSession:
    """
    Direct UCP 2026-compliant entry point into the checkout state machine.
    """
    return await initiate_checkout(payload, request)


@app.post(
    "/ucp/complete",
    response_model=CheckoutCompleteResponse,
    summary="Complete a UCP checkout session, invoking legacy payment processor settlement.",
    tags=["ucp", "checkout"],
)
async def ucp_complete(
    payload: CheckoutCompleteRequest, request: Request
) -> CheckoutCompleteResponse:
    """
    Completes a checkout session that is in 'ready_for_complete' state,
    delegating to the shopping service and legacy payment processor adapter.
    """
    return await complete_checkout(payload, request)


def _map_legacy_to_ucp_error(response_code: str, status: str) -> str:
    """
    Map legacy payment processor response_code + status to UCP-compliant error codes.

    - '101' + 'DECLINED' -> payment_declined_insufficient_funds
    - '502' + 'REJECTED' -> payment_rejected_mandatory_field_missing
    - otherwise          -> payment_declined_unknown_reason
    """
    if response_code == "101" and status == "DECLINED":
        return "payment_declined_insufficient_funds"
    if response_code == "502" and status == "REJECTED":
        return "payment_rejected_mandatory_field_missing"
    return "payment_declined_unknown_reason"


@app.exception_handler(LegacyProcessorError)
async def handle_legacy_processor_error(_: Request, exc: LegacyProcessorError) -> JSONResponse:
    """
    Maps legacy payment processor decline codes into UCP-flavored errors with stable
    identifiers and HTTP semantics suitable for agents.
    Includes response_code for debugging and transparency.
    """
    error_code = _map_legacy_to_ucp_error(exc.response_code, exc.status)
    status_code = (
        status.HTTP_402_PAYMENT_REQUIRED
        if error_code != "payment_declined_unknown_reason"
        else status.HTTP_502_BAD_GATEWAY
    )
    payload = UcpErrorResponse(
        error_code=error_code,
        message=exc.message,
        legacy_status=exc.status,
        legacy_response_code=exc.response_code,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Provide a compact, UCP-friendly view of validation errors so that agents
    can reason about malformed requests programmatically.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "request_validation_failed",
            "message": "Request payload failed validation.",
            "details": exc.errors(),
        },
    )


def create_app() -> FastAPI:
    """
    FastAPI application factory.

    Using a factory makes it easy to plug this app into different
    deployment environments (ASGI servers, tests, etc.).
    """
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

