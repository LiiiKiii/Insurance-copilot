"""Small, fail-closed primitives for the future authentication API.

This module intentionally has no database, FastAPI, or import-time configuration
side effects.  Authentication configuration is read when a token operation is
requested so that unrelated application components remain usable until the
authentication router is introduced.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt


ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7
MAX_BCRYPT_PASSWORD_BYTES = 72
MINIMUM_SECRET_BYTES = 32


class AuthenticationConfigurationError(ValueError):
    """Raised when authentication settings are missing or unsafe."""


class TokenValidationError(ValueError):
    """Raised when a token cannot be safely validated."""


def hash_password(password: str) -> str:
    """Return a newly salted bcrypt hash for ``password``.

    bcrypt accepts at most 72 password bytes.  Rejecting oversized passwords is
    deliberate: silently truncating a newly chosen password can make two
    different passwords authenticate as the same credential.
    """

    password_bytes = _password_bytes(password)
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Safely check a plaintext password against a stored bcrypt hash.

    Invalid input, malformed stored values, and over-limit inputs produce a
    normal authentication failure rather than exposing bcrypt implementation
    details.  Existing valid bcrypt hashes remain supported.
    """

    try:
        plain_bytes = _password_bytes(plain)
        if not isinstance(hashed, str):
            return False
        return bcrypt.checkpw(plain_bytes, hashed.encode("ascii"))
    except (TypeError, ValueError, UnicodeError):
        return False


def create_access_token(payload: dict[str, Any]) -> str:
    """Create an HS256 access token with the configured expiration."""

    return _create_token(payload, token_type="access", expires_in=_access_lifetime())


def create_refresh_token(payload: dict[str, Any]) -> str:
    """Create an HS256 refresh token with the configured expiration."""

    return _create_token(payload, token_type="refresh", expires_in=_refresh_lifetime())


def decode_token(token: str) -> dict[str, Any]:
    """Validate and decode a token signed by this application.

    Only HS256 is accepted.  Callers remain responsible for checking whether a
    valid token is appropriate for a particular operation (for example, access
    versus refresh token use) when those routes are added later.
    """

    if not isinstance(token, str) or not token:
        raise TokenValidationError("Token is invalid.")

    try:
        decoded = jwt.decode(
            token,
            _signing_secret(),
            algorithms=["HS256"],
            options={"verify_aud": False, "require_exp": True},
        )
    except ExpiredSignatureError as exc:
        raise TokenValidationError("Token has expired.") from exc
    except JWTError as exc:
        raise TokenValidationError("Token is invalid.") from exc

    if not isinstance(decoded, dict):
        raise TokenValidationError("Token is invalid.")
    return decoded


def _create_token(
    payload: dict[str, Any], *, token_type: str, expires_in: timedelta
) -> str:
    if not isinstance(payload, dict):
        raise TypeError("Token payload must be a dictionary.")

    claims = payload.copy()
    claims["exp"] = datetime.now(timezone.utc) + expires_in
    claims["type"] = token_type
    return jwt.encode(claims, _signing_secret(), algorithm="HS256")


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise TypeError("Password must be a string.")

    try:
        password_bytes = password.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Password must be valid UTF-8 text.") from exc

    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(
            f"Password exceeds bcrypt's {MAX_BCRYPT_PASSWORD_BYTES}-byte limit."
        )
    return password_bytes


def _signing_secret() -> str:
    secret = os.getenv("ADMIN_SECRET_KEY")
    if secret is None or not secret.strip():
        raise AuthenticationConfigurationError("ADMIN_SECRET_KEY must be configured.")
    if len(secret.encode("utf-8")) < MINIMUM_SECRET_BYTES:
        raise AuthenticationConfigurationError(
            "ADMIN_SECRET_KEY must be at least 32 bytes long."
        )
    return secret


def _access_lifetime() -> timedelta:
    return timedelta(minutes=_positive_setting("ADMIN_ACCESS_TOKEN_MINUTES", ACCESS_TOKEN_MINUTES))


def _refresh_lifetime() -> timedelta:
    return timedelta(days=_positive_setting("ADMIN_REFRESH_TOKEN_DAYS", REFRESH_TOKEN_DAYS))


def _positive_setting(name: str, default: int) -> int:
    configured = os.getenv(name)
    if configured is None:
        return default
    try:
        value = int(configured)
    except ValueError as exc:
        raise AuthenticationConfigurationError(
            f"{name} must be a positive integer."
        ) from exc
    if value <= 0:
        raise AuthenticationConfigurationError(f"{name} must be a positive integer.")
    return value
