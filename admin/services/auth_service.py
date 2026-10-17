"""JWT authentication and password hashing service."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ADMIN_ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("ADMIN_REFRESH_TOKEN_DAYS", "7"))

try:
    import bcrypt as _bcrypt_lib

    def hash_password(password: str) -> str:
        pw = password.encode("utf-8")[:72]  # bcrypt limit
        return _bcrypt_lib.hashpw(pw, _bcrypt_lib.gensalt()).decode("utf-8")

    def verify_password(plain: str, hashed: str) -> bool:
        return _bcrypt_lib.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))

except ImportError:
    # Fallback to passlib
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)


def _secret_key() -> str:
    """Return the configured signing key without creating an implicit default."""
    secret = os.environ.get("ADMIN_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "ADMIN_SECRET_KEY must be configured before issuing or validating admin tokens."
        )
    return secret


def create_access_token(payload: dict[str, Any]) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    data["type"] = "access"
    return jwt.encode(data, _secret_key(), algorithm=ALGORITHM)


def create_refresh_token(payload: dict[str, Any]) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    data["type"] = "refresh"
    return jwt.encode(data, _secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify JWT. Raises JWTError on failure."""
    return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
