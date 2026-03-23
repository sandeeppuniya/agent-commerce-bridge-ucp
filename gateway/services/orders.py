from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from gateway.services.shopping import CheckoutSession, CheckoutState


class OrderStatus(str):
    CREATED = "created"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    checkout_id: str
    created_at: datetime
    status: str = Field(default=OrderStatus.CREATED)
    total_cents: int
    currency: str


class OrderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    total_cents: int
    currency: str


class OrderWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(..., description="Order identifier.")
    status: str = Field(
        ..., description="New status such as 'fulfilled' or 'cancelled'."
    )


router = APIRouter(prefix="/orders", tags=["orders"])


_ORDERS: Dict[str, Order] = {}


def create_order_from_checkout(checkout: CheckoutSession) -> Order:
    order_id = f"ord_{len(_ORDERS) + 1}"
    order = Order(
        id=order_id,
        checkout_id=checkout.id,
        created_at=datetime.now(timezone.utc),
        status=OrderStatus.CREATED,
        total_cents=checkout.total_cents,
        currency=checkout.currency,
    )
    _ORDERS[order_id] = order
    return order


@router.get(
    "/{order_id}",
    response_model=Order,
    summary="Fetch an order created from a completed checkout.",
)
async def get_order(order_id: str) -> Order:
    order = _ORDERS.get(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="order_not_found",
        )
    return order


@router.get(
    "",
    response_model=List[OrderSummary],
    summary="List all orders in this mock environment.",
)
async def list_orders() -> List[OrderSummary]:
    return [
        OrderSummary(
            id=o.id,
            status=o.status,
            total_cents=o.total_cents,
            currency=o.currency,
        )
        for o in _ORDERS.values()
    ]


@router.post(
    "/webhooks/status",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Mock webhook endpoint to update order status.",
)
async def webhook_update_status(event: OrderWebhookEvent) -> dict:
    order = _ORDERS.get(event.order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="order_not_found",
        )
    if event.status not in {
        OrderStatus.CREATED,
        OrderStatus.FULFILLED,
        OrderStatus.CANCELLED,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_status",
        )
    order.status = event.status
    _ORDERS[order.id] = order
    return {"order_id": order.id, "status": order.status}

