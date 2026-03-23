from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field


class IdentityLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_reference: str = Field(
        ...,
        description=(
            "Opaque reference for the shopper from the UCP or merchant context "
            "(e.g. email, wallet id, or external customer id)."
        ),
    )


class IdentityLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(..., description="Synthetic identifier for the link operation.")
    login_url: str = Field(
        ...,
        description="URL where the shopper should be redirected to complete login/consent.",
    )
    expires_at: datetime = Field(
        ..., description="ISO timestamp when this login URL expires."
    )


class TokenExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="Mock authorization code from the login redirect.")


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(..., description="Mock OAuth 2.0 bearer token.")
    token_type: str = Field(default="Bearer", description="Token type.")
    expires_in: int = Field(
        ..., description="Token lifetime in seconds from the time of issuance."
    )
    scope: str = Field(
        default="ucp.shopping ucp.orders",
        description="Granted scopes for this token (space-delimited).",
    )
    customer_reference: str = Field(
        ..., description="Echo of the bound customer reference for this identity link."
    )


class IdentityContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_reference: str
    issued_at: datetime
    expires_at: datetime


router = APIRouter(prefix="/identity", tags=["identity"])


_PENDING_LINKS: Dict[str, IdentityLinkResponse] = {}
_ACTIVE_TOKENS: Dict[str, IdentityContext] = {}


@router.post(
    "/link",
    response_model=IdentityLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Begin identity linking via mock OAuth2 authorization flow.",
)
async def start_identity_link(payload: IdentityLinkRequest) -> IdentityLinkResponse:
    """
    Initiates a mock OAuth 2.0 authorization flow for identity linking.

    In a real implementation, this would mint a short-lived authorization URL
    that redirects to a hosted login + consent page for See's Candies.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=10)

    link_id = f"link_{int(now.timestamp())}_{hash(payload.customer_reference) & 0xffff}"
    login_url = f"https://auth.sees-candies.example.com/login?link_id={link_id}"

    link = IdentityLinkResponse(link_id=link_id, login_url=login_url, expires_at=expires_at)
    _PENDING_LINKS[link_id] = link

    return link


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Exchange a mock authorization code for an access token.",
)
async def exchange_code_for_token(
    payload: TokenExchangeRequest,
) -> TokenResponse:
    """
    Exchanges a mock authorization code for an OAuth 2.0-style access token.

    For this mock implementation, we treat the code as a direct reference to
    an existing link_id.
    """
    link = _PENDING_LINKS.get(payload.code)
    if not link or link.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_or_expired_code",
        )

    now = datetime.now(timezone.utc)
    ttl_seconds = 30 * 60
    expires_at = now + timedelta(seconds=ttl_seconds)

    token = f"tok_{int(now.timestamp())}_{hash(payload.code) & 0xffff}"
    context = IdentityContext(
        customer_reference=link.link_id,
        issued_at=now,
        expires_at=expires_at,
    )
    _ACTIVE_TOKENS[token] = context

    return TokenResponse(
        access_token=token,
        expires_in=ttl_seconds,
        customer_reference=context.customer_reference,
    )


class IdentityPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_reference: str


async def resolve_principal_from_request(request: Request) -> Optional[IdentityPrincipal]:
    """
    Helper used by checkout and order flows to validate the Authorization header.

    If the header is missing or invalid, returns None instead of raising.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    try:
        scheme, token = auth_header.split(" ", 1)
    except ValueError:
        return None

    if scheme.lower() != "bearer":
        return None

    context = _ACTIVE_TOKENS.get(token)
    if not context or context.expires_at <= datetime.now(timezone.utc):
        return None

    return IdentityPrincipal(customer_reference=context.customer_reference)

