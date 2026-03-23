from enum import Enum
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from gateway.services.identity import IdentityPrincipal, resolve_principal_from_request
from gateway.processors.legacy_processor_adapter import (
    LegacyAuthorizeAndCaptureRequest,
    LegacyAuthorizeAndCaptureResult,
    LegacyProcessorError,
    authorize_and_capture,
)


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    price_cents: int
    currency: str = "USD"
    sku: str = Field(..., description="Stock Keeping Unit for inventory management")
    inventory_count: int = Field(..., ge=0, description="Available units in stock")


class CartItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    quantity: int = Field(..., gt=0, le=100)


class Cart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    items: List[CartItem]
    currency: str = "USD"
    customer_reference: Optional[str] = None


class Totals(BaseModel):
    """
    UCP-style totals object including subtotal, tax, and grand total.
    Tax is computed at a fixed 8% rate for See's Candies reference pricing.
    """

    model_config = ConfigDict(extra="forbid")

    subtotal_cents: int
    tax_cents: int
    grand_total_cents: int
    currency: str


class CartSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    items: List[CartItem]
    currency: str
    totals: Totals


class CheckoutState(str, Enum):
    INCOMPLETE = "incomplete"
    REQUIRES_ESCALATION = "requires_escalation"
    READY_FOR_COMPLETE = "ready_for_complete"
    COMPLETED = "completed"
    FAILED = "failed"


class BuyerInfo(BaseModel):
    """UCP 2026 buyer information for checkout compliance."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, description="Buyer full name")
    shipping_address: Optional[str] = Field(
        None, description="Shipping address (required for checkout completion)"
    )
    email: Optional[str] = Field(None, description="Buyer email address")
    phone: Optional[str] = Field(None, description="Buyer phone number")


class CheckoutInitiateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_id: str = Field(..., description="Identifier of the cart to check out.")
    buyer: Optional[BuyerInfo] = Field(
        None, description="Buyer information for UCP 2026 compliance"
    )


class UcpMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Optional[str] = Field(
        None, description="Stable message code for machine processing."
    )
    severity: Literal["info", "warning", "error", "escalation"] = Field(
        ..., description="Message severity as defined by UCP 2026."
    )
    text: str = Field(..., description="Human-readable message text.")


class EscalationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., description="Why escalation is required.")
    continue_url: str = Field(
        ..., description="URL to continue (e.g., for identity linking)."
    )


class CheckoutSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    cart_id: str
    state: CheckoutState
    total_cents: int
    currency: str
    customer_reference: Optional[str] = None
    totals: Totals
    escalation: Optional[EscalationContext] = None
    messages: Optional[List[UcpMessage]] = Field(
        None, description="Array of UCP 2026 messages (errors, escalations, info)."
    )


class CheckoutCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkout_id: str = Field(..., description="Identifier of the checkout session.")


class CheckoutCompleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkout: CheckoutSession
    payment: Optional[LegacyAuthorizeAndCaptureResult] = None


router = APIRouter(prefix="/shopping", tags=["shopping"])


_PRODUCTS: Dict[str, Product] = {
    "540318": Product(
        id="540318",
        name="Milk Chocolate Bordeaux (1 lb)",
        description="See's Candies Milk Chocolate Bordeaux, 1 lb box (#540318).",
        price_cents=3300,
        sku="540318",
        inventory_count=150,
    ),
    "506542": Product(
        id="506542",
        name="Scotchmallow (1 lb)",
        description="See's Candies Scotchmallow, 1 lb box (#506542).",
        price_cents=3300,
        sku="506542",
        inventory_count=140,
    ),
    "peanut_brittle": Product(
        id="peanut_brittle",
        name="Peanut Brittle (1 lb)",
        description="Classic See's Candies Peanut Brittle, 1 lb box.",
        price_cents=3300,
        sku="PB-1LB",
        inventory_count=130,
    ),
    "assorted_chocolates": Product(
        id="assorted_chocolates",
        name="Assorted Chocolates (1 lb)",
        description="Signature Assorted Chocolates from See's Candies, 1 lb box.",
        price_cents=3300,
        sku="AC-1LB",
        inventory_count=160,
    ),
    "toffee_ettes": Product(
        id="toffee_ettes",
        name="Toffee-ettes (1 lb)",
        description="Crunchy, buttery Toffee-ettes from See's Candies, 1 lb tin.",
        price_cents=3300,
        sku="TE-1LB",
        inventory_count=120,
    ),
}

_CARTS: Dict[str, Cart] = {}
_CHECKOUTS: Dict[str, CheckoutSession] = {}


def _compute_cart_subtotal(cart: Cart) -> int:
    subtotal = 0
    for item in cart.items:
        product = _PRODUCTS.get(item.product_id)
        if not product:
            continue
        subtotal += product.price_cents * item.quantity
    return subtotal


def _compute_totals(cart: Cart) -> Totals:
    subtotal = _compute_cart_subtotal(cart)
    tax = int(round(subtotal * 0.08))  # 8% tax
    grand_total = subtotal + tax
    return Totals(
        subtotal_cents=subtotal,
        tax_cents=tax,
        grand_total_cents=grand_total,
        currency=cart.currency,
    )


@router.get(
    "/catalog",
    response_model=List[Product],
    summary="List See's Candies products discoverable by UCP agents.",
)
async def list_products() -> List[Product]:
    return list(_PRODUCTS.values())


class CreateCartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[CartItem]


@router.post(
    "/carts",
    response_model=CartSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new cart with one or more items.",
)
async def create_cart(
    payload: CreateCartRequest, request: Request
) -> CartSummary:
    principal: Optional[IdentityPrincipal] = await resolve_principal_from_request(
        request
    )
    cart_id = f"cart_{len(_CARTS) + 1}"
    cart = Cart(
        id=cart_id,
        items=payload.items,
        customer_reference=principal.customer_reference if principal else None,
    )
    _CARTS[cart_id] = cart
    totals = _compute_totals(cart)
    return CartSummary(
        id=cart.id,
        items=cart.items,
        currency=cart.currency,
        totals=totals,
    )


class UpdateCartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[CartItem]


@router.put(
    "/carts/{cart_id}",
    response_model=CartSummary,
    summary="Replace the contents of an existing cart.",
)
async def update_cart(cart_id: str, payload: UpdateCartRequest) -> CartSummary:
    cart = _CARTS.get(cart_id)
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cart_not_found",
        )
    cart.items = payload.items
    totals = _compute_totals(cart)
    return CartSummary(
        id=cart.id,
        items=cart.items,
        currency=cart.currency,
        totals=totals,
    )


@router.get(
    "/carts/{cart_id}",
    response_model=CartSummary,
    summary="Fetch the latest state of a cart.",
)
async def get_cart(cart_id: str) -> CartSummary:
    cart = _CARTS.get(cart_id)
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cart_not_found",
        )
    totals = _compute_totals(cart)
    return CartSummary(
        id=cart.id,
        items=cart.items,
        currency=cart.currency,
        totals=totals,
    )


@router.post(
    "/checkout",
    response_model=CheckoutSession,
    summary="Initiate a UCP 2026 checkout state machine for a cart.",
)
async def initiate_checkout(
    payload: CheckoutInitiateRequest, request: Request
) -> CheckoutSession:
    """
    UCP 2026-compliant checkout state machine:

    - 'incomplete':
        * Missing 'buyer' or 'shipping_address'.
        * Includes a 'messages' array with severity='error'.
    - 'requires_escalation':
        * All buyer data present, but missing 'auth_token' (Authorization header).
        * Includes 'continue_url' and a message with severity='escalation'.
    - 'ready_for_complete':
        * All data present (buyer, shipping_address, auth_token).
        * Agent can proceed to POST /ucp/complete.
    """
    cart = _CARTS.get(payload.cart_id)
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cart_not_found",
        )

    totals = _compute_totals(cart)
    checkout_id = f"chk_{len(_CHECKOUTS) + 1}"

    # Phase 1: validate buyer + shipping_address
    messages: List[UcpMessage] = []
    if not payload.buyer:
        messages.append(
            UcpMessage(
                code="buyer.missing",
                severity="error",
                text="Buyer information is required to initiate checkout.",
            )
        )
    elif not payload.buyer.shipping_address:
        messages.append(
            UcpMessage(
                code="buyer.shipping_address.missing",
                severity="error",
                text="Shipping address is required to initiate checkout.",
            )
        )

    if messages:
        session = CheckoutSession(
            id=checkout_id,
            cart_id=cart.id,
            state=CheckoutState.INCOMPLETE,
            total_cents=totals.grand_total_cents,
            currency=cart.currency,
            totals=totals,
            messages=messages,
        )
        _CHECKOUTS[checkout_id] = session
        return session

    # Phase 2: check for auth_token (Authorization header)
    auth_header = request.headers.get("Authorization")
    has_auth_token = bool(auth_header and auth_header.strip())

    if not has_auth_token:
        continue_url = "https://auth.sees-candies.example.com/ucp/login"
        session = CheckoutSession(
            id=checkout_id,
            cart_id=cart.id,
            state=CheckoutState.REQUIRES_ESCALATION,
            total_cents=totals.grand_total_cents,
            currency=cart.currency,
            totals=totals,
            escalation=EscalationContext(
                reason="auth_token_required",
                continue_url=continue_url,
            ),
            messages=[
                UcpMessage(
                    code="auth.escalation_required",
                    severity="escalation",
                    text=(
                        "Authorization token is required to complete checkout. "
                        "Redirect the shopper to 'continue_url' to complete login."
                    ),
                )
            ],
        )
    else:
        # All requirements met: ready for payment
        session = CheckoutSession(
            id=checkout_id,
            cart_id=cart.id,
            state=CheckoutState.READY_FOR_COMPLETE,
            total_cents=totals.grand_total_cents,
            currency=cart.currency,
            totals=totals,
            messages=[
                UcpMessage(
                    code="checkout.ready_for_complete",
                    severity="info",
                    text="Checkout session is ready for completion via POST /ucp/complete.",
                )
            ],
        )

    _CHECKOUTS[checkout_id] = session
    return session


@router.post(
    "/checkout/complete",
    response_model=CheckoutCompleteResponse,
    summary="Complete a checkout by invoking the legacy payment processor authorize & capture flow.",
)
async def complete_checkout(
    payload: CheckoutCompleteRequest, request: Request
) -> CheckoutCompleteResponse:
    session = _CHECKOUTS.get(payload.checkout_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="checkout_not_found",
        )

    if session.state != CheckoutState.READY_FOR_COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"checkout_not_ready_for_complete:{session.state}",
        )

    # Enforce presence of auth_token at completion time as well
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_or_invalid_auth_token",
        )

    cart = _CARTS.get(session.cart_id)
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cart_not_found",
        )

    legacy_request = LegacyAuthorizeAndCaptureRequest.from_checkout(
        checkout=session,
    )

    try:
        result = authorize_and_capture(legacy_request)
    except LegacyProcessorError as exc:
        session.state = CheckoutState.FAILED
        _CHECKOUTS[session.id] = session
        # The main router will translate this into a UCP-flavored error.
        raise exc

    session.state = CheckoutState.COMPLETED
    _CHECKOUTS[session.id] = session

    # Create order from completed checkout
    from gateway.services.orders import create_order_from_checkout

    create_order_from_checkout(session)

    return CheckoutCompleteResponse(checkout=session, payment=result)

