from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, constr


class DiscoveryEndpoint(BaseModel):
    """Describes a single UCP-compliant operation exposed by this gateway."""

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
    """Machine-readable catalog of this gateway's capabilities."""

    version: str = Field(..., description="Catalog version.")
    service_name: str = Field(..., description="Logical name of this gateway service.")
    description: str = Field(..., description="High-level service description.")
    endpoints: List[DiscoveryEndpoint] = Field(
        ..., description="List of UCP-compliant endpoints."
    )


class PaymentAmount(BaseModel):
    currency: constr(min_length=3, max_length=3) = Field(
        ..., description="ISO 4217 currency code (e.g. USD, EUR)."
    )
    value: constr(regex=r"^\d+(\.\d{1,2})?$") = Field(
        ..., description="Decimal amount as a string with up to 2 decimal places."
    )


class PaymentIntent(BaseModel):
    """Represents the intent produced by an AI agent under the UCP schema."""

    merchant_id: str = Field(..., description="UCP merchant identifier.")
    order_id: str = Field(..., description="Merchant order identifier.")
    amount: PaymentAmount = Field(..., description="Amount to authorize.")
    customer_id: Optional[str] = Field(
        None, description="Optional customer identifier from merchant or UCP."
    )
    payment_method_hint: Optional[str] = Field(
        None,
        description="Optional hint such as 'paypal', 'card', etc., which can inform routing.",
    )
    metadata: Optional[dict] = Field(
        default_factory=dict,
        description="Arbitrary key/value metadata attached by the agent.",
    )


class AuthorizationResponse(BaseModel):
    """Represents the response from the Legacy Payment Bridge."""

    legacy_transaction_id: str = Field(
        ..., description="Opaque transaction identifier from the legacy bridge."
    )
    status: Literal["authorized", "declined", "error"] = Field(
        ..., description="High-level authorization status."
    )
    message: Optional[str] = Field(
        None,
        description="Optional human-readable message for logging or debugging.",
    )


app = FastAPI(
    title="Agent Commerce Bridge Gateway",
    description=(
        "Gateway providing UCP-compliant discovery and a mock authorization bridge "
        "between AI Agents and legacy payment infrastructure."
    ),
    version="0.1.0",
)


@app.get(
    "/discovery",
    response_model=DiscoveryCatalog,
    summary="UCP discovery catalog",
    tags=["discovery"],
)
async def get_discovery_catalog() -> DiscoveryCatalog:
    """
    Returns a machine-readable catalog describing this gateway's capabilities
    in a UCP-friendly format.
    """
    catalog = DiscoveryCatalog(
        version="1.0.0",
        service_name="agent-commerce-bridge-gateway",
        description=(
            "Foundational gateway for bridging autonomous AI agents (UCP) with "
            "legacy payment systems."
        ),
        endpoints=[
            DiscoveryEndpoint(
                name="Discovery Catalog",
                method="GET",
                path="/discovery",
                summary="Returns this machine-readable capability catalog.",
                ucp_capability="ucp.discovery.catalog.v1",
                request_schema_ref=None,
                response_schema_ref="schema://ucp.discovery.catalog.v1",
            ),
            DiscoveryEndpoint(
                name="Authorize Payment Intent",
                method="POST",
                path="/authorize",
                summary="Accepts a Payment Intent from an AI Agent and returns a Legacy Transaction ID.",
                ucp_capability="ucp.payments.authorize.v1",
                request_schema_ref="schema://ucp.payments.payment_intent.v1",
                response_schema_ref="schema://ucp.payments.authorization_response.v1",
            ),
        ],
    )
    return catalog


@app.post(
    "/authorize",
    response_model=AuthorizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Authorize a payment intent",
    tags=["payments"],
)
async def authorize_payment_intent(intent: PaymentIntent) -> AuthorizationResponse:
    """
    Mock authorization endpoint that receives a Payment Intent from an AI Agent
    and returns a synthetic Legacy Transaction ID.

    In a future iteration, this is where orchestration with the Legacy Payment Bridge
    and PayPal API integration would be implemented.
    """
    if float(intent.amount.value) <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than zero.",
        )

    legacy_transaction_id = (
        f"LEGACY-{intent.merchant_id}-{intent.order_id}"
    )  # deterministic mock ID

    return AuthorizationResponse(
        legacy_transaction_id=legacy_transaction_id,
        status="authorized",
        message="Mock authorization succeeded.",
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

