"""
app/core/oauth.py — Google and Microsoft OAuth2 authorization-code helpers.

Provides build_authorize_url(), exchange_code(), refresh_token(), and
revoke_token() for both providers.  Credentials are stored via SecretStore
(encrypted at rest).  This module never sends tokens to the frontend.

All network calls that use sync SDKs (google-auth, msal) are wrapped with
anyio.to_thread.run_sync so they never block the event loop.

Token refresh
─────────────
``maybe_refresh_google_token()`` and ``maybe_refresh_microsoft_token()`` are
the authoritative refresh helpers consumed by the calendar and slideshow
adapters.  They:
  1. Check whether the stored access token is expired (or will expire within
     the next 5 minutes).
  2. If so, call the provider's refresh endpoint and persist the updated
     token dict via the caller-supplied ``set_secret_fn``.
  3. Return the (possibly refreshed) access token string.

Callers should retry the underlying API call once after receiving a fresh
token; if the retry also returns 401 the caller should mark the source as
"error" and stop.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio.to_thread

logger = logging.getLogger(__name__)

# ── Secret key names ─────────────────────────────────────────────────────────
GOOGLE_SECRET_KEY = "oauth.google"
MICROSOFT_SECRET_KEY = "oauth.microsoft"

# Refresh tokens that expire within this window are pre-emptively refreshed.
_REFRESH_WINDOW = timedelta(minutes=5)


# ── Google ────────────────────────────────────────────────────────────────────

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/photoslibrary.readonly",
]

GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URI = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_google_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the Google OAuth2 consent URL."""
    import urllib.parse

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URI}?{urllib.parse.urlencode(params)}"


async def exchange_google_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange a Google authorization code for access + refresh tokens."""
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URI,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code != 200:
        logger.error("Google token exchange failed: %s %s", resp.status_code, resp.text)
        raise ValueError(f"Google token exchange failed: {resp.status_code}")

    return resp.json()


async def refresh_google_token(
    refresh_token_value: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Refresh a Google access token.  Returns the full new token response."""
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URI,
            data={
                "refresh_token": refresh_token_value,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            },
        )

    if resp.status_code != 200:
        logger.error("Google token refresh failed: %s %s", resp.status_code, resp.text)
        raise ValueError(f"Google token refresh failed: {resp.status_code}")

    return resp.json()


async def maybe_refresh_google_token(
    stored: dict[str, Any],
    client_id: str,
    client_secret: str,
    set_secret_fn: Any,   # async callable(key, value)
) -> str:
    """Return a valid Google access token, refreshing if expired.

    ``stored`` is the token dict retrieved from SecretStore.
    ``set_secret_fn`` is called with ``(GOOGLE_SECRET_KEY, new_token_dict)``
    if a refresh is performed.

    Returns the access token string (fresh or existing).
    """
    access_token: str = stored.get("access_token", "")
    expires_at_str: str | None = stored.get("expires_at")
    refresh_token_value: str | None = stored.get("refresh_token")

    # Determine whether the token is about to expire.
    needs_refresh = False
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            needs_refresh = datetime.now(UTC) >= expires_at - _REFRESH_WINDOW
        except ValueError:
            needs_refresh = False

    if not needs_refresh or not refresh_token_value:
        return access_token

    logger.info("Google access token expiring; refreshing.")
    try:
        new_tokens = await refresh_google_token(
            refresh_token_value=refresh_token_value,
            client_id=client_id,
            client_secret=client_secret,
        )
        # Merge: keep the refresh_token if the response doesn't include one.
        merged = {**stored, **new_tokens}
        if "expires_in" in new_tokens:
            merged["expires_at"] = (
                datetime.now(UTC) + timedelta(seconds=int(new_tokens["expires_in"]))
            ).isoformat()

        await set_secret_fn(GOOGLE_SECRET_KEY, merged)
        logger.info("Google access token refreshed and persisted.")
        return merged.get("access_token", access_token)

    except Exception as exc:
        logger.warning("Google token refresh failed: %s — using existing token.", exc)
        return access_token


async def get_google_account_email(access_token: str) -> str | None:
    """Fetch the email address for the Google account."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                GOOGLE_USERINFO_URI,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code == 200:
            return resp.json().get("email")
    except Exception as exc:
        logger.warning("Failed to fetch Google account info: %s", exc)
    return None


async def revoke_google_token(access_token: str) -> None:
    """Revoke a Google access token."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            await client.post(GOOGLE_REVOKE_URI, params={"token": access_token})
    except Exception as exc:
        logger.warning("Google token revoke failed: %s", exc)


# ── Microsoft / Outlook ───────────────────────────────────────────────────────

MS_SCOPES = [
    "offline_access",
    "User.Read",
    "Calendars.ReadWrite",
]


def build_microsoft_authorize_url(
    client_id: str, tenant_id: str, redirect_uri: str, state: str
) -> str:
    """Build the Microsoft OAuth2 consent URL."""
    import urllib.parse

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(MS_SCOPES),
        "state": state,
    }
    auth_uri = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    return f"{auth_uri}?{urllib.parse.urlencode(params)}"


async def exchange_microsoft_code(
    code: str,
    client_id: str,
    client_secret: str,
    tenant_id: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange a Microsoft authorization code for tokens using msal (sync → thread)."""
    def _exchange() -> dict[str, Any]:
        import msal
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=MS_SCOPES,
            redirect_uri=redirect_uri,
        )
        if "error" in result:
            raise ValueError(
                f"Microsoft token exchange failed: "
                f"{result.get('error_description', result['error'])}"
            )
        return result

    return await anyio.to_thread.run_sync(_exchange)


async def refresh_microsoft_token(
    refresh_token_value: str,
    client_id: str,
    client_secret: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Refresh a Microsoft access token using msal (sync → thread)."""
    def _refresh() -> dict[str, Any]:
        import msal
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        result = app.acquire_token_by_refresh_token(
            refresh_token=refresh_token_value,
            scopes=MS_SCOPES,
        )
        if "error" in result:
            raise ValueError(
                f"Microsoft token refresh failed: "
                f"{result.get('error_description', result['error'])}"
            )
        return result

    return await anyio.to_thread.run_sync(_refresh)


async def maybe_refresh_microsoft_token(
    stored: dict[str, Any],
    client_id: str,
    client_secret: str,
    tenant_id: str,
    set_secret_fn: Any,   # async callable(key, value)
) -> str:
    """Return a valid Microsoft access token, refreshing if expired.

    Mirrors ``maybe_refresh_google_token``; uses msal token keys
    (``access_token``, ``refresh_token``, ``expires_in``).
    """
    access_token: str = stored.get("access_token", "")
    expires_at_str: str | None = stored.get("expires_at")
    refresh_token_value: str | None = stored.get("refresh_token")

    needs_refresh = False
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            needs_refresh = datetime.now(UTC) >= expires_at - _REFRESH_WINDOW
        except ValueError:
            needs_refresh = False

    if not needs_refresh or not refresh_token_value:
        return access_token

    logger.info("Microsoft access token expiring; refreshing.")
    try:
        new_tokens = await refresh_microsoft_token(
            refresh_token_value=refresh_token_value,
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
        )
        merged = {**stored, **new_tokens}
        if "expires_in" in new_tokens:
            merged["expires_at"] = (
                datetime.now(UTC) + timedelta(seconds=int(new_tokens["expires_in"]))
            ).isoformat()

        await set_secret_fn(MICROSOFT_SECRET_KEY, merged)
        logger.info("Microsoft access token refreshed and persisted.")
        return merged.get("access_token", access_token)

    except Exception as exc:
        logger.warning("Microsoft token refresh failed: %s — using existing token.", exc)
        return access_token


async def get_microsoft_account_email(access_token: str) -> str | None:
    """Fetch the email for the Microsoft account."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("mail") or data.get("userPrincipalName")
    except Exception as exc:
        logger.warning("Failed to fetch Microsoft account info: %s", exc)
    return None


# ── State token helpers ───────────────────────────────────────────────────────

def generate_state() -> str:
    """Generate a cryptographically random OAuth state token."""
    return secrets.token_urlsafe(32)
