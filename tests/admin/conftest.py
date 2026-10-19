"""Shared setup for tests under tests/admin/.

`admin/services/__init__.py` eagerly imports `auth_service`, which raises
at import time if `ADMIN_SECRET_KEY` is unset. Setting it here (before any
test module under tests/admin/ is imported) keeps the unit tests
self-contained without requiring developers to export the env var.
"""
import os

# A deterministic Fernet key (32 url-safe base64-encoded bytes) for tests.
# Generated once via Fernet.generate_key(); safe to ship because it only
# touches in-memory test data.
os.environ.setdefault("ADMIN_SECRET_KEY", "test-secret-key-for-tests")
os.environ.setdefault("ADMIN_ENCRYPTION_KEY", "FA0Q2crZh6bl63yyQ2x3EiGOf2lngu8f_2WCAR5tYNI=")
