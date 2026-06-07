"""
app/core/crypto.py — Fernet-based encryption for secrets at rest.

All OAuth tokens, CalDAV passwords and other sensitive values MUST be stored
via ``SecretStore`` and never sent to the frontend.

**Fail-closed design**: ``SecretStore.set()`` (and the underlying ``encrypt()``)
raise ``RuntimeError`` when ``SECRET_KEY`` is absent or invalid.  The app boots
without a key, but any attempt to *write* a credential is rejected with a clear
error message that propagates up to the API layer as a 503.  Reading from an
empty or unconfigured store returns ``None`` (no crash, no plaintext leakage).

Generate a key::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import select

logger = logging.getLogger(__name__)

# ── Key management ────────────────────────────────────────────────────────────

_fernet: Fernet | None = None
_fernet_ok: bool = False     # True only when a valid persistent key is loaded


def _get_fernet_for_encrypt() -> Fernet:
    """Return the Fernet instance for *encryption* (write path).

    Raises ``RuntimeError`` if ``SECRET_KEY`` is not configured or is invalid,
    so the caller surfaces a clear error rather than silently storing plaintext.
    """
    global _fernet, _fernet_ok

    if _fernet_ok and _fernet is not None:
        return _fernet

    from app.config import get_settings
    secret_key = get_settings().secret_key

    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY must be set to store credentials. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\" and add it to .env."
        )

    try:
        _fernet = Fernet(secret_key.encode())
        _fernet_ok = True
        return _fernet
    except Exception as exc:
        raise RuntimeError(
            f"SECRET_KEY is set but is not a valid Fernet key: {exc}. "
            "Re-generate it with the command above."
        ) from exc


def _get_fernet_for_decrypt() -> Fernet | None:
    """Return the Fernet instance for *decryption* (read path).

    Returns ``None`` (instead of raising) when no key is configured, so reads
    from an empty or unconfigured store degrade gracefully to returning ``None``.
    """
    global _fernet, _fernet_ok

    if _fernet_ok and _fernet is not None:
        return _fernet

    from app.config import get_settings
    secret_key = get_settings().secret_key

    if not secret_key:
        return None

    try:
        _fernet = Fernet(secret_key.encode())
        _fernet_ok = True
        return _fernet
    except Exception as exc:
        logger.error("SECRET_KEY is invalid, cannot decrypt: %s", exc)
        return None


# ── Low-level encrypt/decrypt ─────────────────────────────────────────────────

def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string and return the Fernet token as a str.

    Raises ``RuntimeError`` if ``SECRET_KEY`` is not configured or invalid.
    """
    token: bytes = _get_fernet_for_encrypt().encrypt(plaintext.encode())
    return token.decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token and return the original UTF-8 string.

    Raises ``InvalidToken`` if the token is corrupt or was encrypted with a
    different key.  Raises ``RuntimeError`` if no key is configured.
    """
    fernet = _get_fernet_for_decrypt()
    if fernet is None:
        raise RuntimeError("SECRET_KEY not configured; cannot decrypt stored secrets.")
    plaintext: bytes = fernet.decrypt(token.encode())
    return plaintext.decode()


# ── SecretStore ───────────────────────────────────────────────────────────────

class SecretStore:
    """Async CRUD for the ``secret`` table with transparent Fernet encryption.

    Values are JSON-serialised before encryption so any JSON-serialisable type
    (dict, list, str, …) can be stored.

    **Fail-closed**: ``set()`` raises ``RuntimeError`` if ``SECRET_KEY`` is not
    configured.  ``get()`` returns ``None`` if the key is absent or unreadable.

    Usage::

        store = SecretStore(session)
        await store.set("oauth.google", {"access_token": "...", ...})
        token = await store.get("oauth.google")
        await store.delete("oauth.google")
    """

    def __init__(self, session: AsyncSession) -> None:  # noqa: F821
        self._session = session

    async def get(self, key: str) -> Any | None:
        """Return the decrypted value for ``key``, or ``None`` if absent."""
        from app.models import Secret

        result = await self._session.execute(
            select(Secret).where(Secret.key == key)
        )
        row: Secret | None = result.scalar_one_or_none()

        if row is None:
            return None

        try:
            plaintext = decrypt(row.value)
            return json.loads(plaintext)
        except (InvalidToken, RuntimeError, json.JSONDecodeError) as exc:
            logger.error("Failed to decrypt secret %r: %s", key, exc)
            return None

    async def set(self, key: str, value: Any) -> None:
        """Encrypt and persist ``value`` under ``key`` (upsert).

        Raises ``RuntimeError`` if ``SECRET_KEY`` is not configured.
        The caller (OAuth/CalDAV connect flow) should catch this and return
        a 503 with the message so the user knows to configure the key.
        """
        from app.models import Secret

        plaintext = json.dumps(value)
        token = encrypt(plaintext)   # raises RuntimeError if key absent/invalid

        result = await self._session.execute(
            select(Secret).where(Secret.key == key)
        )
        row: Secret | None = result.scalar_one_or_none()

        if row is None:
            row = Secret(key=key, value=token, updated_at=datetime.now(UTC))
            self._session.add(row)
        else:
            row.value = token
            row.updated_at = datetime.now(UTC)

        await self._session.commit()

    async def delete(self, key: str) -> bool:
        """Remove the secret for ``key``.  Returns ``True`` if a row was deleted."""
        from sqlmodel import select

        from app.models import Secret

        result = await self._session.execute(
            select(Secret).where(Secret.key == key)
        )
        row: Secret | None = result.scalar_one_or_none()

        if row is None:
            return False

        await self._session.delete(row)
        await self._session.commit()
        return True

    async def exists(self, key: str) -> bool:
        """Return ``True`` if a (possibly unreadable) secret exists for ``key``."""
        from sqlmodel import select

        from app.models import Secret

        result = await self._session.execute(
            select(Secret.key).where(Secret.key == key)
        )
        return result.scalar_one_or_none() is not None
