from __future__ import annotations

import os

import pytest


def _route_paths(app) -> set[str]:
    paths: set[str] = set()
    for route in app.router.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
    return paths


def test_api_debug_paths_route_dev_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.api_server import create_api_app

    monkeypatch.setenv("ENVIRONMENT", "production")
    app_prod = create_api_app()
    assert "/api/debug/paths" not in _route_paths(app_prod)

    monkeypatch.setenv("ENVIRONMENT", "development")
    app_dev = create_api_app()
    assert "/api/debug/paths" in _route_paths(app_dev)


def test_payment_secret_encryption_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.fernet import Fernet

    from database_pg_module.crypto import (
        EncryptionNotConfiguredError,
        decrypt_secret,
        encrypt_secret,
        is_fernet_token,
    )

    secret = "super-secret-value"

    # Missing key: production mode should fail closed
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(EncryptionNotConfiguredError):
        encrypt_secret(secret, allow_plaintext=False)

    # Missing key: dev mode can allow plaintext (explicit opt-in)
    assert encrypt_secret(secret, allow_plaintext=True) == secret

    # With key: encrypt + decrypt should roundtrip
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("ENCRYPTION_KEY", key)

    encrypted = encrypt_secret(secret, allow_plaintext=False)
    assert encrypted != secret
    assert is_fernet_token(encrypted)
    assert decrypt_secret(encrypted) == secret

