"""
Helpers for encrypting/decrypting sensitive values stored in the database.

Currently used for `store_payment_integrations.secret_key`.
"""
from __future__ import annotations

import os


FERNET_TOKEN_PREFIX = "gAAAA"


class EncryptionError(RuntimeError):
    """Base error for encryption/decryption failures."""


class EncryptionNotConfiguredError(EncryptionError):
    """Raised when ENCRYPTION_KEY/crypto backend is missing."""


def is_dev_environment() -> bool:
    """Return True for non-production environments."""
    environment = os.getenv("ENVIRONMENT", "production").lower()
    return environment in {"development", "dev", "local", "test"}


def is_fernet_token(value: str | None) -> bool:
    """Heuristic check for Fernet-encrypted values."""
    return bool(value) and isinstance(value, str) and value.startswith(FERNET_TOKEN_PREFIX)


def _get_fernet():
    key = (os.getenv("ENCRYPTION_KEY") or "").strip()
    if not key:
        return None

    try:
        from cryptography.fernet import Fernet
    except Exception as e:  # pragma: no cover - depends on runtime env
        raise EncryptionNotConfiguredError(
            "cryptography is required for ENCRYPTION_KEY-based encryption"
        ) from e

    return Fernet(key.encode("utf-8"))


def encrypt_secret(value: str, *, allow_plaintext: bool) -> str:
    """
    Encrypt a secret value using Fernet.

    If `allow_plaintext` is True and ENCRYPTION_KEY is not configured, returns
    the original value (dev-only convenience).
    """
    if not value:
        return value

    if is_fernet_token(value):
        return value

    fernet = _get_fernet()
    if not fernet:
        if allow_plaintext:
            return value
        raise EncryptionNotConfiguredError("ENCRYPTION_KEY is not set")

    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    """
    Decrypt a Fernet-encrypted value.

    If the value is not encrypted (plaintext), returns it unchanged to preserve
    backward compatibility.
    """
    if not value:
        return value

    if not is_fernet_token(value):
        return value

    fernet = _get_fernet()
    if not fernet:
        raise EncryptionNotConfiguredError("ENCRYPTION_KEY is not set (required to decrypt)")

    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise EncryptionError("Failed to decrypt secret (invalid key or corrupted value)") from e

