from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway.services.shopping import CheckoutSession


class LegacyAuthorizeAndCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str = Field(
        ...,
        description="Identifier for See's Candies within the legacy payment processor platform.",
    )
    amount_cents: int = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=3)
    reference: str = Field(..., description="Order or checkout reference.")

    @classmethod
    def from_checkout(
        cls,
        checkout: CheckoutSession,
        merchant_id: str = "sees-candies-us",
    ) -> "LegacyAuthorizeAndCaptureRequest":
        return cls(
            merchant_id=merchant_id,
            amount_cents=checkout.total_cents,
            currency=checkout.currency,
            reference=checkout.id,
        )


class LegacyAuthorizeAndCaptureResult(BaseModel):
    """
    Legacy payment processor API-style response for an authorize & capture call.

    Field semantics:
    - transaction_id: TRN_... identifier issued by the legacy processor.
    - status: CAPTURED (success), DECLINED (insufficient funds), or REJECTED (request error).
    - response_code:
        * '00'  -> Success, funds captured.
        * '101' -> Declined, insufficient funds.
        * '502' -> Rejected, mandatory field missing.
    """

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(
        ..., description="Unique legacy processor transaction ID in TRN_xxx format."
    )
    status: Literal["CAPTURED", "DECLINED", "REJECTED"] = Field(
        ..., description="Transaction status per legacy payment processor API."
    )
    response_code: str = Field(
        ...,
        description="Legacy processor response code ('00' success, '101' insufficient funds, '502' mandatory field missing).",
    )
    time_created: str = Field(
        ..., description="ISO-8601 timestamp of transaction creation (UTC)."
    )
    amount_cents: int = Field(..., description="Transaction amount in cents.")
    currency: str = Field(..., description="ISO-4217 currency code.")
    message: str = Field(..., description="Human-readable summary from the legacy payment processor.")


class LegacyProcessorError(Exception):
    """
    Raised when the simulated legacy payment processor returns a non-success outcome
    that must be translated into a UCP-flavored error for API consumers.
    """

    def __init__(self, response_code: str, status: str, message: str) -> None:
        self.response_code = response_code
        self.status = status
        self.message = message
        super().__init__(message)


def _validate_mandatory_fields(request: LegacyAuthorizeAndCaptureRequest) -> None:
    missing_fields: list[str] = []

    if not request.merchant_id:
        missing_fields.append("merchant_id")
    if not request.currency:
        missing_fields.append("currency")
    if not request.reference:
        missing_fields.append("reference")
    if request.amount_cents <= 0:
        missing_fields.append("amount_cents")

    if missing_fields:
        fields_str = ", ".join(missing_fields)
        raise LegacyProcessorError(
            response_code="502",
            status="REJECTED",
            message=f"Mandatory field(s) missing or invalid in legacy processor request: {fields_str}.",
        )


def authorize_and_capture(
    request: LegacyAuthorizeAndCaptureRequest,
) -> LegacyAuthorizeAndCaptureResult:
    """
    Simulate the legacy payment processor's authorize-and-capture behavior
    with Fintech-grade semantics.

    Outcome rules:
    - If any mandatory field is missing/invalid:
        * response_code = '502'
        * status        = 'REJECTED'
    - Else if amount_cents > $500.00 (50000 cents):
        * response_code = '101'
        * status        = 'DECLINED'
    - Else:
        * response_code = '00'
        * status        = 'CAPTURED'
    """
    _validate_mandatory_fields(request)

    # Insufficient funds rule for high-ticket orders
    if request.amount_cents > 500 * 100:
        message = (
            "Transaction declined by legacy payment processor platform "
            "(response_code=101, reason=insufficient_funds)."
        )
        raise LegacyProcessorError(response_code="101", status="DECLINED", message=message)

    # Successful capture
    now = datetime.now(timezone.utc)
    # Professional 2026-style TRN identifier with fixed merchant prefix.
    # Format: TRN_SEES_<epoch_seconds>
    txn_id = f"TRN_SEES_{int(now.timestamp())}"

    return LegacyAuthorizeAndCaptureResult(
        transaction_id=txn_id,
        status="CAPTURED",
        response_code="00",
        time_created=now.isoformat(),
        amount_cents=request.amount_cents,
        currency=request.currency,
        message="Transaction captured successfully by the legacy payment processor.",
    )
