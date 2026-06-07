"""
app/routers/oauth.py — OAuth2 authorization-code flow endpoints.

Routes:
  GET    /api/oauth/{provider}/authorize  → { url }
  GET    /api/oauth/{provider}/callback   → redirect to /settings?oauth={provider}
  GET    /api/oauth/{provider}/status     → { connected, account? }
  DELETE /api/oauth/{provider}            → 204

Supported providers: google, microsoft
Secrets (tokens) are stored encrypted via SecretStore; never sent to the client.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import SecretStore
from app.core.oauth import (
    GOOGLE_SECRET_KEY,
    MICROSOFT_SECRET_KEY,
    build_google_authorize_url,
    build_microsoft_authorize_url,
    exchange_google_code,
    exchange_microsoft_code,
    generate_state,
    get_google_account_email,
    get_microsoft_account_email,
    revoke_google_token,
)
from app.database import get_session
from app.schemas import OAuthAuthorizeResponse, OAuthStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

Provider = Literal["google", "microsoft"]

# In-memory state store (LAN-only app; state is short-lived).
# Maps state token → provider name for CSRF validation.
_pending_states: dict[str, str] = {}


def _secret_key_for(provider: Provider) -> str:
    if provider == "google":
        return GOOGLE_SECRET_KEY
    return MICROSOFT_SECRET_KEY


def _redirect_uri_for(provider: Provider, request: Request) -> str:
    from app.config import get_settings
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/api/oauth/{provider}/callback"


@router.get("/{provider}/authorize", response_model=OAuthAuthorizeResponse)
async def get_authorize_url(
    provider: Provider,
    request: Request,
) -> OAuthAuthorizeResponse:
    """Return the provider's consent URL.  The frontend opens this in a new tab."""
    from app.config import get_settings

    settings = get_settings()
    state = generate_state()
    _pending_states[state] = provider
    redirect_uri = _redirect_uri_for(provider, request)

    if provider == "google":
        if not settings.google_client_id:
            raise HTTPException(status_code=503, detail="Google OAuth not configured")
        url = build_google_authorize_url(
            client_id=settings.google_client_id,
            redirect_uri=redirect_uri,
            state=state,
        )
    else:
        if not settings.ms_client_id:
            raise HTTPException(status_code=503, detail="Microsoft OAuth not configured")
        url = build_microsoft_authorize_url(
            client_id=settings.ms_client_id,
            tenant_id=settings.ms_tenant_id,
            redirect_uri=redirect_uri,
            state=state,
        )

    return OAuthAuthorizeResponse(url=url)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: Provider,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Handle the OAuth callback.  Exchanges the code for tokens and redirects."""
    from app.config import get_settings
    settings = get_settings()

    # Validate state to prevent CSRF.
    if state is None or _pending_states.pop(state, None) != provider:
        logger.warning("OAuth callback: invalid or missing state for provider %r", provider)
        return RedirectResponse(url="/settings?oauth_error=invalid_state")

    if error:
        logger.warning("OAuth callback error from %r: %s", provider, error)
        return RedirectResponse(url=f"/settings?oauth_error={error}&provider={provider}")

    if not code:
        return RedirectResponse(url="/settings?oauth_error=no_code")

    redirect_uri = _redirect_uri_for(provider, request)
    store = SecretStore(session)

    try:
        if provider == "google":
            tokens = await exchange_google_code(
                code=code,
                client_id=settings.google_client_id or "",
                client_secret=settings.google_client_secret or "",
                redirect_uri=redirect_uri,
            )
        else:
            tokens = await exchange_microsoft_code(
                code=code,
                client_id=settings.ms_client_id or "",
                client_secret=settings.ms_client_secret or "",
                tenant_id=settings.ms_tenant_id,
                redirect_uri=redirect_uri,
            )

        await store.set(_secret_key_for(provider), tokens)
        logger.info("OAuth tokens stored for provider %r", provider)

    except RuntimeError as exc:
        # Raised by SecretStore.set() when SECRET_KEY is absent/invalid.
        logger.error("Cannot store OAuth tokens for %r — SECRET_KEY not configured: %s", provider, exc)
        return RedirectResponse(url=f"/settings?oauth_error=secret_key_not_configured&provider={provider}")

    except Exception as exc:
        logger.error("OAuth code exchange failed for %r: %s", provider, exc)
        return RedirectResponse(url=f"/settings?oauth_error=exchange_failed&provider={provider}")

    return RedirectResponse(url=f"/settings?oauth={provider}")


@router.get("/{provider}/status", response_model=OAuthStatusResponse)
async def get_oauth_status(
    provider: Provider,
    session: AsyncSession = Depends(get_session),
) -> OAuthStatusResponse:
    """Return whether the provider is connected (tokens exist)."""
    store = SecretStore(session)
    tokens = await store.get(_secret_key_for(provider))

    if tokens is None:
        return OAuthStatusResponse(connected=False)

    # Try to resolve the account email without blocking.
    account: str | None = None
    try:
        access_token = tokens.get("access_token") or tokens.get("accessToken", "")
        if provider == "google":
            account = await get_google_account_email(access_token)
        else:
            account = await get_microsoft_account_email(access_token)
    except Exception as exc:
        logger.debug("Could not fetch account info for %r: %s", provider, exc)

    return OAuthStatusResponse(connected=True, account=account)


@router.delete("/{provider}", status_code=204)
async def revoke_oauth(
    provider: Provider,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Revoke the stored OAuth tokens and delete them from the secret store."""
    store = SecretStore(session)
    tokens = await store.get(_secret_key_for(provider))

    if tokens is not None:
        if provider == "google":
            access_token = tokens.get("access_token", "")
            if access_token:
                await revoke_google_token(access_token)
        # Microsoft revocation happens server-side on token expiry or via Graph API;
        # deleting the stored token is sufficient for our purposes.

        await store.delete(_secret_key_for(provider))
        logger.info("OAuth tokens revoked for provider %r", provider)
