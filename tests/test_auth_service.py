"""Offline tests for the authentication-service primitives."""

from __future__ import annotations

import base64
import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from jose import jwt

from admin.services.auth_service import (
    AuthenticationConfigurationError,
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


TEST_SECRET = "offline-test-secret-with-at-least-thirty-two-bytes"


class AuthenticationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        for name in (
            "ADMIN_SECRET_KEY",
            "ADMIN_ACCESS_TOKEN_MINUTES",
            "ADMIN_REFRESH_TOKEN_DAYS",
        ):
            os.environ.pop(name, None)
        os.environ["ADMIN_SECRET_KEY"] = TEST_SECRET

    def tearDown(self) -> None:
        self.environment.stop()

    def test_import_has_no_secret_configuration_side_effect(self) -> None:
        self.assertTrue(callable(create_access_token))

    def test_hash_is_bcrypt_compatible_and_uses_distinct_salts(self) -> None:
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")

        self.assertTrue(first.startswith("$2"))
        self.assertEqual(60, len(first))
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("correct horse battery staple", first))

    def test_incorrect_password_and_invalid_hash_fail_without_detail(self) -> None:
        hashed = hash_password("correct-password")

        self.assertFalse(verify_password("wrong-password", hashed))
        self.assertFalse(verify_password("correct-password", "not-a-bcrypt-hash"))
        self.assertFalse(verify_password("correct-password", "$2b$bad"))

    def test_unicode_passwords_use_utf8_byte_length(self) -> None:
        password = "\u4fdd\u9669\U0001f510"
        hashed = hash_password(password)

        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("\u4fdd\u9669\U0001f513", hashed))

    def test_passwords_over_72_utf8_bytes_are_rejected_not_truncated(self) -> None:
        oversized = "\u5bc6" * 25  # 75 UTF-8 bytes

        with self.assertRaisesRegex(ValueError, "72-byte"):
            hash_password(oversized)
        self.assertFalse(verify_password(oversized, hash_password("safe-password")))

    def test_bcrypt_72_byte_boundary_is_explicit(self) -> None:
        accepted = "a" * 72
        rejected = "a" * 73
        hashed = hash_password(accepted)

        self.assertTrue(verify_password(accepted, hashed))
        with self.assertRaisesRegex(ValueError, "72-byte"):
            hash_password(rejected)
        self.assertFalse(verify_password(rejected, hashed))

    def test_non_string_passwords_are_explicitly_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, "Password must be a string"):
            hash_password(None)  # type: ignore[arg-type]
        self.assertFalse(verify_password(None, hash_password("safe-password")))  # type: ignore[arg-type]

    def test_access_token_preserves_payload_and_uses_default_expiry(self) -> None:
        before = int(time.time())
        token = create_access_token({"sub": "user-1", "tenant_id": "tenant-a", "roles": ["user"]})
        claims = decode_token(token)

        self.assertEqual("user-1", claims["sub"])
        self.assertEqual("tenant-a", claims["tenant_id"])
        self.assertEqual(["user"], claims["roles"])
        self.assertEqual("access", claims["type"])
        self.assertGreaterEqual(claims["exp"], before + (14 * 60))
        self.assertLessEqual(claims["exp"], before + (16 * 60))

    def test_refresh_token_has_refresh_type_and_default_expiry(self) -> None:
        before = int(time.time())
        claims = decode_token(create_refresh_token({"sub": "user-1"}))

        self.assertEqual("refresh", claims["type"])
        self.assertGreaterEqual(claims["exp"], before + (6 * 24 * 60 * 60))
        self.assertLessEqual(claims["exp"], before + (8 * 24 * 60 * 60))

    def test_token_claims_supplied_by_callers_are_not_mutated(self) -> None:
        payload = {"sub": "user-1", "type": "caller-value", "exp": 1}
        token = create_access_token(payload)

        self.assertEqual({"sub": "user-1", "type": "caller-value", "exp": 1}, payload)
        self.assertEqual("access", decode_token(token)["type"])

    def test_expired_token_is_rejected(self) -> None:
        expired = jwt.encode(
            {"sub": "user-1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            TEST_SECRET,
            algorithm="HS256",
        )

        with self.assertRaisesRegex(TokenValidationError, "expired"):
            decode_token(expired)

    def test_token_without_expiration_is_rejected(self) -> None:
        no_expiration = jwt.encode(
            {"sub": "user-1", "type": "access"},
            TEST_SECRET,
            algorithm="HS256",
        )

        with self.assertRaisesRegex(TokenValidationError, "invalid"):
            decode_token(no_expiration)

    def test_signed_future_expiration_is_accepted(self) -> None:
        future = jwt.encode(
            {"sub": "user-1", "exp": datetime.now(timezone.utc) + timedelta(minutes=1)},
            TEST_SECRET,
            algorithm="HS256",
        )

        self.assertEqual("user-1", decode_token(future)["sub"])

    def test_malformed_expiration_is_rejected(self) -> None:
        malformed = jwt.encode(
            {"sub": "user-1", "exp": "not-a-timestamp"},
            TEST_SECRET,
            algorithm="HS256",
        )

        with self.assertRaisesRegex(TokenValidationError, "invalid"):
            decode_token(malformed)

    def test_invalid_signature_and_tampering_are_rejected(self) -> None:
        token = create_access_token({"sub": "user-1", "roles": ["user"]})
        wrong_signature = jwt.encode(
            {"sub": "user-1", "exp": datetime.now(timezone.utc) + timedelta(minutes=1)},
            "another-offline-secret-with-at-least-thirty-two-bytes",
            algorithm="HS256",
        )

        with self.assertRaisesRegex(TokenValidationError, "invalid"):
            decode_token(wrong_signature)
        with self.assertRaisesRegex(TokenValidationError, "invalid"):
            decode_token(_replace_payload_roles(token, ["admin"]))

    def test_unsupported_algorithm_is_rejected(self) -> None:
        hs384_token = jwt.encode(
            {"sub": "user-1", "exp": datetime.now(timezone.utc) + timedelta(minutes=1)},
            TEST_SECRET,
            algorithm="HS384",
        )

        with self.assertRaisesRegex(TokenValidationError, "invalid"):
            decode_token(hs384_token)

    def test_missing_or_invalid_secret_fails_closed_without_leaking_secret(self) -> None:
        os.environ.pop("ADMIN_SECRET_KEY")
        with self.assertRaises(AuthenticationConfigurationError) as missing:
            create_access_token({"sub": "user-1"})
        self.assertNotIn(TEST_SECRET, str(missing.exception))

        os.environ["ADMIN_SECRET_KEY"] = "too-short"
        with self.assertRaises(AuthenticationConfigurationError) as invalid:
            create_access_token({"sub": "user-1"})
        self.assertNotIn("too-short", str(invalid.exception))

    def test_invalid_expiration_settings_fail_closed(self) -> None:
        os.environ["ADMIN_ACCESS_TOKEN_MINUTES"] = "0"
        with self.assertRaises(AuthenticationConfigurationError):
            create_access_token({"sub": "user-1"})

        os.environ.pop("ADMIN_ACCESS_TOKEN_MINUTES")
        os.environ["ADMIN_REFRESH_TOKEN_DAYS"] = "not-a-number"
        with self.assertRaises(AuthenticationConfigurationError):
            create_refresh_token({"sub": "user-1"})


def _replace_payload_roles(token: str, roles: list[str]) -> str:
    """Produce a syntactically valid token with an unchanged signature."""

    header, payload, signature = token.split(".")
    padded = payload + "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(padded))
    claims["roles"] = roles
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return ".".join((header, encoded, signature))
