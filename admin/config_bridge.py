"""Read the system default briefing model configuration.

This bridge has no tenant input, so it deliberately resolves only an enabled,
global default LLM.  Tenant-scoped model configuration requires an explicit
tenant-aware interface rather than being silently selected for a system call.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy.exc import SQLAlchemyError

from admin.services.crypto_service import (
    CredentialDecryptionError,
    EncryptionConfigurationError,
    decrypt_if_not_empty,
)

logger = logging.getLogger(__name__)


class DefaultModelConfigurationError(RuntimeError):
    """Raised when a selected model configuration cannot be safely used."""


class DefaultModelConfigurationAmbiguityError(DefaultModelConfigurationError):
    """Raised when multiple global default LLM configurations are eligible."""


def get_default_model_config() -> dict | None:
    """Return the enabled global default LLM configuration and resolved API key.

    A missing eligible configuration or an unavailable database preserves the
    historical ``None`` result for the briefing generator's rule-based
    fallback.  Stored credential failures are intentionally different: they
    raise a sanitized error and never fall back to environment credentials.
    """

    try:
        from admin.db import get_sync_db
        from admin.models.model_config import ModelConfig

        with get_sync_db() as db:
            rows = (
                db.query(ModelConfig)
                .filter(
                    ModelConfig.is_default.is_(True),
                    ModelConfig.model_type == "llm",
                    ModelConfig.enabled.is_(True),
                    ModelConfig.tenant_id.is_(None),
                )
                .order_by(ModelConfig.id.asc())
                .limit(2)
                .all()
            )
    except SQLAlchemyError:
        # The existing caller treats ``None`` as a signal to use its local,
        # deterministic fallback.  Do not log the database exception: it may
        # contain connection details or SQL text.
        logger.warning("Default model configuration database lookup failed.")
        return None

    if not rows:
        return None
    if len(rows) > 1:
        raise DefaultModelConfigurationAmbiguityError(
            "Multiple global default model configurations are enabled."
        )

    row = rows[0]
    if row.api_key_encrypted is None or row.api_key_encrypted == "":
        api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
    else:
        try:
            api_key = decrypt_if_not_empty(row.api_key_encrypted)
        except (CredentialDecryptionError, EncryptionConfigurationError) as exc:
            raise DefaultModelConfigurationError(
                "Stored model credential cannot be decrypted."
            ) from exc

    return {
        "id": row.id,
        "provider": row.provider,
        "model_id": row.model_id,
        "display_name": row.display_name,
        "api_key": api_key,
        "base_url": row.base_url,
        "max_tokens": row.max_tokens or 4096,
        "temperature": row.temperature if row.temperature is not None else 0.7,
    }
