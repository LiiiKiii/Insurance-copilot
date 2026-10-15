"""Offline tests for credential encryption helpers."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from admin.services.crypto_service import (
    CredentialDecryptionError,
    EncryptionConfigurationError,
    decrypt,
    decrypt_if_not_empty,
    encrypt,
    encrypt_if_not_empty,
)


class CryptoServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        os.environ.pop("ADMIN_ENCRYPTION_KEY", None)
        os.environ.pop("ADMIN_SECRET_KEY", None)
        self.key = Fernet.generate_key().decode("ascii")

    def tearDown(self) -> None:
        self.environment.stop()

    def _configure_key(self) -> None:
        os.environ["ADMIN_ENCRYPTION_KEY"] = self.key

    def test_encrypt_decrypt_round_trip_supports_unicode(self) -> None:
        self._configure_key()
        standard_fernet = Fernet(self.key.encode("ascii"))

        token = encrypt("保單 API key: café")

        self.assertIsInstance(token, str)
        self.assertNotIn("保單 API key: café", token)
        self.assertEqual(
            standard_fernet.decrypt(token.encode("ascii")).decode("utf-8"),
            "保單 API key: café",
        )
        self.assertEqual(decrypt(token), "保單 API key: café")

    def test_empty_helper_values_remain_absent(self) -> None:
        self.assertIsNone(encrypt_if_not_empty(None))
        self.assertIsNone(encrypt_if_not_empty(""))
        self.assertIsNone(decrypt_if_not_empty(None))
        self.assertIsNone(decrypt_if_not_empty(""))

    def test_non_empty_helpers_round_trip(self) -> None:
        self._configure_key()

        token = encrypt_if_not_empty("credential")

        self.assertIsInstance(token, str)
        self.assertEqual(decrypt_if_not_empty(token), "credential")

    def test_missing_key_fails_closed_without_using_jwt_secret(self) -> None:
        os.environ["ADMIN_SECRET_KEY"] = Fernet.generate_key().decode("ascii")

        with self.assertRaises(EncryptionConfigurationError) as error:
            encrypt("credential")

        self.assertNotIn(os.environ["ADMIN_SECRET_KEY"], str(error.exception))

    def test_empty_or_invalid_key_is_rejected(self) -> None:
        for key in ("", "not-a-fernet-key"):
            with self.subTest(key=key):
                os.environ["ADMIN_ENCRYPTION_KEY"] = key
                with self.assertRaises(EncryptionConfigurationError):
                    encrypt("credential")

    def test_invalid_or_wrong_key_token_is_rejected_without_leakage(self) -> None:
        self._configure_key()
        token = encrypt("credential")
        os.environ["ADMIN_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")

        for invalid_token in ("not-a-token", token):
            with self.subTest(token=invalid_token):
                with self.assertRaises(CredentialDecryptionError) as error:
                    decrypt(invalid_token)
                self.assertNotIn(invalid_token, str(error.exception))

    def test_invalid_token_helper_does_not_hide_corruption(self) -> None:
        self._configure_key()

        with self.assertRaises(CredentialDecryptionError):
            decrypt_if_not_empty("not-a-token")

    def test_non_string_inputs_are_rejected(self) -> None:
        self._configure_key()

        with self.assertRaises(TypeError):
            encrypt(None)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            decrypt(None)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            encrypt_if_not_empty(1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            decrypt_if_not_empty(1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
