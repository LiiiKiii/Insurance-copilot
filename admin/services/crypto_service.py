"""Fail-closed Fernet helpers for encrypted configuration credentials.

The encryption key is intentionally resolved only when an operation is
requested.  This lets unrelated application components import safely while
ensuring that credential encryption and decryption cannot proceed without an
explicit, valid ``ADMIN_ENCRYPTION_KEY``.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


ADMIN_ENCRYPTION_KEY_ENV = "ADMIN_ENCRYPTION_KEY"


class EncryptionConfigurationError(ValueError):
    """Raised when the credential-encryption key is absent or invalid."""


class CredentialDecryptionError(ValueError):
    """Raised when an encrypted credential cannot be safely decrypted."""


def encrypt(value: str) -> str:
    """Encrypt a UTF-8 text value using the configured Fernet key.

    The returned token is URL-safe ASCII and is suitable for text persistence.
    """

    if not isinstance(value, str):
        raise TypeError("Value must be a string.")

    fernet = _fernet()
    try:
        return fernet.encrypt(value.encode("utf-8")).decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Value must be valid UTF-8 text.") from exc


def decrypt(token: str) -> str:
    """Decrypt a Fernet token without exposing token or key material on error."""

    if not isinstance(token, str):
        raise TypeError("Token must be a string.")

    fernet = _fernet()
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
        raise CredentialDecryptionError(
            "Encrypted credential is invalid or cannot be decrypted."
        ) from exc


def encrypt_if_not_empty(value: str | None) -> str | None:
    """Encrypt a present, non-empty credential while preserving absent values."""

    if value is None or value == "":
        return None
    return encrypt(value)


def decrypt_if_not_empty(token: str | None) -> str | None:
    """Decrypt a present, non-empty credential while preserving absent values."""

    if token is None or token == "":
        return None
    return decrypt(token)


def _fernet() -> Fernet:
    """Return the configured Fernet instance, rejecting missing/invalid keys."""

    key = os.getenv(ADMIN_ENCRYPTION_KEY_ENV)
    if key is None or not key.strip():
        raise EncryptionConfigurationError(
            "ADMIN_ENCRYPTION_KEY must be configured with a valid Fernet key."
        )

    try:
        return Fernet(key.encode("utf-8"))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise EncryptionConfigurationError(
            "ADMIN_ENCRYPTION_KEY must be configured with a valid Fernet key."
        ) from exc
