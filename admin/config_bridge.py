"""Read the default briefing model configuration for the A3 integration.

The completed project exposes a wider configuration bridge. This staged
version intentionally includes only the model lookup required by the M3 daily
briefing generator.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_default_model_config() -> dict | None:
    """Return the enabled default LLM configuration and resolved API key."""
    try:
        from admin.db import get_sync_db
        from admin.models.model_config import ModelConfig

        with get_sync_db() as db:
            row = (
                db.query(ModelConfig)
                .filter(
                    ModelConfig.is_default.is_(True),
                    ModelConfig.model_type == "llm",
                    ModelConfig.enabled.is_(True),
                )
                .first()
            )
        if not row:
            return None

        api_key = None
        if row.api_key_encrypted:
            try:
                from admin.services.crypto_service import decrypt_if_not_empty

                api_key = decrypt_if_not_empty(row.api_key_encrypted)
            except Exception as exc:
                logger.debug("Unable to decrypt the configured model key: %s", exc)

        if not api_key:
            api_key = (
                os.environ.get("OPENROUTER_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
            )

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
    except Exception as exc:
        logger.debug("Default model configuration lookup failed: %s", exc)
        return None
