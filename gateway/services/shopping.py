from enum import Enum
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from gateway.services.identity import IdentityPrincipal, resolve_principal_from_request
from gateway.processors.gpn_adapter import (
    GpnAuthorizeAndCaptureRequest,
    GpnAuthorizeAndCaptureResult,
    GpnError,
    authorize_and_capture,
)


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    price_cents: int
    currency: str = "USD"


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


class CartSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    items: List[CartItem]
    subtotal_cents: int
    currency: str


class CheckoutState(str, Enum):
    INCOMPLETE = "incomplete"
    REQUIRES_ESCALATION = "requires_escalation"
    READY_FOR_COMPLETE = "ready_for_complete"
    COMPLETED = "completed"
    FAILED = "failed"


class CheckoutInitiateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_id: str = Field(..., description="Identifier of the cart to check out.")


class EscalationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., description="Why escalation is required.")
    login_url: str = Field(..., description="URL to initiate identity linking.")


class CheckoutSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    cart_id: str
    state: CheckoutState
    total_cents: int
    currency: str
    customer_reference: Optional[str] = None
    escalation: Optional[EscalationContext] = None


class CheckoutCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkout_id: str = Field(..., description="Identifier of the checkout session.")


class CheckoutCompleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkout: CheckoutSession
    payment: Optional[GpnAuthorizeAndCaptureResult] = None


router = APIRouter(prefix="/shopping", tags=["shopping"])


_PRODUCTS: Dict[str, Product] = {
    "sc_truffles_box": Product(
        id="sc_truffles_box",
        name="See's Assorted Truffles (1 lb)",
        description="A classic assortment of rich chocolate truffles from See's Candies.",
        price_cents=3299,
    ),
    "sc_lollypops_variety": Product(
        id="sc_lollypops_variety",
        name="See's Lollypops Variety Pack",
        description="Caramel, chocolate, vanilla, and butterscotch lollypops.",
        price_cents=1599,
    ),
    "sc_peanut_brittle": Product(
        id="sc_peanut_brittle",
        name="See's Peanut Brittle",
        description="Small-batch, hand-pulled peanut brittle.",
        price_cents=1899,
    ),
    "sc_milk_chocolate": Product(
        id="sc_milk_chocolate",
        name="See's Milk Chocolate Bar (Pack of 4)",
        description="Silky milk chocolate bars in a convenient multi-pack.",
        price_cents=1299,
    ),
    "sc_dark_chocolate": Product(
        id="sc_dark_chocolate",
        name="See's Dark Chocolate Nuts & Chews",
        description="Dark chocolate assortment with nuts and chews.",
        price_cents=2499,
    ),
}

_CARTS: Dict[str, Cart] = {}
_CHECKOUTS: Dict[str, CheckoutSession] = {}


def _compute_cart_totals(cart: Cart) -> int:
    total = 0
    for item in cart.items:
        product = _PRODUCTS.get(item.product_id)
        if not product:
            continue
        total += product.price_cents * item.quantity
    return total


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
    subtotal = _compute_cart_totals(cart)
    return CartSummary(
        id=cart.id,
        items=cart.items,
        subtotal_cents=subtotal,
        currency=cart.currency,
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
    subtotal = _compute_cart_totals(cart)
    return CartSummary(
        id=cart.id,
        items=cart.items,
        subtotal_cents=subtotal,
        currency=cart.currency,
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
    subtotal = _compute_cart_totals(cart)
    return CartSummary(
        id=cart.id,
        items=cart.items,
        subtotal_cents=subtotal,
        currency=cart.currency,
    )


@router.post(
    "/checkout",
    response_model=CheckoutSession,
    summary="Initiate a UCP checkout state machine for a cart.",
)
async def initiate_checkout(
    payload: CheckoutInitiateRequest, request: Request
) -> CheckoutSession:
    cart = _CARTS.get(payload.cart_id)
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cart_not_found",
        )

    principal: Optional[IdentityPrincipal] = await resolve_principal_from_request(
        request
    )
    total = _compute_cart_totals(cart)
    checkout_id = f"chk_{len(_CHECKOUTS) + 1}"

    if not principal:
        from gateway.services.identity import start_identity_link, IdentityLinkRequest

        # Trigger escalation: identity linking is required before we can safely complete.
        link = await start_identity_link(
            IdentityLinkRequest(customer_reference=cart.id)
        )
        session = CheckoutSession(
            id=checkout_id,
            cart_id=cart.id,
            state=CheckoutState.REQUIRES_ESCALATION,
            total_cents=total,
            currency=cart.currency,
            escalation=EscalationContext(
                reason="identity_link_required",
                login_url=link.login_url,
            ),
        )
    else:
        session = CheckoutSession(
            id=checkout_id,
            cart_id=cart.id,
            state=CheckoutState.READY_FOR_COMPLETE,
            total_cents=total,
            currency=cart.currency,
            customer_reference=principal.customer_reference,
        )

    _CHECKOUTS[checkout_id] = session
    return session


@router.post(
    "/checkout/complete",
    response_model=CheckoutCompleteResponse,
    summary="Complete a checkout by invoking the GPN-backed authorize & capture flow.",
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

    principal: Optional[IdentityPrincipal] = await resolve_principal_from_request(
        request
    )
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_or_invalid_authorization",
        )

    cart = _CARTS.get(session.cart_id)
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cart_not_found",
        )

    gpn_request = GpnAuthorizeAndCaptureRequest.from_cart_and_checkout(
        cart=cart,
        checkout=session,
    )

    try:
        result = authorize_and_capture(gpn_request)
    except GpnError as exc:
        session.state = CheckoutState.FAILED
        _CHECKOUTS[session.id] = session
        # The main router will translate this into a UCP-flavored error.
        raise exc

    session.state = CheckoutState.COMPLETED
    _CHECKOUTS[session.id] = session

    return CheckoutCompleteResponse(checkout=session, payment=result)

