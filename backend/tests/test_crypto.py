"""
tests/test_crypto.py — Fernet crypto and SecretStore tests.
"""

from __future__ import annotations

import pytest

from app.core.crypto import decrypt, encrypt


def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = '{"access_token": "abc123", "refresh_token": "xyz"}'
    token = encrypt(plaintext)
    assert token != plaintext
    result = decrypt(token)
    assert result == plaintext


def test_encrypt_produces_different_tokens_each_time() -> None:
    """Fernet tokens include a timestamp + random IV, so each call differs."""
    pt = "same plaintext"
    t1 = encrypt(pt)
    t2 = encrypt(pt)
    assert t1 != t2
    assert decrypt(t1) == pt
    assert decrypt(t2) == pt


def test_invalid_token_raises() -> None:
    from cryptography.fernet import InvalidToken

    with pytest.raises((InvalidToken, Exception)):
        decrypt("not-a-valid-fernet-token")


def test_encrypt_raises_without_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """encrypt() must raise RuntimeError when SECRET_KEY is absent — fail closed."""
    import app.core.crypto as crypto_mod

    # Temporarily clear the cached key and patch settings to return None.
    saved_fernet = crypto_mod._fernet
    saved_ok = crypto_mod._fernet_ok
    crypto_mod._fernet = None
    crypto_mod._fernet_ok = False

    from app.config import Settings
    monkeypatch.setattr(
        "app.core.crypto._get_fernet_for_encrypt.__globals__['get_settings']",
        lambda: Settings(secret_key=None),
        raising=False,
    )

    try:
        # Patch at the module level instead.
        original_get_settings = None
        import app.config as config_mod
        original_get_settings = config_mod.get_settings

        def _no_key_settings() -> Settings:
            return Settings(secret_key=None)

        config_mod.get_settings = _no_key_settings  # type: ignore[assignment]
        crypto_mod._fernet = None
        crypto_mod._fernet_ok = False

        with pytest.raises(RuntimeError, match="SECRET_KEY must be set"):
            encrypt("test plaintext")
    finally:
        # Restore state so other tests are unaffected.
        if original_get_settings is not None:
            config_mod.get_settings = original_get_settings  # type: ignore[assignment]
        crypto_mod._fernet = saved_fernet
        crypto_mod._fernet_ok = saved_ok


@pytest.mark.asyncio
async def test_secret_store_set_get_delete() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.database as db_module
    from app.core.crypto import SecretStore
    from app.database import get_engine, init_db

    if db_module._engine is None:
        await init_db()

    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        store = SecretStore(session)

        # Set.
        await store.set("test.crypto.key", {"token": "super_secret"})

        # Get returns the original value.
        val = await store.get("test.crypto.key")
        assert val == {"token": "super_secret"}

        # Exists.
        assert await store.exists("test.crypto.key") is True
        assert await store.exists("test.nonexistent") is False

        # Delete.
        deleted = await store.delete("test.crypto.key")
        assert deleted is True
        assert await store.exists("test.crypto.key") is False

        # Delete again returns False.
        deleted2 = await store.delete("test.crypto.key")
        assert deleted2 is False


@pytest.mark.asyncio
async def test_secret_store_get_nonexistent_returns_none() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.database as db_module
    from app.core.crypto import SecretStore
    from app.database import get_engine, init_db

    if db_module._engine is None:
        await init_db()

    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        store = SecretStore(session)
        val = await store.get("key.that.does.not.exist")
        assert val is None
